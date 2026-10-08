from PyQt5.QtCore import QObject, pyqtSignal

from database.db_manager import DatabaseManager
from managers.payment_algorithm_manager import PaymentAlgorithmManager


class HomepageModel(QObject):
    """Handles data and logic for the landing (upload method selection) screen."""
    method_selected = pyqtSignal(str)  # Emits the selected method key

    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()

    def is_change_low(self):
        """Fresh each call (coin inventory and settings both change at runtime)."""
        return PaymentAlgorithmManager(self.db_manager).is_change_low()

    def select_method(self, method):
        """Records the selected upload method and emits signal."""
        print(f"Landing screen: method selected -> {method}")
        self.method_selected.emit(method)
