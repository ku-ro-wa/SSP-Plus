# screens/scan_destination/model.py
#
# Holds the composed scan PDF and what the customer wants done with it:
# printed (photocopy) and/or a digital copy (download or email, via a
# Wi-Fi/OTP session). Nothing is carried out here: payment comes first.
# The controller routes the selection (print only -> printing_options,
# print + digital -> printing_options with the digital fee added, digital
# only -> payment), and the payment model creates the session only once the
# payment succeeds (see managers/adapters/scan_adapter.py and
# webapp/routers/redeem.py for the phone-side choice).

from datetime import datetime

from PyQt5.QtCore import QObject

from database.db_manager import DatabaseManager
from managers.digital_fee import get_digital_fee


class ScanDestinationModel(QObject):
    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.pdf_path = None
        self.page_count = 0

    def set_scan_result(self, pdf_path: str, page_count: int):
        self.pdf_path = pdf_path
        self.page_count = page_count

    def get_pdf_data(self) -> dict:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return {'path': self.pdf_path, 'filename': f"Scan_{stamp}.pdf"}

    def get_selected_pages(self) -> list:
        return list(range(1, self.page_count + 1))

    def get_digital_fee(self) -> int:
        return get_digital_fee(self.db_manager)

    def get_digital_only_payment_data(self) -> dict:
        """Payment data for a digital copy with no printing: just the flat fee."""
        fee = self.get_digital_fee()
        return {
            'pdf_data': self.get_pdf_data(),
            'selected_pages': self.get_selected_pages(),
            'copies': 0,
            'color_mode': 'N/A',
            'total_cost': fee,
            'print_job': False,
            'digital_copy': {'fee': fee},
            'source': 'scanner',
        }
