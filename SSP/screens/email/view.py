# screens/email/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator

from ui.theme import COLORS, FONT
from ui.qr import qr_pixmap
from ui.widgets import BackButton, Card, Header, PrimaryButton, StatusBanner


class EmailScreenView(QWidget):
    """The user interface for the Email Upload screen. Contains no logic."""
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
            '1. Email your PDF file(s) to the address below, with the keyword in the subject line.<br>'
            '2. You will get a reply with a 6-digit code and a QR code.<br>'
            '3. Enter that code below.'
        )
        self.guide_text.setAlignment(Qt.AlignCenter)
        self.guide_text.setWordWrap(True)
        self.guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.address_label = QLabel("")
        self.address_label.setAlignment(Qt.AlignCenter)
        self.address_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.address_label.setWordWrap(True)
        self.address_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )

        self.address_qr_label = QLabel("")
        self.address_qr_label.setAlignment(Qt.AlignCenter)

        body_layout.addWidget(guide_title)
        body_layout.addSpacing(8)
        body_layout.addWidget(self.guide_text)
        body_layout.addSpacing(10)
        body_layout.addWidget(self.address_label)
        body_layout.addSpacing(8)
        body_layout.addWidget(self.address_qr_label)
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

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.back_button, 0, Qt.AlignLeft)
        nav_row.addStretch()
        body_layout.addLayout(nav_row)

    def set_email_hint(self, address: str, keyword: str):
        """Show the submission address + required subject keyword, and a
        mailto: QR that pre-fills both."""
        if address:
            self.address_label.setText(f'{address}<br>subject must contain: <b>{keyword}</b>')
            self.address_qr_label.setPixmap(qr_pixmap(f"mailto:{address}?subject={keyword}"))
        else:
            self.address_label.setText(
                "No email account configured — set EMAIL_USER in .env"
            )
            self.address_qr_label.clear()

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def clear_otp_input(self):
        self.otp_input.clear()
