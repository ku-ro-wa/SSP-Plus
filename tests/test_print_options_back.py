"""
Back on the print options screen returns to where the files came from: the file
browser (ticks, tick order and pages kept), or the scan's destination choice.
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
import pytest  # noqa: E402

from managers.print_items import PrintItem  # noqa: E402
from screens.file_browser.controller import FileBrowserController  # noqa: E402
from screens.print_options.controller import PrintOptionsController  # noqa: E402

app = QApplication.instance() or QApplication([])

PDF = os.path.join(os.path.dirname(__file__), '..', 'test_pdfs', 'Rootlocus-Plotting-1.pdf')


class FakeMainApp:
    """Records navigation and runs the outgoing/incoming screen hooks like show_screen()."""

    def __init__(self):
        self.shown = []
        self.screens = {}
        self.open_voucher_balance = MagicMock()
        self.print_supplies_low = MagicMock(return_value=False)
        self.admin_screen = MagicMock(get_paper_count=MagicMock(return_value=100))

    def show_screen(self, name):
        if self.shown and self.shown[-1] in self.screens:
            self.screens[self.shown[-1]].on_leave()
        self.shown.append(name)
        if name in self.screens:
            self.screens[name].on_enter()


@pytest.fixture
def kiosk():
    main_app = FakeMainApp()
    main_app.printing_options_screen = PrintOptionsController(main_app)
    main_app.file_browser_screen = FileBrowserController(main_app)
    main_app.screens = {'printing_options': main_app.printing_options_screen,
                        'file_browser': main_app.file_browser_screen}
    yield main_app
    # set_items() queues a paper check and starts pricing; finish both here, not in a later test.
    QTest.qWait(150)
    main_app.printing_options_screen.model.stop_analysis()


def test_back_returns_to_the_file_browser_with_the_same_files_ticked(kiosk):
    main_app = kiosk
    browser, options = main_app.file_browser_screen, main_app.printing_options_screen
    browser.set_source('usb')
    files = [{'filename': name, 'pages': 2, 'size': 1, 'path': f'{PDF}?{name}'} for name in ('a.pdf', 'b.pdf')]
    browser.view.load_pdf_files(files)
    browser.view.ticked = []
    browser.view.toggle_tick(browser.view.pdf_files_data[1])
    browser.view.toggle_tick(browser.view.pdf_files_data[0])
    browser.view.pdf_page_selections[files[1]['path']] = {1: False, 2: True}
    ticked_before = browser.view.ticked_files()

    browser._continue_to_payment()
    options.view.back_button_clicked.emit()

    assert main_app.shown == ['printing_options', 'file_browser']
    assert browser.view.ticked_files() == ticked_before
    assert [(p['filename'], pages) for p, pages in ticked_before] == [('b.pdf', [2]), ('a.pdf', [1, 2])]


def test_back_after_a_scan_returns_to_the_scan_destination(kiosk):
    main_app = kiosk
    options = main_app.printing_options_screen
    options.set_items([PrintItem({'path': PDF, 'filename': 'scan.pdf'}, [1])], 'scanner')

    options.view.back_button_clicked.emit()

    assert main_app.shown == ['scan_destination']
