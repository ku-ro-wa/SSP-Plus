# screens/scan_result/view.py
#
# Reverses screens/wifi's QR pattern: that screen shows a QR of the upload
# portal so a phone can send files IN to the kiosk. This one shows a QR of
# the redeem portal so the user can pull a kiosk-generated file OUT to
# their own phone (download or email) — see webapp/routers/redeem.py.

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.qr import qr_pixmap
from ui.widgets import Header, PrimaryButton


class ScanResultScreenView(QWidget):
    """Shows the redeem-portal QR + OTP for a scan sent via Wi-Fi. Contains no logic."""
    done_clicked = pyqtSignal()

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

        body_layout.addStretch(1)

        title = QLabel("Get Your Scan on Your Phone")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        guide_text = QLabel(
            'Open the address below on your OWN phone, then enter the code shown '
            'below to download this scan or have it emailed to you.'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.portal_url_label = QLabel("")
        self.portal_url_label.setAlignment(Qt.AlignCenter)
        self.portal_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.portal_url_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )

        self.portal_qr_label = QLabel("")
        self.portal_qr_label.setAlignment(Qt.AlignCenter)

        self.otp_label = QLabel("")
        self.otp_label.setAlignment(Qt.AlignCenter)
        self.otp_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.otp_label.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: 48px; font-weight: 800; letter-spacing: 6px;"
        )

        body_layout.addWidget(title)
        body_layout.addSpacing(8)
        body_layout.addWidget(guide_text)
        body_layout.addSpacing(10)
        body_layout.addWidget(self.portal_url_label)
        body_layout.addSpacing(8)
        body_layout.addWidget(self.portal_qr_label)
        body_layout.addSpacing(16)
        body_layout.addWidget(self.otp_label)
        body_layout.addSpacing(16)

        self.done_button = PrimaryButton("Done")
        self.done_button.clicked.connect(self.done_clicked.emit)

        body_layout.addStretch(2)

        nav_row = QHBoxLayout()
        nav_row.addStretch()
        nav_row.addWidget(self.done_button)
        nav_row.addStretch()
        body_layout.addLayout(nav_row)

    def set_portal_hint(self, url: str):
        self.portal_url_label.setText(url)
        self.portal_qr_label.setPixmap(qr_pixmap(url))

    def set_otp(self, otp: str):
        self.otp_label.setText(otp)
