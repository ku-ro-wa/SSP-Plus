"""
The copies stepper on the print options screen (offscreen Qt). The kiosk's touch
panel sometimes reports one press as several taps, so taps closer together than
STEPPER_REPEAT_MS count once.
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from managers.print_items import PrintItem  # noqa: E402
from screens.print_options.view import STEPPER_REPEAT_MS, PrintOptionsScreenView  # noqa: E402

app = QApplication.instance() or QApplication([])


def _view_and_counts():
    view = PrintOptionsScreenView()
    view.set_items([PrintItem({'path': 'a.pdf', 'filename': 'a.pdf'}, [1])])
    counts = {"up": 0, "down": 0}
    view.item_copies_step.connect(lambda i, d: counts.__setitem__("up" if d > 0 else "down", counts["up" if d > 0 else "down"] + 1))
    return view, view.item_rows[0], counts


def test_a_burst_of_taps_steps_once():
    view, row, counts = _view_and_counts()
    for _ in range(9):
        QTest.mouseClick(row.copies_plus_btn, Qt.LeftButton)
    assert counts["up"] == 1


def test_separate_taps_each_step():
    view, row, counts = _view_and_counts()
    QTest.mouseClick(row.copies_plus_btn, Qt.LeftButton)
    QTest.qWait(STEPPER_REPEAT_MS + 50)
    QTest.mouseClick(row.copies_plus_btn, Qt.LeftButton)
    QTest.qWait(STEPPER_REPEAT_MS + 50)
    QTest.mouseClick(row.copies_minus_btn, Qt.LeftButton)
    assert counts == {"up": 2, "down": 1}
