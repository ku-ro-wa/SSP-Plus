# screens/scan_result/model.py

from PyQt5.QtCore import QObject


class ScanResultModel(QObject):
    """Holds the session created for a scanned document sent via Wi-Fi, plus
    an optional pending print leg when Print Now was also selected alongside
    it on scan_destination."""

    def __init__(self):
        super().__init__()
        self.session = None
        self.pending_print = None  # None, or {'pdf_data': ..., 'selected_pages': ...}

    def set_session(self, session, pending_print=None):
        self.session = session
        self.pending_print = pending_print

    def has_pending_print(self) -> bool:
        return self.pending_print is not None
