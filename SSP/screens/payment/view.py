# screens/payment/view.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.widgets import Header, BackButton, PrimaryButton, SecondaryButton, StatusBanner

try:
    import pigpio  # noqa: F401
    PAYMENT_GPIO_AVAILABLE = True
except ImportError:
    PAYMENT_GPIO_AVAILABLE = False


def _classify_status_variant(status_text: str) -> str:
    text = status_text.lower()
    if "error" in text or "fail" in text or "insufficient" in text:
        return "error"
    if any(kw in text for kw in ("success", "dispensed", "sufficient", "received", "complete")):
        return "success"
    return "info"


class PaymentScreenView(QWidget):
    """View for the Payment screen - handles UI components and presentation."""

    # Signals for user interactions
    back_button_clicked = pyqtSignal()
    simulation_coin_clicked = pyqtSignal(int)  # coin_value
    simulation_bill_clicked = pyqtSignal(int)  # bill_value
    voucher_code_entered = pyqtSignal(str)     # raw text from the "Use a voucher" entry
    voucher_entry_activity = pyqtSignal()      # typing in the entry (keeps the screen awake)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface for the screen."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(30, 20, 30, 30)
        body_layout.setSpacing(10)
        main_layout.addWidget(body, 1)

        top_row = QHBoxLayout()
        self.back_btn = BackButton("Back to Options")
        self.back_btn.setMinimumHeight(44)
        self.back_btn.clicked.connect(self.back_button_clicked.emit)
        top_row.addWidget(self.back_btn)
        top_row.addStretch()
        body_layout.addLayout(top_row)

        body_layout.addStretch(1)

        # Summary label
        self.summary_label = QLabel("Print Job Summary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; padding: 10px;"
        )
        body_layout.addWidget(self.summary_label)

        # Total label
        self.total_label = QLabel("Total Amount Due: P0.00")
        self.total_label.setAlignment(Qt.AlignCenter)
        self.total_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700; padding: 12px;"
        )
        body_layout.addWidget(self.total_label)

        # Suggested payment, shown independently of the status banner below.
        self.suggestion_banner = StatusBanner()
        body_layout.addWidget(self.suggestion_banner)

        # Payment status
        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        # Amount received label
        self.amount_received_label = QLabel("Amount Received: P0.00")
        self.amount_received_label.setAlignment(Qt.AlignCenter)
        self.amount_received_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700; padding: 10px;"
        )
        body_layout.addWidget(self.amount_received_label)

        # Change label
        self.change_label = QLabel("")
        self.change_label.setAlignment(Qt.AlignCenter)
        self.change_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_lg']}px; font-weight: 700; "
            f"padding: 8px; background-color: {COLORS['bg_subtle']}; border-radius: 6px;"
        )
        body_layout.addWidget(self.change_label)

        self._add_voucher_entry(body_layout)

        # Add simulation buttons if GPIO not available
        if not PAYMENT_GPIO_AVAILABLE:
            self._add_simulation_buttons(body_layout)

        body_layout.addStretch(2)

        # Don't set layout here - let the controller handle it
        self.main_layout = main_layout

    def _add_voucher_entry(self, layout):
        """"Use a voucher": a button that reveals a code entry, plus the list
        of Vouchers Applied so far with what each will have left."""
        row = QHBoxLayout()
        row.setSpacing(6)
        self.use_voucher_btn = SecondaryButton("Use a voucher")
        self.use_voucher_btn.setMinimumHeight(44)
        self.use_voucher_btn.clicked.connect(self._show_voucher_input)
        row.addWidget(self.use_voucher_btn)

        self.voucher_input = QLineEdit()
        self.voucher_input.setPlaceholderText("Voucher code (XXXX-XXXX)")
        self.voucher_input.setMaxLength(16)  # room for 'V1:' and a hyphen
        self.voucher_input.setAlignment(Qt.AlignCenter)
        self.voucher_input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {COLORS['border_strong']}; border-radius: 6px; padding: 6px; "
            f"font-size: {FONT['size_md']}px; color: {COLORS['text']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}"
        )
        self.voucher_input.textEdited.connect(lambda _: self.voucher_entry_activity.emit())
        self.voucher_input.returnPressed.connect(self._submit_voucher)
        self.apply_voucher_btn = PrimaryButton("Apply")
        self.apply_voucher_btn.setMinimumHeight(44)
        self.apply_voucher_btn.clicked.connect(self._submit_voucher)
        row.addWidget(self.voucher_input, 1)
        row.addWidget(self.apply_voucher_btn)
        layout.addLayout(row)

        self.voucher_banner = StatusBanner()
        layout.addWidget(self.voucher_banner)

        self.vouchers_label = QLabel("")
        self.vouchers_label.setAlignment(Qt.AlignCenter)
        self.vouchers_label.setWordWrap(True)
        self.vouchers_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; padding: 4px;"
        )
        layout.addWidget(self.vouchers_label)
        self._set_voucher_input_visible(False)

    def _set_voucher_input_visible(self, visible):
        self.voucher_input.setVisible(visible)
        self.apply_voucher_btn.setVisible(visible)

    def _show_voucher_input(self):
        self._set_voucher_input_visible(True)
        self.voucher_input.setFocus()
        self.voucher_entry_activity.emit()

    def _submit_voucher(self):
        text = self.voucher_input.text()
        self.voucher_input.clear()  # don't leave a code sitting on screen
        if text.strip():
            self.voucher_code_entered.emit(text)

    def show_voucher_message(self, message, is_error):
        self.voucher_banner.show_message(message, "error" if is_error else "success")

    def update_vouchers(self, vouchers):
        """vouchers: [AppliedVoucher] in the order Applied."""
        lines = [f"{v.label}: P{v.amount} applied, P{v.remaining} left" for v in vouchers]
        self.vouchers_label.setText("<br>".join(lines))

    def reset_voucher_entry(self):
        self.voucher_input.clear()
        self._set_voucher_input_visible(False)
        self.voucher_banner.show_message("", "info")

    def _add_simulation_buttons(self, layout):
        """Adds simulation buttons for testing when GPIO is not available."""
        sim_banner = StatusBanner()
        sim_banner.show_message("Simulation Mode - Test Payment", "warning")
        layout.addWidget(sim_banner)

        sim_layout = QHBoxLayout()
        sim_layout.setSpacing(10)

        for val in [1, 5, 10, 20, 50, 100]:
            btn = SecondaryButton(f"P{val}")
            btn.setMinimumSize(44, 44)
            if val <= 10:
                btn.clicked.connect(lambda _, v=val: self.simulation_coin_clicked.emit(v))
            else:
                btn.clicked.connect(lambda _, v=val: self.simulation_bill_clicked.emit(v))
            sim_layout.addWidget(btn)

        layout.addLayout(sim_layout)

    def update_payment_data(self, summary_data):
        """Updates the payment data display."""
        self.total_label.setText(f"Total Amount Due: P{summary_data['total_cost']:.2f}")

        summary_lines = [
            "<b>Print Job Summary:</b>",
            f"• Document: {summary_data['document_name']}",
            f"• Copies: {summary_data['copies']}",
            f"• Color Mode: {summary_data['color_mode']}",
            f"• Breakdown: {summary_data['black_pages']} B&W pages, {summary_data['color_pages']} Color pages",
        ]
        self.summary_label.setText("<br>".join(summary_lines))

    def update_payment_status(self, status_text):
        """Updates the payment status banner."""
        self.status_banner.show_message(status_text, _classify_status_variant(status_text))

    def update_amount_received(self, amount):
        """Updates the amount received display."""
        self.amount_received_label.setText(f"Amount Received: P{amount:.2f}")

    def update_change_display(self, change_amount, change_text):
        """Updates the change display."""
        self.change_label.setText(change_text)
        if "Remaining" in change_text:
            color, bg = COLORS["danger"], COLORS["danger_bg"]
        else:
            color, bg = COLORS["success"], COLORS["success_bg"]
        self.change_label.setStyleSheet(
            f"color: {color}; font-size: {FONT['size_lg']}px; font-weight: 700; "
            f"padding: 8px; background-color: {bg}; border-radius: 6px;"
        )

    def set_buttons_enabled(self, back_enabled):
        """Sets the enabled state of all buttons."""
        self.back_btn.setEnabled(back_enabled)
        self.use_voucher_btn.setEnabled(back_enabled)
        self.apply_voucher_btn.setEnabled(back_enabled)

    def update_inline_suggestion(self, text: str):
        self.suggestion_banner.show_message(text or "", "info")
