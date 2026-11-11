# screens/data_viewer/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal

from managers.admin_actions import where_text
from ui.theme import COLORS, TABLE_QSS, TAB_QSS
from ui.widgets import BackButton, Header, SecondaryButton, nav_row


class DataViewerScreenView(QWidget):
    """The user interface for the Data Viewer Screen. Contains no logic."""
    back_clicked = pyqtSignal()
    refresh_transactions_clicked = pyqtSignal()
    refresh_cash_inventory_clicked = pyqtSignal()
    refresh_error_log_clicked = pyqtSignal()
    refresh_admin_actions_clicked = pyqtSignal()
    previous_actions_clicked = pyqtSignal()
    next_actions_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface components."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(30, 20, 30, 20)
        body_layout.setSpacing(16)
        outer_layout.addWidget(body, 1)

        # Tab widget with the three data tables.
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(TAB_QSS)
        self.tab_widget.addTab(self.create_transactions_tab(), "Transactions")
        self.tab_widget.addTab(self.create_cash_inventory_tab(), "Cash Inventory")
        self.tab_widget.addTab(self.create_error_log_tab(), "Error Log")
        self.tab_widget.addTab(self.create_admin_actions_tab(), "Admin Actions")
        body_layout.addWidget(self.tab_widget, 1)

        # Bottom navigation row.
        self.back_button = BackButton("Back to Admin")
        self.back_button.setMinimumHeight(44)
        self.back_button.clicked.connect(self.back_clicked.emit)

        self.refresh_data_button = SecondaryButton("Refresh Data")
        self.refresh_data_button.setMinimumHeight(44)
        self.refresh_data_button.clicked.connect(self._on_refresh_clicked)

        body_layout.addLayout(nav_row(self.back_button, self.refresh_data_button))

    def _on_refresh_clicked(self):
        """Handle refresh button click based on current tab."""
        current_index = self.tab_widget.currentIndex()
        if current_index == 0:  # Transactions
            self.refresh_transactions_clicked.emit()
        elif current_index == 1:  # Cash Inventory
            self.refresh_cash_inventory_clicked.emit()
        elif current_index == 2:  # Error Log
            self.refresh_error_log_clicked.emit()
        elif current_index == 3:  # Admin Actions
            self.refresh_admin_actions_clicked.emit()

    def _make_table(self):
        table = QTableWidget()
        table.setStyleSheet(TABLE_QSS)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.ElideNone)
        # Rows grow to fit wrapped text, and re-fit whenever a column width changes.
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        return table

    @staticmethod
    def _fit_columns(table, stretch_column):
        """Short columns size to their content; the long-text column takes the rest
        and wraps, so messages and file names are never cut off."""
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(table.columnCount()):
            mode = QHeaderView.Stretch if col == stretch_column else QHeaderView.ResizeToContents
            header.setSectionResizeMode(col, mode)

    @staticmethod
    def _item(text):
        """Table cell that also shows its full text as a tooltip."""
        text = str(text)
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        return item

    def create_transactions_tab(self):
        """Creates the transactions tab."""
        self.transactions_table = self._make_table()

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.transactions_table)
        return widget

    def create_cash_inventory_tab(self):
        """Creates the cash inventory tab."""
        self.cash_inventory_table = self._make_table()

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.cash_inventory_table)
        return widget

    def create_error_log_tab(self):
        """Creates the error log tab."""
        self.error_log_table = self._make_table()

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.error_log_table)
        return widget

    def create_admin_actions_tab(self):
        """Creates the admin actions tab: the audit trail, newest first, paged."""
        self.admin_actions_table = self._make_table()

        self.previous_actions_button = SecondaryButton("Newer")
        self.previous_actions_button.setMinimumHeight(44)
        self.previous_actions_button.clicked.connect(self.previous_actions_clicked.emit)
        self.next_actions_button = SecondaryButton("Older")
        self.next_actions_button.setMinimumHeight(44)
        self.next_actions_button.clicked.connect(self.next_actions_clicked.emit)
        self.actions_page_label = QLabel("")
        self.actions_page_label.setAlignment(Qt.AlignCenter)
        self.actions_page_label.setStyleSheet(f"color: {COLORS['text']};")

        pager = QHBoxLayout()
        pager.addWidget(self.previous_actions_button)
        pager.addWidget(self.actions_page_label, 1)
        pager.addWidget(self.next_actions_button)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.admin_actions_table)
        layout.addLayout(pager)
        return widget

    def update_admin_actions_table(self, actions, page, pages):
        """Updates the admin actions table; same columns as the Dashboard's /logs."""
        self.admin_actions_table.clear()
        self.admin_actions_table.setColumnCount(6)
        self.admin_actions_table.setHorizontalHeaderLabels(["Time", "Who", "Where", "Action", "Old", "New"])
        self.admin_actions_table.setRowCount(len(actions))

        for i, action in enumerate(actions):
            self.admin_actions_table.setItem(i, 0, self._item(action['timestamp']))
            self.admin_actions_table.setItem(i, 1, self._item(action['actor']))
            self.admin_actions_table.setItem(i, 2, self._item(where_text(action)))
            self.admin_actions_table.setItem(i, 3, self._item(action['action']))
            self.admin_actions_table.setItem(i, 4, self._item(action['old_value'] or ''))
            self.admin_actions_table.setItem(i, 5, self._item(action['new_value'] or ''))

        self._fit_columns(self.admin_actions_table, stretch_column=5)
        self.actions_page_label.setText(f"Page {page} of {pages}")
        self.previous_actions_button.setEnabled(page > 1)
        self.next_actions_button.setEnabled(page < pages)

    def update_transactions_table(self, transactions):
        """Updates the transactions table with new data."""
        self.transactions_table.clear()
        self.transactions_table.setColumnCount(9)
        self.transactions_table.setHorizontalHeaderLabels([
            "ID", "Date/Time", "File Name", "Pages", "Copies",
            "Color Mode", "Total Cost", "Amount Paid", "Status"
        ])
        self.transactions_table.setRowCount(len(transactions))

        for i, trans in enumerate(transactions):
            self.transactions_table.setItem(i, 0, self._item(str(trans['id'])))
            self.transactions_table.setItem(i, 1, self._item(str(trans['timestamp'])))
            self.transactions_table.setItem(i, 2, self._item(trans['file_name']))
            self.transactions_table.setItem(i, 3, self._item(str(trans['pages'])))
            self.transactions_table.setItem(i, 4, self._item(str(trans['copies'])))
            self.transactions_table.setItem(i, 5, self._item(trans['color_mode']))
            self.transactions_table.setItem(i, 6, self._item(f"₱{trans['total_cost']:.2f}"))
            self.transactions_table.setItem(i, 7, self._item(f"₱{trans['amount_paid']:.2f}"))
            self.transactions_table.setItem(i, 8, self._item(trans['status']))

        self._fit_columns(self.transactions_table, stretch_column=2)

    def update_cash_inventory_table(self, inventory):
        """Updates the cash inventory table with new data."""
        self.cash_inventory_table.clear()
        self.cash_inventory_table.setColumnCount(4)
        self.cash_inventory_table.setHorizontalHeaderLabels(["Denomination", "Count", "Type", "Last Updated"])
        self.cash_inventory_table.setRowCount(len(inventory))

        for i, item in enumerate(inventory):
            self.cash_inventory_table.setItem(i, 0, self._item(f"₱{item['denomination']}"))
            self.cash_inventory_table.setItem(i, 1, self._item(str(item['count'])))
            self.cash_inventory_table.setItem(i, 2, self._item(item['type']))
            self.cash_inventory_table.setItem(i, 3, self._item(str(item['last_updated'])))

        self._fit_columns(self.cash_inventory_table, stretch_column=3)

    def update_error_log_table(self, errors):
        """Updates the error log table with new data."""
        self.error_log_table.clear()
        self.error_log_table.setColumnCount(4)
        self.error_log_table.setHorizontalHeaderLabels(["Date/Time", "Error Type", "Error Message", "Screen"])
        self.error_log_table.setRowCount(len(errors))

        for i, error in enumerate(errors):
            self.error_log_table.setItem(i, 0, self._item(str(error['timestamp'])))
            self.error_log_table.setItem(i, 1, self._item(error['error_type']))
            self.error_log_table.setItem(i, 2, self._item(error['error_message']))
            self.error_log_table.setItem(i, 3, self._item(error['screen_name']))

        self._fit_columns(self.error_log_table, stretch_column=2)
