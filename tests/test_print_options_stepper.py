"""
The copies stepper on the print options screen (offscreen Qt). On the kiosk's
touchscreen a few taps jumped copies straight to 10, as if the panel reported
one touch several times, so taps closer together than STEPPER_REPEAT_MS count once.
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from screens.print_options.view import STEPPER_REPEAT_MS, PrintOptionsScreenView  # noqa: E402


app = QApplication.instance() or QApplication([])


def _view_and_counts():
    view = PrintOptionsScreenView()
    counts = {"up": 0, "down": 0}
    view.copies_increased.connect(lambda: counts.__setitem__("up", counts["up"] + 1))
    view.copies_decreased.connect(lambda: counts.__setitem__("down", counts["down"] + 1))
    return view, counts


def test_a_burst_of_taps_steps_once():
    view, counts = _view_and_counts()
    for _ in range(9):
        QTest.mouseClick(view.copies_plus_btn, Qt.LeftButton)
    assert counts["up"] == 1


def test_separate_taps_each_step():
    view, counts = _view_and_counts()
    QTest.mouseClick(view.copies_plus_btn, Qt.LeftButton)
    QTest.qWait(STEPPER_REPEAT_MS + 50)
    QTest.mouseClick(view.copies_plus_btn, Qt.LeftButton)
    QTest.qWait(STEPPER_REPEAT_MS + 50)
    QTest.mouseClick(view.copies_minus_btn, Qt.LeftButton)
    assert counts == {"up": 2, "down": 1}
