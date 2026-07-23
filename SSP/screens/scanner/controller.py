# screens/scanner/controller.py

import os
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

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        self.view.back_button_clicked.connect(self._go_back)
        self.view.back_button_clicked.connect(self._reset_timeout)

        self.view.start_scan_clicked.connect(self._handle_start_scan)
        self.view.start_scan_clicked.connect(self._reset_timeout)

        self.model.scan_result.connect(self._handle_scan_result)

    def _handle_start_scan(self):
        self.view.show_status("Scanning...", is_error=False)
        self.model.start_scan()

    def _handle_scan_result(self, success, message):
        if success:
            self.view.show_status(message, is_error=False)
            print("Scanner screen: scan accepted")

            # --- DEV BYPASS: no real scanner backend yet, reuse test_pdfs ---
            from managers.usb_file_manager import USBFileManager

            test_folder = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', '..', '..', 'test_pdfs')
            )
            os.makedirs(test_folder, exist_ok=True)

            temp_manager = USBFileManager()
            pdf_files = temp_manager.scan_and_copy_pdf_files(test_folder)

            if pdf_files:
                print(f"[SIM] Scanner screen: loaded {len(pdf_files)} test PDF(s) from {test_folder}")
                self.main_app.file_browser_screen.set_source("scanner")
                self.main_app.file_browser_screen.load_pdf_files(pdf_files)
                self.main_app.show_screen('file_browser')
            else:
                self.view.show_status("No PDF files found in test folder.", is_error=True)
            # --- END DEV BYPASS ---
        else:
            self.view.show_status(message, is_error=True)

    def _go_back(self):
        self.main_app.show_screen('homepage')

    # --- Public API for main_app ---

    def on_enter(self):
        print("Scanner screen entered")
        self.view.show_status("")
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("Scanner screen leaving")
        self.timeout_timer.stop()

    def _on_timeout(self):
        print("⏰ Scanner screen timeout - returning to homepage")
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)