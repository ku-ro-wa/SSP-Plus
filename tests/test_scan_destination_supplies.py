"""Without paper or ink, scan_destination still offers the digital copy."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication  # noqa: E402

from screens.scan_destination.view import ScanDestinationScreenView  # noqa: E402

app = QApplication.instance() or QApplication([])


def test_low_supplies_disable_print_but_keep_digital():
    view = ScanDestinationScreenView()
    view.print_option.set_selected(True)
    view.send_wifi_option.set_selected(True)

    view.set_print_available(False)

    assert view.get_selected_keys() == {'send_wifi'}
    assert not view.print_option.isEnabled()
    assert view.send_wifi_option.isEnabled()
    assert view.continue_button.isEnabled()


def test_print_only_selection_cannot_continue_once_print_is_unavailable():
    view = ScanDestinationScreenView()
    view.print_option.set_selected(True)
    view.set_print_available(False)
    assert not view.continue_button.isEnabled()


def test_print_available_again_re_enables_it():
    view = ScanDestinationScreenView()
    view.set_print_available(False)
    view.set_print_available(True)
    assert view.print_option.isEnabled()
