# screens/data_viewer/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal

from managers.log_pages import ERROR_COLUMNS, TRANSACTION_COLUMNS
from ui.theme import COLORS, TABLE_QSS, TAB_QSS
from ui.widgets import BackButton, Header, SecondaryButton, nav_row


class DataViewerScreenView(QWidget):
    """The user interface for the Data Viewer Screen. Contains no logic."""
    back_clicked = pyqtSignal()
    refresh_transactions_clicked = pyqtSignal()
    refresh_cash_inventory_clicked = pyqtSignal()
    refresh_error_log_clicked = pyqtSignal()
    previous_transactions_clicked = pyqtSignal()
    next_transactions_clicked = pyqtSignal()
    previous_errors_clicked = pyqtSignal()
    next_errors_clicked = pyqtSignal()

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

    def _pager(self, previous_signal, next_signal):
        """Newer / 'Page n of m' / Older row. Returns (layout, label, newer, older)."""
        newer = SecondaryButton("Newer")
        newer.setMinimumHeight(44)
        newer.clicked.connect(previous_signal.emit)
        older = SecondaryButton("Older")
        older.setMinimumHeight(44)
        older.clicked.connect(next_signal.emit)
        label = QLabel("")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color: {COLORS['text']};")
        row = QHBoxLayout()
        row.addWidget(newer)
        row.addWidget(label, 1)
        row.addWidget(older)
        return row, label, newer, older

    @staticmethod
    def _show_page(label, newer, older, page, pages):
        label.setText(f"Page {page} of {pages}")
        newer.setEnabled(page > 1)
        older.setEnabled(page < pages)

    def create_transactions_tab(self):
        """Creates the transactions tab."""
        self.transactions_table = self._make_table()
        pager, self.transactions_page_label, self.newer_transactions_button, \
            self.older_transactions_button = self._pager(
                self.previous_transactions_clicked, self.next_transactions_clicked)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.transactions_table)
        layout.addLayout(pager)
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
        pager, self.errors_page_label, self.newer_errors_button, \
            self.older_errors_button = self._pager(self.previous_errors_clicked, self.next_errors_clicked)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.error_log_table)
        layout.addLayout(pager)
        return widget

    def update_transactions_table(self, transactions, page, pages):
        """Updates the transactions table: the Dashboard's /logs columns, after an ID."""
        table = self.transactions_table
        table.clear()
        headers = ["ID", *TRANSACTION_COLUMNS]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(transactions))

        for i, t in enumerate(transactions):
            cells = [
                t['id'], t['timestamp'], t['file_name'], t['source'] or '', t['pages'], t['copies'],
                t['color_mode'], f"₱{t['total_cost']:.2f}", f"₱{t['amount_paid']:.2f}",
                f"₱{t['change_given']:.2f}", t['status'],
            ]
            for col, value in enumerate(cells):
                table.setItem(i, col, self._item(value))

        self._fit_columns(table, stretch_column=headers.index("File"))
        self._show_page(self.transactions_page_label, self.newer_transactions_button,
                        self.older_transactions_button, page, pages)

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

    def update_error_log_table(self, errors, page, pages):
        """Updates the error log table: the Dashboard's /logs columns."""
        table = self.error_log_table
        table.clear()
        headers = list(ERROR_COLUMNS)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(errors))

        for i, error in enumerate(errors):
            cells = [error['timestamp'], error['error_type'], error['error_message'],
                     error['screen_name'], 'yes' if error['resolved'] else 'no']
            for col, value in enumerate(cells):
                table.setItem(i, col, self._item(value))

        self._fit_columns(table, stretch_column=headers.index("Message"))
        self._show_page(self.errors_page_label, self.newer_errors_button,
                        self.older_errors_button, page, pages)
