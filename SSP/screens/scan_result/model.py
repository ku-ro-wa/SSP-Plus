# screens/scan_result/model.py

from PyQt5.QtCore import QObject


class ScanResultModel(QObject):
    """Holds the session created for a scanned document's paid-for digital copy,
    plus whether a paid-for print follows (the print starts on thank_you)."""

    def __init__(self):
        super().__init__()
        self.session = None
        self.then_print = False

    def set_session(self, session, then_print=False):
        self.session = session
        self.then_print = then_print

    def has_pending_print(self) -> bool:
        return self.then_print
