# screens/voucher/view.py
#
# Shows a freshly issued Voucher: typeable code + QR side by side (compact
# enough for the kiosk display), the amount, and a one-time-code warning.
# Contains no logic; the controller feeds it from VoucherModel.

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.theme import COLORS, FONT
from ui.widgets import Header, PrimaryButton, StatusBanner

QR_SIZE = 220


class VoucherScreenView(QWidget):
    continue_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(Header())

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        body = QVBoxLayout(content)
        body.setContentsMargins(60, 20, 60, 24)
        body.setSpacing(10)
        outer.addWidget(content, 1)

        body.addStretch(1)

        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;"
        )

        self.body_label = QLabel("")
        self.body_label.setAlignment(Qt.AlignCenter)
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;"
        )

        # QR on the left, code on the right; the whole row hides on failure.
        self.code_row = QWidget()
        row = QHBoxLayout(self.code_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(30)
        row.addStretch()

        self.qr_label = QLabel("")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setFixedSize(QR_SIZE, QR_SIZE)
        row.addWidget(self.qr_label)

        self.code_label = QLabel("")
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: 64px; font-weight: 800; letter-spacing: 8px;"
        )
        row.addWidget(self.code_label)
        row.addStretch()

        self.note_banner = StatusBanner()

        self.continue_button = PrimaryButton("Continue")
        self.continue_button.setMinimumHeight(50)
        self.continue_button.clicked.connect(self.continue_clicked.emit)

        nav = QHBoxLayout()
        nav.addStretch()
        nav.addWidget(self.continue_button)
        nav.addStretch()

        body.addWidget(self.title_label)
        body.addWidget(self.body_label)
        body.addSpacing(6)
        body.addWidget(self.code_row)
        body.addSpacing(6)
        body.addWidget(self.note_banner)
        body.addStretch(2)
        body.addLayout(nav)

    def render(self, model):
        """Paint the current VoucherModel. Called by the controller."""
        self.title_label.setText(model.title())
        self.body_label.setText(model.body())
        self.continue_button.setText(model.button_text())
        self.continue_button.setEnabled(True)

        self.code_row.setVisible(model.has_code)
        self.code_label.setText(model.display_code if model.has_code else "")
        self._set_qr(model.qr_bytes if model.has_qr else None)

        if model.has_code:
            self.note_banner.show_message(model.footnote(), "warning")
        else:
            self.note_banner.show_message(model.body(), "error")
            self.body_label.setText("")

    def _set_qr(self, png_bytes):
        pixmap = QPixmap()
        if png_bytes and pixmap.loadFromData(png_bytes, "PNG"):
            self.qr_label.setPixmap(pixmap.scaled(QR_SIZE, QR_SIZE, Qt.KeepAspectRatio))
            self.qr_label.show()
        else:
            self.qr_label.clear()
            self.qr_label.hide()  # the typeable code is still shown

    def clear(self):
        """Drop everything sensitive from the widgets."""
        self.code_label.setText("")
        self.qr_label.clear()
        self.note_banner.show_message("", "info")

    def set_busy(self):
        self.continue_button.setEnabled(False)
