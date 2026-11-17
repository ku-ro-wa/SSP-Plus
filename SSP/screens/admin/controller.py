# screens/admin/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout

from config import get_config
from managers.inventory_edits import TOUCHSCREEN
from managers.payment_recovery import owed_payments, settle_in_cash, settle_with_voucher
from managers.printer_status import read_printer_status
from screens.voucher.model import VoucherModel

from .model import AdminModel
from .view import AdminScreenView


class AdminController(QWidget):
    """Manages the Admin screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = AdminModel()
        self.view = AdminScreenView(sim_mode=get_config().sim_mode)

        # Connect to database thread manager if available
        if hasattr(main_app, 'db_threader'):
            self._connect_to_database_thread_manager()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    # --- NEW PROPERTY TO FIX THE ERROR ---
    @property
    def db_manager(self):
        """Provides access to the model's database manager instance."""
        return self.model.db_manager
    # ------------------------------------

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller/Model ---
        self.view.back_clicked.connect(self._go_back)
        self.view.view_data_logs_clicked.connect(self._show_data_viewer)
        self.view.settings_clicked.connect(lambda: self.main_app.show_screen('settings'))
        self.view.reports_clicked.connect(lambda: self.main_app.show_screen('reports'))
        self.view.paper_decreased.connect(self.model.decrease_paper_count)
        self.view.paper_increased.connect(self.model.increase_paper_count)
        self.view.reset_paper_clicked.connect(self.model.reset_paper_count)
        self.view.coin_1_decreased.connect(self.model.decrease_coin_1_count)
        self.view.coin_1_increased.connect(self.model.increase_coin_1_count)
        self.view.coin_5_decreased.connect(self.model.decrease_coin_5_count)
        self.view.coin_5_increased.connect(self.model.increase_coin_5_count)
        self.view.reset_coins_clicked.connect(self.model.reset_coin_counts)
        self.view.empty_coins_clicked.connect(self.model.empty_coin_counts)
        self.view.collect_cash_clicked.connect(self._collect_cash)
        self.view.owed_payments_clicked.connect(self._review_owed_payments)
        self.view.update_cmyk_clicked.connect(self.model.update_cmyk_levels)
        self.view.reset_cmyk_clicked.connect(self.model.reset_cmyk_levels)
        self.view.refresh_cmyk_clicked.connect(self.model.refresh_cmyk_levels)

        # --- Model -> View ---
        self.model.paper_count_changed.connect(self.view.update_paper_count_display)
        self.model.coin_count_changed.connect(self.view.update_coin_count_display)
        self.model.cmyk_levels_changed.connect(self.view.update_cmyk_display)
        self.model.show_message.connect(self.view.show_message_box)

    def _collect_cash(self):
        """Confirm, then record the collection and zero the counts. Cancel changes nothing."""
        preview = self.model.get_collection_preview()
        if self.view.confirm_collect_cash(preview['items'], preview['total']):
            self.model.collect_cash()

    def _refresh_owed_payments(self):
        owed = owed_payments(self.model.db_manager)
        self.view.update_owed_payments(len(owed), sum(int(r['amount_owed']) for r in owed))

    def _review_owed_payments(self):
        """Settle Interrupted Payments one at a time (ADR 0011). A Voucher is shown
        on the voucher screen straight away, to the customer standing here; it
        then comes back to Kiosk Admin."""
        db = self.model.db_manager
        vouchers_enabled = bool(db.get_setting('vouchers_enabled', 1))
        for row in owed_payments(db):
            choice = self.view.ask_settle_owed(row, vouchers_enabled)
            if choice is None:
                break
            if choice == 'cash':
                settle_in_cash(db, row['id'], TOUCHSCREEN)
                continue
            try:
                voucher = settle_with_voucher(db, row['id'], TOUCHSCREEN)
            except Exception as e:
                print(f"❌ Could not issue the voucher for an owed payment: {e}")
                self.view.show_message_box(
                    "Voucher not issued",
                    f"The voucher couldn't be saved, so the payment is still owed. ({e})")
                break
            if voucher is None:
                continue  # settled meanwhile
            screen = self.main_app.voucher_screen
            screen.show_issued(voucher, reason=VoucherModel.INTERRUPTED,
                               on_continue=lambda: self.main_app.show_screen('admin'))
            self.main_app.show_screen('voucher')
            return
        self._refresh_owed_payments()

    def _connect_to_database_thread_manager(self):
        """Connect to database thread manager for real-time updates."""
        if hasattr(self.main_app, 'db_threader'):
            # Connect CMYK level updates from database thread
            self.main_app.db_threader.cmyk_levels_updated.connect(self._on_cmyk_levels_updated)
            print("Admin screen connected to database thread manager")

    def _on_cmyk_levels_updated(self, cmyk_data):
        """Handle CMYK levels updated from database thread."""
        print(f"Admin screen received CMYK update: {cmyk_data}")
        if cmyk_data:
            self.model.cmyk_levels_changed.emit(
                cmyk_data['cyan'],
                cmyk_data['magenta'],
                cmyk_data['yellow'],
                cmyk_data['black']
            )

    # --- Public API for main_app and other screens ---

    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Admin screen entered. Refreshing data.")
        self.model.load_paper_count()
        self.model.load_coin_counts()
        self.model.load_cmyk_levels()
        self.view.update_qr_reader_status(self.main_app.qr_reader_status_text())
        self.view.update_printer_status(*read_printer_status())
        self.view.update_unresolved_errors(self.model.db_manager.count_unresolved_errors())
        self._refresh_owed_payments()
        # Debug: Show what paper count is loaded
        print(f"Admin on_enter: Paper count loaded as {self.model.paper_count}")
        print(f"Admin on_enter: Fresh DB value: {self.model.db_manager.get_setting('paper_count', default=100)}")

    def refresh_cmyk_levels(self):
        """Manually refresh CMYK levels from database."""
        print("Manually refreshing CMYK levels...")
        self.model.load_cmyk_levels()

    def get_paper_count(self) -> int:
        """Returns the current paper count from the model."""
        # Always get fresh data from database to ensure consistency
        fresh_count = self.model.db_manager.get_setting('paper_count', default=100)
        print(f"Admin get_paper_count: Returning {fresh_count} (model has {self.model.paper_count})")
        return fresh_count

    def check_paper_availability(self, pages_to_print: int) -> bool:
        """
        Public method to check paper availability without decrementing.
        """
        return self.model.check_paper_availability(pages_to_print)

    def update_paper_count(self, pages_to_print: int) -> bool:
        """
        Public method for PaymentScreen to call. Delegates logic to the model.
        """
        return self.model.decrement_paper_count(pages_to_print)

    # --- Private navigation methods ---

    def _go_back(self):
        self.main_app.show_screen('idle')

    def _show_data_viewer(self):
        """Navigate to data viewer screen with error handling."""
        try:
            if hasattr(self.main_app, 'data_viewer_screen') and self.main_app.data_viewer_screen is not None:
                self.main_app.show_screen('data_viewer')
            else:
                print("❌ Data viewer screen is not available")
                self.view.show_message_box("Error", "Data viewer is not available. Please restart the application.")
        except Exception as e:
            print(f"❌ ERROR: Failed to show data viewer: {e}")
            self.view.show_message_box("Error", f"Failed to open data viewer: {str(e)}")
