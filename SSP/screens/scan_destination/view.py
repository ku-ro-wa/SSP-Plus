# screens/scan_destination/view.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Card, Header, StatusBanner


class ScanDestinationScreenView(QWidget):
    """The user interface for choosing what happens to a finished scan. Contains no logic."""
    cancel_clicked = pyqtSignal()
    print_now_clicked = pyqtSignal()
    send_wifi_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(content)
        body_layout.setContentsMargins(60, 20, 60, 24)
        body_layout.setSpacing(10)
        outer_layout.addWidget(content, 1)

        self.cancel_button = BackButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_clicked.emit)

        body_layout.addStretch(1)

        title = QLabel("Scan Complete")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        body_layout.addWidget(title)
        body_layout.addSpacing(6)
        body_layout.addWidget(self.summary_label)
        body_layout.addSpacing(20)

        self.print_card = Card('print', "Print Now", "Print this scan right away (photocopy).")
        self.print_card.clicked.connect(lambda _key: self.print_now_clicked.emit())

        self.send_card = Card(
            'wifi', "Send via Wi-Fi", "Get a code to download or email this scan from your phone.",
            icon_name='wifi',
        )
        self.send_card.clicked.connect(lambda _key: self.send_wifi_clicked.emit())

        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)
        cards_row.addStretch()
        cards_row.addWidget(self.print_card)
        cards_row.addWidget(self.send_card)
        cards_row.addStretch()
        body_layout.addLayout(cards_row)

        body_layout.addSpacing(16)

        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        body_layout.addStretch(2)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.cancel_button, 0, Qt.AlignLeft)
        nav_row.addStretch()
        body_layout.addLayout(nav_row)

    def set_summary(self, page_count: int):
        if page_count == 1:
            self.summary_label.setText("1 page scanned — choose what to do with it.")
        else:
            self.summary_label.setText(f"{page_count} pages scanned — choose what to do with them.")

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def set_busy(self, busy: bool):
        self.print_card.setEnabled(not busy)
        self.send_card.setEnabled(not busy)
