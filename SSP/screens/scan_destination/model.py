# screens/scan_destination/model.py
#
# Holds the composed scan PDF and offers the two ways it can leave the
# kiosk: printed immediately (photocopy) and/or sent via a Wi-Fi/OTP
# session that also covers email delivery (see managers/adapters/scan_adapter.py
# and webapp/routers/redeem.py for the phone-side email/download choice).
# Both can be selected together — confirm_selection() creates the Wi-Fi
# session immediately (it's free and untied to any payment) while leaving
# the print leg, if selected, for the caller to route into printing_options.

from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal

from config import get_config
from database.db_manager import DatabaseManager
from managers.adapters.scan_adapter import ScanAdapter
from managers.session_manager import SessionManager


class ScanDestinationModel(QObject):
    session_created = pyqtSignal(object)  # Session
    session_failed = pyqtSignal(str)
    ready_to_print = pyqtSignal()  # print-only selection, no session needed

    def __init__(self):
        super().__init__()
        config = get_config()
        self.db_manager = DatabaseManager()
        self.session_manager = SessionManager(self.db_manager)
        self.scan_adapter = ScanAdapter(self.session_manager, config.scan_upload_dir)

        self.pdf_path = None
        self.page_count = 0
        self.wants_print = False

    def set_scan_result(self, pdf_path: str, page_count: int):
        self.pdf_path = pdf_path
        self.page_count = page_count

    def get_pdf_data(self) -> dict:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return {'path': self.pdf_path, 'filename': f"Scan_{stamp}.pdf"}

    def get_selected_pages(self) -> list:
        return list(range(1, self.page_count + 1))

    def confirm_selection(self, selected_keys: set):
        self.wants_print = 'print' in selected_keys

        if 'send_wifi' in selected_keys:
            success, message, session = self.scan_adapter.handle_scan(self.pdf_path)
            if success:
                self.session_created.emit(session)
            else:
                self.session_failed.emit(message)
        else:
            self.ready_to_print.emit()
