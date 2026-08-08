# screens/scanner/view.py

import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedLayout
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Card, Header, StatusBanner


def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


class ScannerScreenView(QWidget):
    """The user interface for the Scanner screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    start_scan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QStackedLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setStackingMode(QStackedLayout.StackAll)
        self.setLayout(main_layout)

        self.background_label = QLabel()
        self._load_background_image()

        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")

        outer_layout = QVBoxLayout(foreground_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        body_layout = QVBoxLayout(content)
        body_layout.setContentsMargins(60, 20, 60, 24)
        body_layout.setSpacing(10)
        outer_layout.addWidget(content, 1)

        top_row = QHBoxLayout()
        self.back_button = BackButton()
        self.back_button.clicked.connect(self.back_button_clicked.emit)
        top_row.addWidget(self.back_button)
        top_row.addStretch()
        body_layout.addLayout(top_row)

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

        main_layout.addWidget(self.background_label)
        main_layout.addWidget(foreground_widget)
        main_layout.setCurrentWidget(foreground_widget)

    def _load_background_image(self):
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'scanner_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'")
            self.background_label.setStyleSheet("background-color: #ffffff;")

    def show_status(self, message, is_error=True):
        # While a scan is in progress, disable the card so it can't be re-tapped mid-flight.
        self.scan_card.setEnabled(message != "Scanning...")
        self.status_banner.show_message(message, variant="error" if is_error else "success")
