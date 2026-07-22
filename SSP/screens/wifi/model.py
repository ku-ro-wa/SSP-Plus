from PyQt5.QtCore import QObject, pyqtSignal


class WifiModel(QObject):
    """Handles data and logic for the WiFi upload screen."""
    otp_result = pyqtSignal(bool, str)  # (is_valid, message)

    def __init__(self):
        super().__init__()

    def validate_otp(self, otp_text):
        """
        Validates the entered OTP.

        TODO: Replace this stub with a real call into the session manager
        once Phase 3 (OTP + QR sessions) exists — see project_objectives.txt.
        For now, any 6-digit numeric code is accepted so the flow can be tested.
        """
        otp_text = otp_text.strip()

        if not otp_text:
            self.otp_result.emit(False, "Please enter a code.")
            return

        if not otp_text.isdigit() or len(otp_text) != 6:
            self.otp_result.emit(False, "Invalid code.")
            return

        print(f"[STUB] Accepting OTP '{otp_text}' — no real session backend yet")
        self.otp_result.emit(True, "Code accepted.")