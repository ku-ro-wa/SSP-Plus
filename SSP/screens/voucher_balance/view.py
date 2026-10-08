# screens/voucher_balance/view.py
#
# Code entry plus the result: a Voucher's remaining value and expiry, nothing
# else. Contains no logic; the controller feeds it from VoucherBalanceModel.

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Header, PrimaryButton, StatusBanner


class VoucherBalanceScreenView(QWidget):
    check_clicked = pyqtSignal(str)  # code_text
    back_button_clicked = pyqtSignal()
    input_edited = pyqtSignal()

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

        title = QLabel("Check voucher balance")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        subtitle = QLabel("Enter your voucher code to see how much is left on it.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        entry_row = QHBoxLayout()
        entry_row.setSpacing(6)
        entry_row.addStretch()

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("XXXX-XXXX")
        self.code_input.setMaxLength(16)  # room for 'V1:' and spaces; normalize_code decides
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setMinimumWidth(260)
        self.code_input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {COLORS['border_strong']}; border-radius: 6px; padding: 8px; "
            f"font-size: {FONT['size_lg']}px; color: {COLORS['text']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}"
        )
        self.code_input.textEdited.connect(lambda _text: self.input_edited.emit())
        self.code_input.returnPressed.connect(self._emit_check)

        self.check_button = PrimaryButton("Check balance")
        self.check_button.clicked.connect(self._emit_check)

        entry_row.addWidget(self.code_input)
        entry_row.addWidget(self.check_button)
        entry_row.addStretch()

        # Remaining value and expiry; hidden until a code is found.
        self.result_panel = QWidget()
        result = QVBoxLayout(self.result_panel)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(4)

        caption = QLabel("Remaining value")
        caption.setAlignment(Qt.AlignCenter)
        caption.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.amount_label = QLabel("")
        self.amount_label.setAlignment(Qt.AlignCenter)
        self.amount_label.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: {FONT['size_display']}px; font-weight: 800;"
        )

        self.expiry_label = QLabel("")
        self.expiry_label.setAlignment(Qt.AlignCenter)
        self.expiry_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 600;"
        )

        result.addWidget(caption)
        result.addWidget(self.amount_label)
        result.addWidget(self.expiry_label)
        self.result_panel.hide()

        self.status_banner = StatusBanner()

        self.back_button = BackButton("Back to Home")
        self.back_button.clicked.connect(self.back_button_clicked.emit)

        body.addWidget(title)
        body.addWidget(subtitle)
        body.addSpacing(12)
        body.addLayout(entry_row)
        body.addSpacing(12)
        body.addWidget(self.result_panel)
        body.addWidget(self.status_banner)
        body.addStretch(2)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.back_button, 0, Qt.AlignLeft)
        nav_row.addStretch()
        body.addLayout(nav_row)

    def _emit_check(self):
        self.check_clicked.emit(self.code_input.text())

    def render(self, model):
        """Paint the current VoucherBalanceModel. Called by the controller."""
        self.result_panel.setVisible(model.found)
        self.amount_label.setText(model.amount_text())
        self.expiry_label.setText(model.expiry_text())
        if model.found:
            # The code has done its job; don't leave it on screen.
            self.code_input.clear()
            self.status_banner.show_message("")
        else:
            self.status_banner.show_message(model.message, "error")

    def clear(self):
        self.code_input.clear()
        self.amount_label.setText("")
        self.expiry_label.setText("")
        self.result_panel.hide()
        self.status_banner.show_message("")
