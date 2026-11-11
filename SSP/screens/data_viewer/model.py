# screens/data_viewer/model.py

from PyQt5.QtCore import QObject, pyqtSignal
from database.db_manager import DatabaseManager
from managers.log_pages import PAGE_SIZE, page_count


class DataViewerModel(QObject):
    """Handles the data and business logic for the data viewer screen.

    Transactions and errors are read a page at a time with the same
    DatabaseManager methods and page size as the Dashboard's /logs (issue #131).
    """
    transactions_loaded = pyqtSignal(list, int, int)  # Emits rows, page, pages
    cash_inventory_loaded = pyqtSignal(list)    # Emits list of cash inventory
    error_log_loaded = pyqtSignal(list, int, int)     # Emits rows, page, pages
    show_message = pyqtSignal(str, str)         # Emits message title and text

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.transactions_page = 1
        self.errors_page = 1

    def _read_page(self, reader, page):
        """(rows, page, pages) for `page`, clamped to the last page that exists."""
        page = max(1, page)
        rows, total = reader(PAGE_SIZE, (page - 1) * PAGE_SIZE)
        pages = page_count(total)
        if page > pages:
            page = pages
            rows, _ = reader(PAGE_SIZE, (page - 1) * PAGE_SIZE)
        return rows, page, pages

    def load_transactions(self, page=None):
        """Loads one page of transaction history (the current page by default)."""
        try:
            rows, page, pages = self._read_page(
                self.db_manager.get_transaction_page, page or self.transactions_page)
            self.transactions_page = page
            self.transactions_loaded.emit(rows, page, pages)
        except Exception as e:
            print(f"❌ ERROR: Failed to load transactions: {e}")
            self.show_message.emit("Error", f"Failed to load transactions: {str(e)}")

    def next_transactions_page(self):
        self.load_transactions(self.transactions_page + 1)

    def previous_transactions_page(self):
        self.load_transactions(self.transactions_page - 1)

    def load_cash_inventory(self):
        """Loads cash inventory from the database."""
        try:
            print("🔄 Loading cash inventory from database...")
            inventory = self.db_manager.get_cash_inventory()
            print(f"✅ Loaded {len(inventory)} cash inventory items")
            self.cash_inventory_loaded.emit(inventory)
        except Exception as e:
            print(f"❌ ERROR: Failed to load cash inventory: {e}")
            self.show_message.emit("Error", f"Failed to load cash inventory: {str(e)}")

    def load_error_log(self, page=None):
        """Loads one page of the error log (the current page by default)."""
        try:
            rows, page, pages = self._read_page(self.db_manager.get_error_page, page or self.errors_page)
            self.errors_page = page
            self.error_log_loaded.emit(rows, page, pages)
        except Exception as e:
            print(f"❌ ERROR: Failed to load error log: {e}")
            self.show_message.emit("Error", f"Failed to load error log: {str(e)}")

    def next_errors_page(self):
        self.load_error_log(self.errors_page + 1)

    def previous_errors_page(self):
        self.load_error_log(self.errors_page - 1)

    def refresh_all_data(self):
        """Refreshes all data types, from the newest page."""
        self.load_transactions(1)
        self.load_cash_inventory()
        self.load_error_log(1)
