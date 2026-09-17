# screens/scan_destination/controller.py

import os
import shutil

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from .model import ScanDestinationModel
from .view import ScanDestinationScreenView


class ScanDestinationController(QWidget):
    """Manages the post-scan destination-choice screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = ScanDestinationModel()
        self.view = ScanDestinationScreenView()

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

        self.view.print_now_clicked.connect(self._handle_print_now)
        self.view.print_now_clicked.connect(self._reset_timeout)

        self.view.send_wifi_clicked.connect(self._handle_send_wifi)
        self.view.send_wifi_clicked.connect(self._reset_timeout)

        self.model.session_created.connect(self._handle_session_created)
        self.model.session_failed.connect(self._handle_session_failed)

    # --- Public API for main_app ---

    def set_scan_result(self, pdf_path: str, page_count: int):
        self.model.set_scan_result(pdf_path, page_count)
        self.view.set_summary(page_count)

    def _handle_print_now(self):
        pdf_data = self.model.get_pdf_data()
        selected_pages = self.model.get_selected_pages()
        self.main_app.printing_options_screen.set_pdf_data(pdf_data, selected_pages, "scanner")
        self.main_app.show_screen('printing_options')

    def _handle_send_wifi(self):
        self.view.set_busy(True)
        self.view.show_status("Creating your pickup code...", is_error=False)
        self.model.send_via_wifi()

    def _handle_session_created(self, session):
        self.view.set_busy(False)
        self._cleanup_pdf()
        self.main_app.scan_result_screen.set_session(session)
        self.main_app.show_screen('scan_result')

    def _handle_session_failed(self, message):
        self.view.set_busy(False)
        self.view.show_status(message, is_error=True)

    def _handle_cancel(self):
        self._cleanup_pdf()
        self.main_app.show_screen('homepage')

    def _cleanup_pdf(self):
        pdf_path = self.model.pdf_path
        if pdf_path and os.path.exists(pdf_path):
            try:
                shutil.rmtree(os.path.dirname(pdf_path), ignore_errors=True)
            except OSError:
                pass

    def on_enter(self):
        print("Scan destination screen entered")
        self.view.show_status("")
        self.view.set_busy(False)
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("Scan destination screen leaving")
        self.timeout_timer.stop()

    def _on_timeout(self):
        print("⏰ Scan destination screen timeout - returning to homepage")
        self._cleanup_pdf()
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        if self.main_app.stacked_widget.currentWidget() is not self:
            return
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)
