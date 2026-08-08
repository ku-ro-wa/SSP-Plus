# screens/wifi/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QStackedLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QIntValidator

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Card, Header, PrimaryButton, StatusBanner


def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


class WifiScreenView(QWidget):
    """The user interface for the WiFi Upload screen. Contains no logic."""
    cancel_card_clicked = pyqtSignal()
    back_button_clicked = pyqtSignal()
    send_otp_clicked = pyqtSignal(str)  # otp_text

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
            '1. Connect to the local WiFi network "<b>usc_printer_kiosk</b>".<br><br>'
            '2. Scan the provided QR code or input the provided OTP to proceed to the printing configuration.'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        body_layout.addWidget(guide_title)
        body_layout.addSpacing(8)
        body_layout.addWidget(guide_text)
        body_layout.addSpacing(24)

        # QR Code Scan / Enter Code cards
        self.cancel_card = Card('qr', "QR Code Scan", "Scan QR code to access files.", icon_name='qr-code')
        self.cancel_card.clicked.connect(lambda _key: self.cancel_card_clicked.emit())

        otp_row_widget = QWidget()
        otp_row = QHBoxLayout(otp_row_widget)
        otp_row.setContentsMargins(0, 0, 0, 0)
        otp_row.setSpacing(6)

        self.otp_input = QLineEdit()
        self.otp_input.setPlaceholderText("6-digit code")
        self.otp_input.setMaxLength(6)
        self.otp_input.setValidator(QIntValidator(0, 999999))
        self.otp_input.setAlignment(Qt.AlignCenter)
        self.otp_input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {COLORS['border_strong']}; border-radius: 6px; padding: 6px; "
            f"font-size: {FONT['size_sm']}px; color: {COLORS['text']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}"
        )

        self.send_button = PrimaryButton("Send")
        self.send_button.clicked.connect(lambda: self.send_otp_clicked.emit(self.otp_input.text()))
        self.otp_input.returnPressed.connect(lambda: self.send_otp_clicked.emit(self.otp_input.text()))

        otp_row.addWidget(self.otp_input)
        otp_row.addWidget(self.send_button)

        self.enter_code_card = Card(
            'otp', "Enter Code", "Alternatively, enter the OTP that was provided to you.",
            extra_widget=otp_row_widget,
        )

        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)
        cards_row.addStretch()
        cards_row.addWidget(self.cancel_card)
        cards_row.addWidget(self.enter_code_card)
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
        image_path = os.path.join(base_dir, 'assets', 'wifi_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'")
            self.background_label.setStyleSheet("background-color: #ffffff;")

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def clear_otp_input(self):
        self.otp_input.clear()
