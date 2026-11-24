"""
No pop-up on the kiosk has a window-manager title bar: maximising then minimising one
left the customer on the Pi desktop, outside the app. ui/dialogs.py's boxes and the PIN
dialog are frameless, the PIN dialog has its own Cancel (usable during a lockout), and
the main window restores itself if minimised.
"""
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from ui.dialogs import DIALOG_BUTTON_HEIGHT, KioskMessageBox  # noqa: E402

SSP_DIR = Path(__file__).resolve().parent.parent / "SSP"


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def frameless(widget):
    return bool(widget.windowFlags() & Qt.FramelessWindowHint)


def test_kiosk_message_box_has_no_title_bar(qapp):
    box = KioskMessageBox(None, "Low on change", "Pay the exact amount.", QMessageBox.Warning)
    assert frameless(box)
    assert box.text() == "Low on change"  # the title a title bar would have shown
    assert box.informativeText() == "Pay the exact amount."


def test_kiosk_message_box_buttons_are_touch_sized(qapp):
    box = KioskMessageBox(None, "Title", "Text")
    button = box.addButton("OK", QMessageBox.AcceptRole)
    box.show()
    qapp.processEvents()
    try:
        assert button.height() >= DIALOG_BUTTON_HEIGHT
    finally:
        box.hide()


def test_pin_dialog_is_frameless_with_a_cancel_that_survives_the_lockout(qapp):
    from screens.dialogs.pin_dialog.view import PinDialogView
    dialog = PinDialogView()
    assert frameless(dialog)
    dialog.set_locked(True, 300)
    assert dialog.cancel_button.isEnabled()
    dialog.show()
    dialog.cancel_button.click()
    assert dialog.result() == QDialog.Rejected


def test_no_screen_uses_a_native_message_box():
    # QMessageBox's static helpers and bare QMessageBox(...) get a title bar on the kiosk.
    native = re.compile(r"QMessageBox\.(warning|information|critical|question)\(|QMessageBox\(")
    offenders = [
        f"{path.relative_to(SSP_DIR)}:{n}"
        for path in (SSP_DIR / "screens").rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if native.search(line)
    ]
    assert offenders == []


@pytest.mark.parametrize("sim_mode,restored", [(False, True), (True, False)])
def test_main_window_restores_itself_when_minimised(qapp, sim_mode, restored):
    from PyQt5.QtCore import QEvent
    from PyQt5.QtWidgets import QMainWindow

    import main_app

    # A PrintingSystemApp without its __init__ (no screens, threads or hardware)
    window = main_app.PrintingSystemApp.__new__(main_app.PrintingSystemApp)
    QMainWindow.__init__(window)
    calls = []
    window.showFullScreen = lambda: calls.append("fullscreen")
    window.isMinimized = lambda: True
    config = type("Config", (), {"sim_mode": sim_mode})()
    with patch.object(main_app, "get_config", return_value=config), \
            patch.object(main_app.QTimer, "singleShot", lambda _ms, fn: fn()):
        window.changeEvent(QEvent(QEvent.WindowStateChange))
    assert (calls == ["fullscreen"]) == restored
