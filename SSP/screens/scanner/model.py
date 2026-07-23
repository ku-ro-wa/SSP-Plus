from PyQt5.QtCore import QObject, pyqtSignal


class ScannerModel(QObject):
    """Handles data and logic for the Scanner screen."""
    scan_result = pyqtSignal(bool, str)  # (success, message)

    def __init__(self):
        super().__init__()
        self.scanning = False

    def start_scan(self):
        """
        Triggers a scan.

        TODO: Replace this stub with a real call into ScannerInterface /
        sane-airscan once Phase 6 (Scanner Module) exists — see
        project_objectives.txt. For now this just reports success so the
        flow can be tested; the controller pulls test PDFs as a stand-in
        for actual scanned output.
        """
        if self.scanning:
            self.scan_result.emit(False, "A scan is already in progress.")
            return

        self.scanning = True
        print("[STUB] Scan started — no real scanner backend yet")
        self.scan_result.emit(True, "Scan complete.")
        self.scanning = False