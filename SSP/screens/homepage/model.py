from PyQt5.QtCore import QObject, pyqtSignal

class HomepageModel(QObject):
    """Handles data and logic for the landing (upload method selection) screen."""
    method_selected = pyqtSignal(str)  # Emits the selected method key

    def __init__(self):
        super().__init__()

    def select_method(self, method):
        """Records the selected upload method and emits signal."""
        print(f"Landing screen: method selected -> {method}")
        self.method_selected.emit(method)