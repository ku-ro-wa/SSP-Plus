# screens/email/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from config import get_config

from .model import EmailModel
from .view import EmailScreenView


class EmailController(QWidget):
    """Manages the Email upload screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = EmailModel()
        self.view = EmailScreenView()

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

    def _handle_send_otp(self, otp_text):
        self.model.validate_otp(otp_text)

    def _handle_otp_result(self, is_valid, message, files):
        if is_valid:
            self.view.show_status(message, is_error=False)
            print("Email screen: OTP accepted")

            if not self.main_app.open_session_files("email", files):
                self.view.show_status("Could not load the uploaded file(s).", is_error=True)
        else:
            self.view.show_status(message, is_error=True)

    def show_qr_message(self, message):
        """A message about a QR read (from main_app), shown like a typed-code error."""
        self.view.show_status(message, is_error=True)

    def _go_back(self):
        self.main_app.show_screen('homepage')

    # --- Public API for main_app ---

    def on_enter(self):
        print("Email screen entered")
        self.view.clear_otp_input()
        self.view.show_status("")
        try:
            config = get_config()
            self.view.set_email_hint(config.email_user, config.email_subject_keyword)
        except Exception as e:
            print(f"Could not resolve email intake hint: {e}")
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("Email screen leaving")
        self.timeout_timer.stop()

    def refresh_files(self):
        """Called by file_browser when the user wants to add another
        email-sourced document — send them back to enter a fresh code."""
        self.main_app.show_screen('email')

    def _on_timeout(self):
        print("⏰ Email screen timeout - returning to homepage")
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        if self.main_app.stacked_widget.currentWidget() is not self:
            return
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)

    def _cancel_upload(self):
        print("QR card clicked")
