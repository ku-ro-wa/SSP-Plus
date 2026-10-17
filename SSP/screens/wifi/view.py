# screens/wifi/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator

from ui.theme import COLORS, FONT
from ui.qr import qr_pixmap
from ui.widgets import BackButton, Card, Header, PrimaryButton, ReaderHint, StatusBanner, nav_row


class WifiScreenView(QWidget):
    """The user interface for the WiFi Upload screen. Contains no logic."""
    cancel_card_clicked = pyqtSignal()
    back_button_clicked = pyqtSignal()
    send_otp_clicked = pyqtSignal(str)  # otp_text

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

        self.guide_text = QLabel(
            '1. Connect your phone to the same network as this kiosk.<br>'
            '2. Open the address below in a browser and upload your PDF file(s).<br>'
            '3. Enter the 6-digit code shown after the upload.'
        )
        self.guide_text.setAlignment(Qt.AlignCenter)
        self.guide_text.setWordWrap(True)
        self.guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.portal_url_label = QLabel("")
        self.portal_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.portal_url_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )

        # A phone VPN routes the portal address into the tunnel, so the page never loads
        self.vpn_note = QLabel("Page won't load? Turn off any VPN on your phone, then try again.")
        self.vpn_note.setWordWrap(True)
        self.vpn_note.setMaximumWidth(420)
        self.vpn_note.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_sm']}px; font-weight: 600;"
        )

        url_column = QVBoxLayout()
        url_column.setSpacing(8)
        url_column.addStretch()
        url_column.addWidget(self.portal_url_label)
        url_column.addWidget(self.vpn_note)
        url_column.addStretch()

        self.portal_qr_label = QLabel("")
        self.portal_qr_label.setAlignment(Qt.AlignCenter)

        # QR beside the address, not under it: stacked, the page is taller than the screen
        portal_row = QHBoxLayout()
        portal_row.setSpacing(24)
        portal_row.addStretch()
        portal_row.addWidget(self.portal_qr_label)
        portal_row.addLayout(url_column)
        portal_row.addStretch()

        body_layout.addWidget(guide_title)
        body_layout.addSpacing(8)
        body_layout.addWidget(self.guide_text)
        body_layout.addSpacing(10)
        body_layout.addLayout(portal_row)
        body_layout.addSpacing(16)

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

        # Shorter than the default card, so the page fits with its QR, a status and the nav row
        for card in (self.cancel_card, self.enter_code_card):
            card.setFixedHeight(172)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)
        cards_row.addStretch()
        cards_row.addWidget(self.cancel_card)
        cards_row.addWidget(self.enter_code_card)
        cards_row.addStretch()
        body_layout.addLayout(cards_row)

        body_layout.addSpacing(12)
        self.reader_hint = ReaderHint()
        body_layout.addWidget(self.reader_hint)
        body_layout.addSpacing(8)

        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        body_layout.addStretch(2)

        body_layout.addLayout(nav_row(self.back_button))

    def set_portal_hint(self, url: str):
        """Show the live upload-portal URL and a scannable QR of it."""
        self.portal_url_label.setText(url)
        self.portal_qr_label.setPixmap(qr_pixmap(url, size=160))

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def clear_otp_input(self):
        self.otp_input.clear()
