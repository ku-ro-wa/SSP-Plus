# screens/wifi/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from managers.usb_file_manager import USBFileManager

from .model import WifiModel
from .view import WifiScreenView


class WifiController(QWidget):
    """Manages the WiFi upload screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = WifiModel()
        self.view = WifiScreenView()

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

        self.view.cancel_card_clicked.connect(self._cancel_upload)
        self.view.cancel_card_clicked.connect(self._reset_timeout)

        self.view.send_otp_clicked.connect(self._handle_send_otp)
        self.view.send_otp_clicked.connect(self._reset_timeout)

        self.model.otp_result.connect(self._handle_otp_result)

    def _cancel_upload(self):
        print("QR card clicked")
        # QR scan

    def _handle_send_otp(self, otp_text):
        self.model.validate_otp(otp_text)

    def _handle_otp_result(self, is_valid, message, files):
        if is_valid:
            self.view.show_status(message, is_error=False)
            print("WiFi screen: OTP accepted")

            temp_manager = USBFileManager()
            source_paths = [f['path'] for f in files]
            pdf_files = temp_manager.scan_and_copy_pdf_files_by_paths(source_paths)

            if pdf_files:
                self.main_app.file_browser_screen.set_source("wifi")
                self.main_app.file_browser_screen.load_pdf_files(pdf_files)
                self.main_app.show_screen('file_browser')
            else:
                self.view.show_status("Could not load the uploaded file(s).", is_error=True)
        else:
            self.view.show_status(message, is_error=True)


    def _go_back(self):
        self.main_app.show_screen('homepage')

    # --- Public API for main_app ---

    def on_enter(self):
        print("WiFi screen entered")
        self.view.clear_otp_input()
        self.view.show_status("")
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("WiFi screen leaving")
        self.timeout_timer.stop()

    def refresh_files(self):
        """Called by file_browser when the user wants to add another
        wifi-sourced document — send them back to enter a fresh code."""
        self.main_app.show_screen('wifi')

    def _on_timeout(self):
        print("⏰ WiFi screen timeout - returning to homepage")
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)