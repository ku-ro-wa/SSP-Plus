# managers/scanner_thread.py
#
# Thin QThread wrapper so a (possibly slow, real-hardware) ScannerManager
# call doesn't block the UI thread. Generalized to run any bound
# ScannerManager method rather than duplicating per-operation logic, since
# scan_page/rescan_last/finish all follow the same "run it, report success
# or failure" shape. Mirrors the PrinterManager/PrinterThread split.

from PyQt5.QtCore import QThread, pyqtSignal

from managers.scanner import ScannerError


class ScannerThread(QThread):
    operation_succeeded = pyqtSignal(dict)
    operation_failed = pyqtSignal(str)

    def __init__(self, operation):
        """`operation` is a bound ScannerManager method taking no args and
        returning a dict, e.g. manager.scan_page."""
        super().__init__()
        self._operation = operation

    def run(self):
        try:
            result = self._operation()
            self.operation_succeeded.emit(result)
        except ScannerError as e:
            self.operation_failed.emit(str(e))
        except Exception as e:
            self.operation_failed.emit(f"Unexpected scanner error: {e}")
