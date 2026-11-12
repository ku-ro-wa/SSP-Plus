# screens/data_viewer/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout, QMessageBox

from .model import DataViewerModel
from .view import DataViewerScreenView


class DataViewerController(QWidget):
    """Manages the Data Viewer screen's logic and UI."""

    def __init__(self, main_app, db_manager, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        # Add error handling for database manager
        if db_manager is None:
            print("❌ ERROR: Database manager is None in DataViewerController")
            raise ValueError("Database manager cannot be None")

        try:
            self.model = DataViewerModel(db_manager)
            print("✅ DataViewerModel initialized successfully")
        except Exception as e:
            print(f"❌ ERROR: Failed to initialize DataViewerModel: {e}")
            raise

        self.view = DataViewerScreenView()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller ---
        self.view.back_clicked.connect(self._go_back)
        self.view.refresh_transactions_clicked.connect(lambda: self.model.load_transactions())
        self.view.refresh_cash_inventory_clicked.connect(self.model.load_cash_inventory)
        self.view.refresh_error_log_clicked.connect(lambda: self.model.load_error_log())
        self.view.previous_transactions_clicked.connect(self.model.previous_transactions_page)
        self.view.next_transactions_clicked.connect(self.model.next_transactions_page)
        self.view.previous_errors_clicked.connect(self.model.previous_errors_page)
        self.view.next_errors_clicked.connect(self.model.next_errors_page)
        self.view.refresh_admin_actions_clicked.connect(lambda: self.model.load_admin_actions(1))
        self.view.previous_actions_clicked.connect(self.model.previous_actions_page)
        self.view.next_actions_clicked.connect(self.model.next_actions_page)

        # --- Model -> View ---
        self.model.transactions_loaded.connect(self.view.update_transactions_table)
        self.model.cash_inventory_loaded.connect(self.view.update_cash_inventory_table)
        self.model.error_log_loaded.connect(self.view.update_error_log_table)
        self.model.admin_actions_loaded.connect(self.view.update_admin_actions_table)
        self.model.show_message.connect(self._show_message)

    def _go_back(self):
        """Navigates back to the admin screen."""
        self.main_app.show_screen('admin')

    def _show_message(self, title, text):
        """Shows a message to the user."""
        QMessageBox.warning(self, title, text)

    # --- Public API for main_app ---

    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Data viewer screen entered. Loading all data.")
        try:
            self.model.refresh_all_data()
            print("✅ Data viewer data loaded successfully")
        except Exception as e:
            print(f"❌ ERROR: Failed to load data in data viewer: {e}")
            self._show_message("Error", f"Failed to load data: {str(e)}")

    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("Data viewer screen left.")
