# screens/scanner/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from .model import ScannerModel
from .view import ScannerScreenView


class ScannerController(QWidget):
    """Manages the Scanner screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = ScannerModel()
        self.view = ScannerScreenView()
        self._scan_completed = False

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        self.view.cancel_clicked.connect(self._handle_cancel)
        self.view.cancel_clicked.connect(self._reset_timeout)

        self.view.scan_page_clicked.connect(self._handle_scan_page)
        self.view.scan_page_clicked.connect(self._reset_timeout)

        self.view.rescan_clicked.connect(self._handle_rescan)
        self.view.rescan_clicked.connect(self._reset_timeout)

        self.view.done_clicked.connect(self._handle_done)
        self.view.done_clicked.connect(self._reset_timeout)

        self.model.busy_changed.connect(self.view.set_busy)
        self.model.page_scanned.connect(self._handle_page_scanned)
        self.model.scan_failed.connect(self._handle_scan_failed)
        self.model.scan_finished.connect(self._handle_scan_finished)
        self.model.finish_failed.connect(self._handle_finish_failed)

    def _handle_scan_page(self):
        self.view.show_status("Scanning...", is_error=False)
        self.model.scan_page()

    def _handle_rescan(self):
        self.view.show_status("Rescanning last page...", is_error=False)
        self.model.rescan_last()

    def _handle_page_scanned(self, page_number, image_path):
        self.view.update_page_count(page_number)
        self.view.show_thumbnail(image_path)
        self.view.show_status(f"Page {page_number} scanned.", is_error=False)

    def _handle_scan_failed(self, message):
        self.view.show_status(message, is_error=True)

    def _handle_done(self):
        self.view.show_status("Preparing your document...", is_error=False)
        self.model.finish()

    def _handle_scan_finished(self, pdf_path, page_count):
        self._scan_completed = True
        self.main_app.scan_destination_screen.set_scan_result(pdf_path, page_count)
        self.main_app.show_screen('scan_destination')

    def _handle_finish_failed(self, message):
        self.view.show_status(message, is_error=True)

    def _handle_cancel(self):
        self.model.cancel()
        self.main_app.show_screen('homepage')

    # --- Public API for main_app ---

    def on_enter(self):
        print("Scanner screen entered")
        self._scan_completed = False
        self.model.start_session()
        self.view.reset()
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("Scanner screen leaving")
        self.timeout_timer.stop()
        if not self._scan_completed:
            self.model.cancel()

    def _on_timeout(self):
        print("⏰ Scanner screen timeout - returning to homepage")
        self.model.cancel()
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        if self.main_app.stacked_widget.currentWidget() is not self:
            return
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)
