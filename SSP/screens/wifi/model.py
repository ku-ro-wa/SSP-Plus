from PyQt5.QtCore import QObject, pyqtSignal

from database.db_manager import DatabaseManager
from managers.pickup_code_lockout import PickupCodeLockout, locked_message
from managers.session_manager import SessionManager


class WifiModel(QObject):
    """Handles data and logic for the WiFi upload screen."""
    otp_result = pyqtSignal(bool, str, list)  # (is_valid, message, files)

    def __init__(self, db_manager=None, lockout=None):
        super().__init__()
        self.db_manager = db_manager or DatabaseManager()
        self.session_manager = SessionManager(self.db_manager)
        self.lockout = lockout or PickupCodeLockout(self.db_manager)

    def lock_remaining(self):
        """Seconds the typed-code lockout has left (0 when not locked)."""
        return self.lockout.remaining()

    def validate_otp(self, otp_text):
        """Validates the entered OTP against a real pending wifi session."""
        otp_text = otp_text.strip()

        # Checked before the format so even the right code is refused while
        # locked, and no guess is looked up (or counted) during a lockout.
        remaining = self.lock_remaining()
        if remaining:
            self.otp_result.emit(False, locked_message(remaining), [])
            return

        if not otp_text:
            self.otp_result.emit(False, "Please enter a code.", [])
            return

        if not otp_text.isdigit() or len(otp_text) != 6:
            self.otp_result.emit(False, "Invalid code.", [])
            return

        result = self.lockout.verify(self.session_manager, "wifi", otp_text)
        self.otp_result.emit(result.success, result.message, result.files or [])
