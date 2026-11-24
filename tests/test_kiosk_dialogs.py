"""
Pop-ups are overlays inside the app window (ui/dialogs.py), never separate windows: a
window's title bar let a customer maximise then minimise it and land on the Pi desktop,
outside the app. The PIN dialog is one too, with its own Cancel (usable during a lockout),
and the main window restores itself if it is minimised anyway.
"""
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialog, QMainWindow, QWidget  # noqa: E402

from ui import dialogs  # noqa: E402
from ui.dialogs import DIALOG_BUTTON_HEIGHT, MessageDialog, OverlayDialog  # noqa: E402

SSP_DIR = Path(__file__).resolve().parent.parent / "SSP"


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def screen(qapp):
    """A screen inside a kiosk-sized window, as the app has it."""
    window = QMainWindow()
    window.resize(1422, 800)
    central = QWidget()
    window.setCentralWidget(central)
    window.show()
    qapp.processEvents()
    yield central
    window.close()


def answer(text):
    """Tap the button labelled `text` on the overlay that opens next."""
    def tap():
        dialog = OverlayDialog.active()
        [button] = [b for b in dialog.buttons() if b.text() == text]
        button.click()
    QTimer.singleShot(0, tap)


def test_a_message_is_an_overlay_over_the_whole_window_not_a_window(screen):
    dialog = MessageDialog(screen, "Low on change", "Pay the exact amount.")
    dialog.add_button("OK", primary=True)
    seen = {}

    def check():
        seen['window'] = dialog.isWindow()
        seen['covers'] = dialog.geometry() == screen.window().rect()
        seen['button_height'] = dialog.buttons()[0].height()
        dialog.buttons()[0].click()
    QTimer.singleShot(0, check)

    assert dialog.exec_() == QDialog.Accepted
    assert seen == {'window': False, 'covers': True, 'button_height': seen['button_height']}
    assert seen['button_height'] >= DIALOG_BUTTON_HEIGHT


def test_the_tapped_button_is_reported(screen):
    dialog = MessageDialog(screen, "Collect cash", "Record these counts?")
    dialog.add_button("Cancel", cancel=True)
    collect = dialog.add_button("Collect", primary=True)
    answer("Cancel")
    assert dialog.exec_() == QDialog.Rejected
    assert dialog.clicked_button() is not collect


def test_helpers_wait_for_ok(screen):
    answer("OK")
    assert dialogs.warning(screen, "No PDF Selected", "Please tick at least one file.") == QDialog.Accepted
    assert OverlayDialog.active() is None


def test_pin_dialog_is_an_overlay_with_a_cancel_that_survives_the_lockout(screen):
    from screens.dialogs.pin_dialog.view import PinDialogView
    dialog = PinDialogView(screen)
    assert not dialog.isWindow()
    dialog.set_locked(True, 300)
    assert dialog.cancel_button.isEnabled()
    QTimer.singleShot(0, dialog.cancel_button.click)
    assert dialog.exec_() == QDialog.Rejected


def test_no_screen_uses_a_native_message_box():
    # QMessageBox opens a window with a title bar on the kiosk.
    native = re.compile(r"QMessageBox|QInputDialog")
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
