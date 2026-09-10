# screens/scanner/view.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Card, Header, StatusBanner


class ScannerScreenView(QWidget):
    """The user interface for the Scanner screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    start_scan_clicked = pyqtSignal()

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

        self.back_button = BackButton("Back to Input Selection")
        self.back_button.clicked.connect(self.back_button_clicked.emit)

        body_layout.addStretch(1)

        guide_title = QLabel("Usage Guide")
        guide_title.setAlignment(Qt.AlignCenter)
        guide_title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        guide_text = QLabel(
            '1. Place your document face-down on the scanner glass.<br><br>'
            '2. Press "Start Scan" below. Your document will be scanned and prepared for printing.'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        body_layout.addWidget(guide_title)
        body_layout.addSpacing(8)
        body_layout.addWidget(guide_text)
        body_layout.addSpacing(24)

        # Single Start Scan card
        self.scan_card = Card('scan', "Start Scan", "Tap to begin scanning your document.", icon_name='scanner')
        self.scan_card.clicked.connect(lambda _key: self.start_scan_clicked.emit())

        cards_row = QHBoxLayout()
        cards_row.addStretch()
        cards_row.addWidget(self.scan_card)
        cards_row.addStretch()
        body_layout.addLayout(cards_row)

        body_layout.addSpacing(16)

        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        body_layout.addStretch(2)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.back_button, 0, Qt.AlignLeft)
        nav_row.addStretch()
        body_layout.addLayout(nav_row)

    def show_status(self, message, is_error=True):
        # While a scan is in progress, disable the card so it can't be re-tapped mid-flight.
        self.scan_card.setEnabled(message != "Scanning...")
        self.status_banner.show_message(message, variant="error" if is_error else "success")
