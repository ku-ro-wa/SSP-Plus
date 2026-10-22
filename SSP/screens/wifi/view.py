# screens/wifi/view.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.qr import qr_pixmap
from ui.widgets import BackButton, Header, OtpEntryPanel, ReaderHint, StatusBanner, nav_row


class WifiScreenView(QWidget):
    """The user interface for the WiFi Upload screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    send_otp_clicked = pyqtSignal(str)  # otp_text
    otp_entry_activity = pyqtSignal()  # a keypad key was pressed

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
        guide_title.setAlignment(Qt.AlignLeft)
        guide_title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        self.guide_text = QLabel(
            '1. Connect your phone to the same network as this kiosk.<br>'
            '2. Open the address below in a browser and upload your PDF file(s).<br>'
            '3. Type the 6-digit code shown after the upload on the keypad.'
        )
        self.guide_text.setAlignment(Qt.AlignLeft)
        self.guide_text.setWordWrap(True)
        self.guide_text.setFixedWidth(600)
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
        portal_row.addWidget(self.portal_qr_label)
        portal_row.addLayout(url_column)
        portal_row.addStretch()

        guide_column = QVBoxLayout()
        guide_column.setSpacing(0)
        guide_column.addStretch()  # centred beside the taller keypad, not spread to its height
        guide_column.addWidget(guide_title)
        guide_column.addSpacing(8)
        guide_column.addWidget(self.guide_text)
        guide_column.addSpacing(16)
        guide_column.addLayout(portal_row)
        guide_column.addStretch()

        # The touchscreen has no keyboard, so the code is typed on this keypad.
        # Beside the guide, not under it: stacked, the page is taller than the screen.
        self.otp_entry = OtpEntryPanel()
        self.otp_entry.submitted.connect(self.send_otp_clicked.emit)
        self.otp_entry.activity.connect(self.otp_entry_activity.emit)
        self.otp_input = self.otp_entry.input
        self.send_button = self.otp_entry.send_button

        columns = QHBoxLayout()
        columns.setSpacing(80)
        columns.addStretch()
        columns.addLayout(guide_column)
        columns.addWidget(self.otp_entry, alignment=Qt.AlignVCenter)
        columns.addStretch()
        body_layout.addLayout(columns)

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
        self.otp_entry.clear()
