"""
Every screen's view lives inside its controller, never as a window of its own.

payment, thank_you, print_options and file_browser used to take only the view's
layout (`self.setLayout(self.view.main_layout)`). The view's widgets moved into
the controller, but the view QWidget itself stayed a parentless top-level window,
never shown, owned only by Python and destroyed in whatever order Python's
teardown picked after the app closed.
"""
import os
import re
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from screens.file_browser.controller import FileBrowserController
from screens.print_options.controller import PrintOptionsController
from screens.thank_you.controller import ThankYouController
from screens.payment.view import PaymentScreenView
from managers.voucher_manager import CODE_ALPHABET

app = QApplication.instance() or QApplication([])

SCREENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SSP", "screens")


def test_no_controller_takes_its_views_layout():
    offenders = []
    for root, _dirs, files in os.walk(SCREENS_DIR):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    if re.search(r"setLayout\(\s*self\.view\.", f.read()):
                        offenders.append(os.path.relpath(path, SCREENS_DIR))
    assert offenders == []


@pytest.mark.parametrize("controller_class", [ThankYouController, PrintOptionsController, FileBrowserController])
def test_controller_holds_its_view_and_adds_no_window(monkeypatch, controller_class):
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    windows_before = set(QApplication.topLevelWidgets())

    controller = controller_class(MagicMock())
    try:
        assert controller.view.parent() is controller
        assert controller.view.layout() is controller.view.main_layout
        assert set(QApplication.topLevelWidgets()) - windows_before == {controller}
    finally:
        for stop in ("stop_analysis", "cleanup"):
            getattr(controller.model, stop, lambda: None)()
        controller.deleteLater()


def test_payment_view_owns_its_layout():
    view = PaymentScreenView(voucher_keys=CODE_ALPHABET)
    assert view.layout() is view.main_layout
