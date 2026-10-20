"""
ScreenChangeTapGuard (offscreen Qt): the kiosk's touch panel sometimes reports one
press as two taps, and the second landed on the next screen's button in the same
spot (file_browser's "Set Print Options" -> print_options' "Continue to Payment").
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from ui.tap_guard import ScreenChangeTapGuard  # noqa: E402

app = QApplication.instance() or QApplication([])


def _guarded_button(guard_ms=100):
    guard = ScreenChangeTapGuard(guard_ms)
    app.installEventFilter(guard)
    button = QPushButton("Continue")
    clicks = []
    button.clicked.connect(lambda: clicks.append(1))
    return guard, button, clicks


def test_a_tap_right_after_a_screen_change_is_dropped():
    guard, button, clicks = _guarded_button()
    try:
        guard.arm()
        QTest.mouseClick(button, Qt.LeftButton)
        assert clicks == []
    finally:
        app.removeEventFilter(guard)


def test_taps_go_through_once_the_screen_has_settled():
    guard, button, clicks = _guarded_button()
    try:
        QTest.mouseClick(button, Qt.LeftButton)  # never armed
        guard.arm()
        QTest.qWait(guard.guard_ms + 50)
        QTest.mouseClick(button, Qt.LeftButton)
        assert clicks == [1, 1]
    finally:
        app.removeEventFilter(guard)
