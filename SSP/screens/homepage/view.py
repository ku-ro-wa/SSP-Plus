# screens/landing/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel, QStackedLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.theme import COLORS, FONT
from ui.widgets import Card, Header

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


class HomepageScreenView(QWidget):
    """The user interface for the Landing (upload method selection) screen. Contains no logic."""

    method_card_clicked = pyqtSignal(str)  # method_key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QStackedLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setStackingMode(QStackedLayout.StackAll)
        self.setLayout(main_layout)

        # Background
        self.background_label = QLabel()
        self._load_background_image()

        # Foreground
        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")

        outer_layout = QVBoxLayout(foreground_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        fg_layout = QVBoxLayout(content)
        fg_layout.setContentsMargins(120, 24, 120, 24)
        fg_layout.setSpacing(8)
        outer_layout.addWidget(content, 1)

        title = QLabel("Select Upload Method")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        subtitle = QLabel("Please select the desired file upload method or the scanning function.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_lg']}px;")

        disclaimer = QLabel("Disclaimer: This kiosk only accepts files in the PDF format.")
        disclaimer.setAlignment(Qt.AlignCenter)
        disclaimer.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: {FONT['size_sm']}px; font-weight: 600;")

        fg_layout.addStretch(1)
        fg_layout.addWidget(title)
        fg_layout.addSpacing(8)
        fg_layout.addWidget(subtitle)
        fg_layout.addWidget(disclaimer)
        fg_layout.addStretch(1)

        # Cards: 2x2 grid.
        self.usb_card = Card('usb', "USB", "Upload files via USB.", icon_name='usb')
        self.wifi_card = Card('wifi', "WiFi", 'Connect to the local network:\n"usc_printer_kiosk"', icon_name='wifi')
        self.email_card = Card('email', "Email", "Email address:\nprinter_kiosk@usc.edu.ph", icon_name='email')
        self.scanner_card = Card(
            'scanner', "Scanner", "Scan documents via the printer's built-in scanner.", icon_name='scanner'
        )

        for card in (self.usb_card, self.wifi_card, self.email_card, self.scanner_card):
            card.clicked.connect(self.method_card_clicked.emit)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(20)
        cards_grid.setVerticalSpacing(20)
        cards_grid.addWidget(self.usb_card, 0, 0)
        cards_grid.addWidget(self.wifi_card, 0, 1)
        cards_grid.addWidget(self.email_card, 1, 0)
        cards_grid.addWidget(self.scanner_card, 1, 1)

        grid_wrapper = QHBoxLayout()
        grid_wrapper.addStretch()
        grid_wrapper.addLayout(cards_grid)
        grid_wrapper.addStretch()
        fg_layout.addLayout(grid_wrapper)
        fg_layout.addStretch(2)

        main_layout.addWidget(self.background_label)
        main_layout.addWidget(foreground_widget)
        main_layout.setCurrentWidget(foreground_widget)

    def _load_background_image(self):
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'upload_method_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'")
            self.background_label.setStyleSheet("background-color: #ffffff;")
