# screens/scan_result/model.py

from PyQt5.QtCore import QObject


class ScanResultModel(QObject):
    """Holds the session created for a scanned document sent via Wi-Fi."""

    def __init__(self):
        super().__init__()
        self.session = None

    def set_session(self, session):
        self.session = session
