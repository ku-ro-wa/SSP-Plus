from PyQt5.QtCore import QObject, pyqtSignal

from database.db_manager import DatabaseManager
from managers.session_manager import SessionManager


class WifiModel(QObject):
    """Handles data and logic for the WiFi upload screen."""
    otp_result = pyqtSignal(bool, str, list)  # (is_valid, message, files)

    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.session_manager = SessionManager(self.db_manager)

    def validate_otp(self, otp_text):
        """Validates the entered OTP against a real pending wifi session."""
        otp_text = otp_text.strip()

        if not otp_text:
            self.otp_result.emit(False, "Please enter a code.", [])
            return

        if not otp_text.isdigit() or len(otp_text) != 6:
            self.otp_result.emit(False, "Invalid code.", [])
            return

        success, message, files = self.session_manager.verify_otp_for_source("wifi", otp_text)
        self.otp_result.emit(success, message, files or [])
