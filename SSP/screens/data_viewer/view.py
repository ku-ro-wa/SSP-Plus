# screens/data_viewer/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import pyqtSignal

from ui.theme import COLORS, TABLE_QSS, TAB_QSS
from ui.widgets import BackButton, Header, SecondaryButton


class DataViewerScreenView(QWidget):
    """The user interface for the Data Viewer Screen. Contains no logic."""
    back_clicked = pyqtSignal()
    refresh_transactions_clicked = pyqtSignal()
    refresh_cash_inventory_clicked = pyqtSignal()
    refresh_error_log_clicked = pyqtSignal()

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
        body_layout.addWidget(self.tab_widget, 1)

        # Bottom navigation row.
        self.back_button = BackButton("Back to Admin")
        self.back_button.setMinimumHeight(44)
        self.back_button.clicked.connect(self.back_clicked.emit)

        self.refresh_data_button = SecondaryButton("Refresh Data")
        self.refresh_data_button.setMinimumHeight(44)
        self.refresh_data_button.clicked.connect(self._on_refresh_clicked)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.back_button, 0)
        nav_row.addStretch()
        nav_row.addWidget(self.refresh_data_button, 0)
        body_layout.addLayout(nav_row)

    def _on_refresh_clicked(self):
        """Handle refresh button click based on current tab."""
        current_index = self.tab_widget.currentIndex()
        if current_index == 0:  # Transactions
            self.refresh_transactions_clicked.emit()
        elif current_index == 1:  # Cash Inventory
            self.refresh_cash_inventory_clicked.emit()
        elif current_index == 2:  # Error Log
            self.refresh_error_log_clicked.emit()

    def _make_table(self):
        table = QTableWidget()
        table.setStyleSheet(TABLE_QSS)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        return table

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
            self.transactions_table.setItem(i, 0, QTableWidgetItem(str(trans['id'])))
            self.transactions_table.setItem(i, 1, QTableWidgetItem(str(trans['timestamp'])))
            self.transactions_table.setItem(i, 2, QTableWidgetItem(trans['file_name']))
            self.transactions_table.setItem(i, 3, QTableWidgetItem(str(trans['pages'])))
            self.transactions_table.setItem(i, 4, QTableWidgetItem(str(trans['copies'])))
            self.transactions_table.setItem(i, 5, QTableWidgetItem(trans['color_mode']))
            self.transactions_table.setItem(i, 6, QTableWidgetItem(f"₱{trans['total_cost']:.2f}"))
            self.transactions_table.setItem(i, 7, QTableWidgetItem(f"₱{trans['amount_paid']:.2f}"))
            self.transactions_table.setItem(i, 8, QTableWidgetItem(trans['status']))

        header = self.transactions_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(9):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

    def update_cash_inventory_table(self, inventory):
        """Updates the cash inventory table with new data."""
        self.cash_inventory_table.clear()
        self.cash_inventory_table.setColumnCount(4)
        self.cash_inventory_table.setHorizontalHeaderLabels(["Denomination", "Count", "Type", "Last Updated"])
        self.cash_inventory_table.setRowCount(len(inventory))

        for i, item in enumerate(inventory):
            self.cash_inventory_table.setItem(i, 0, QTableWidgetItem(f"₱{item['denomination']}"))
            self.cash_inventory_table.setItem(i, 1, QTableWidgetItem(str(item['count'])))
            self.cash_inventory_table.setItem(i, 2, QTableWidgetItem(item['type']))
            self.cash_inventory_table.setItem(i, 3, QTableWidgetItem(str(item['last_updated'])))

        header = self.cash_inventory_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

    def update_error_log_table(self, errors):
        """Updates the error log table with new data."""
        self.error_log_table.clear()
        self.error_log_table.setColumnCount(4)
        self.error_log_table.setHorizontalHeaderLabels(["Date/Time", "Error Type", "Error Message", "Screen"])
        self.error_log_table.setRowCount(len(errors))

        for i, error in enumerate(errors):
            self.error_log_table.setItem(i, 0, QTableWidgetItem(str(error['timestamp'])))
            self.error_log_table.setItem(i, 1, QTableWidgetItem(error['error_type']))
            self.error_log_table.setItem(i, 2, QTableWidgetItem(error['error_message']))
            self.error_log_table.setItem(i, 3, QTableWidgetItem(error['screen_name']))

        header = self.error_log_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
