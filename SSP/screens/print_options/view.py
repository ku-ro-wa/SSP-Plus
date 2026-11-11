# screens/print_options/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QButtonGroup, QFrame, QLabel, QPushButton, QSizePolicy
)
from PyQt5.QtCore import QElapsedTimer, Qt, pyqtSignal

from ui.theme import COLORS, RADIUS, FONT
from ui.touch_scroll import SCROLLBAR_QSS, DragScrollArea
from ui.widgets import Header, BackButton, PrimaryButton, SecondaryButton, StatusBanner, nav_row

# Big enough to hit reliably on the touchscreen panel
STEPPER_SIZE = 64
# Taps closer together than this are one touch the panel reported several times
STEPPER_REPEAT_MS = 150

STEPPER_BUTTON_QSS = f"""
QPushButton {{
    background-color: {COLORS["primary"]}; color: {COLORS["bg"]}; border: none;
    border-radius: {RADIUS["sm"]}px; font-size: 30px; font-weight: 700;
    min-width: {STEPPER_SIZE}px; max-width: {STEPPER_SIZE}px; min-height: {STEPPER_SIZE}px;
    max-height: {STEPPER_SIZE}px; padding: 0;
}}
QPushButton:hover {{ background-color: {COLORS["primary_hover"]}; }}
QPushButton:pressed {{ background-color: {COLORS["primary_pressed"]}; }}
"""

SEGMENT_BUTTON_QSS = f"""
QPushButton {{
    background-color: {COLORS["bg"]}; color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border_strong"]}; border-radius: {RADIUS["sm"]}px;
    font-size: {FONT["size_md"]}px; font-weight: 600; min-width: 96px; min-height: 52px;
    padding-left: 12px; padding-right: 12px;
}}
QPushButton:hover {{ border-color: {COLORS["primary"]}; color: {COLORS["primary"]}; }}
QPushButton:checked {{
    background-color: {COLORS["primary"]}; color: {COLORS["bg"]}; border-color: {COLORS["primary"]};
}}
"""

BW = "Black and White"
COLOR = "Color"


class PrintItemRow(QFrame):
    """One file's settings: its place in the print order, name and pages, B&W/Color,
    copies and price. Contains no logic; the controller tells the model."""
    color_clicked = pyqtSignal(int, str)   # index, mode
    copies_step = pyqtSignal(int, int)     # index, +1 / -1

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self._last_step = QElapsedTimer()
        self.setObjectName("PrintItemRow")
        self.setStyleSheet(
            f"QFrame#PrintItemRow {{ background-color: {COLORS['bg']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: {RADIUS['md']}px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        self.position_label = QLabel(str(index + 1))
        self.position_label.setAlignment(Qt.AlignCenter)
        self.position_label.setFixedSize(44, 44)
        self.position_label.setStyleSheet(
            f"background-color: {COLORS['text']}; color: {COLORS['bg']}; border-radius: 22px; "
            f"font-size: {FONT['size_md']}px; font-weight: 700;"
        )
        layout.addWidget(self.position_label)

        names = QVBoxLayout()
        names.setSpacing(2)
        self.name_label = QLabel("")
        self.name_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; font-weight: 700; border: none;"
        )
        self.name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.pages_label = QLabel("")
        self.pages_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_sm']}px; font-weight: 600; border: none;"
        )
        names.addWidget(self.name_label)
        names.addWidget(self.pages_label)
        layout.addLayout(names, 1)
        self._full_name = ""

        self.bw_btn = QPushButton("B&&W")
        self.color_btn = QPushButton("Color")
        for button in (self.bw_btn, self.color_btn):
            button.setCheckable(True)
            button.setStyleSheet(SEGMENT_BUTTON_QSS)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.bw_btn)
        self._mode_group.addButton(self.color_btn)
        self.bw_btn.clicked.connect(lambda: self.color_clicked.emit(self.index, BW))
        self.color_btn.clicked.connect(lambda: self.color_clicked.emit(self.index, COLOR))
        layout.addWidget(self.bw_btn)
        layout.addWidget(self.color_btn)
        layout.addSpacing(8)

        self.copies_minus_btn = _stepper_button("−")
        self.copies_plus_btn = _stepper_button("+")
        self.copies_minus_btn.clicked.connect(lambda: self._step(-1))
        self.copies_plus_btn.clicked.connect(lambda: self._step(1))
        self.copies_count_label = QLabel("1")
        self.copies_count_label.setAlignment(Qt.AlignCenter)
        self.copies_count_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 26px; font-weight: 700; border: none; "
            f"min-width: 48px; max-width: 48px;"
        )
        layout.addWidget(self.copies_minus_btn)
        layout.addWidget(self.copies_count_label)
        layout.addWidget(self.copies_plus_btn)

        self.price_label = QLabel("")
        self.price_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.price_label.setMinimumWidth(130)
        self.price_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700; border: none;"
        )
        layout.addWidget(self.price_label)

    def _step(self, delta):
        # Taps closer together than this are one touch the panel reported several times
        if self._last_step.isValid() and self._last_step.elapsed() < STEPPER_REPEAT_MS:
            return
        self._last_step.start()
        self.copies_step.emit(self.index, delta)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_name()

    def _elide_name(self):
        metrics = self.name_label.fontMetrics()
        self.name_label.setText(metrics.elidedText(self._full_name, Qt.ElideMiddle, max(self.name_label.width(), 40)))

    def show_item(self, item):
        """Shows the item's current settings; the price reads 'Calculating...' until it's priced."""
        self._full_name = item.file_name
        self.name_label.setToolTip(item.file_name)
        self._elide_name()
        pages = len(item.pages)
        self.pages_label.setText(f"{pages} page{'s' if pages != 1 else ''}")
        (self.color_btn if item.color_mode == COLOR else self.bw_btn).setChecked(True)
        self.copies_count_label.setText(str(item.copies))
        self.price_label.setText(f"₱{item.cost:.2f}" if item.analysis is not None else "Calculating…")


class PrintOptionsScreenView(QWidget):
    """The user interface for the Print Options Screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    voucher_balance_clicked = pyqtSignal()
    continue_button_clicked = pyqtSignal()
    item_color_clicked = pyqtSignal(int, str)   # item index, mode
    item_copies_step = pyqtSignal(int, int)     # item index, +1 / -1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cost_text = "Calculating cost..."
        self._details_text = "Analysis details will appear here."
        self.item_rows = []
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(40, 24, 40, 12)
        layout.setSpacing(12)
        main_layout.addWidget(body, 1)

        self.back_btn = BackButton("Back to Input Selection")
        self.back_btn.clicked.connect(self.back_button_clicked.emit)

        # ---- One row per file; scrolls when there are more than fit ----
        self.scroll = DragScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(SCROLLBAR_QSS)
        self.scroll.setMinimumHeight(150)
        self.rows_widget = QWidget()
        self.rows_widget.setStyleSheet("background-color: transparent;")
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.rows_widget)
        layout.addWidget(self.scroll, 1)

        # ---- Cost / analysis / paper-warning status ----
        self.status_banner = StatusBanner()
        layout.addWidget(self.status_banner)

        # ---- Supplies warnings (low change/ink/paper), separate from cost status ----
        self.supplies_banner = StatusBanner()
        layout.addWidget(self.supplies_banner)

        # ---- Buttons ----
        self.continue_btn = PrimaryButton("Continue to Payment →")
        self.continue_btn.clicked.connect(self.continue_button_clicked.emit)
        # A popup over this screen, so checking a voucher never costs the customer their place
        self.voucher_balance_btn = SecondaryButton("Check voucher balance")
        self.voucher_balance_btn.clicked.connect(self.voucher_balance_clicked.emit)
        layout.addLayout(nav_row(self.back_btn, self.voucher_balance_btn, self.continue_btn))

        # Don't set layout here - let the controller handle it
        self.main_layout = main_layout

        self._refresh_status_banner("info")

    def _refresh_status_banner(self, variant):
        self.status_banner.show_message(f"{self._cost_text}\n{self._details_text}", variant)

    # --- The file rows ---

    def set_items(self, items):
        """Builds one row per item, in print order."""
        for row in self.item_rows:
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.item_rows = []
        for index, item in enumerate(items):
            row = PrintItemRow(index)
            row.color_clicked.connect(self.item_color_clicked.emit)
            row.copies_step.connect(self.item_copies_step.emit)
            row.show_item(item)
            self.item_rows.append(row)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self.scroll.verticalScrollBar().setValue(0)

    def update_item(self, index, item):
        if 0 <= index < len(self.item_rows):
            self.item_rows[index].show_item(item)

    def update_cost_display(self, cost_text, details_text):
        """Updates the cost and details display."""
        self._cost_text = cost_text
        self._details_text = details_text
        self._refresh_status_banner("info")

    def set_analysis_status(self, status_text, details_text):
        """Sets the analysis status display."""
        self._cost_text = status_text
        self._details_text = details_text
        self._refresh_status_banner("info")

    def set_continue_button_enabled(self, enabled):
        """Enables or disables the continue button."""
        self.continue_btn.setEnabled(enabled)

    def show_paper_warning(self, available_paper, required_paper):
        """Shows a warning about insufficient paper."""
        self._cost_text = "⚠️ INSUFFICIENT PAPER ⚠️"
        self._details_text = (
            f"Only {available_paper} sheets available, but {required_paper} sheets needed.\n"
            f"Please contact administrator to refill paper."
        )
        self._refresh_status_banner("error")

        self.continue_btn.setEnabled(False)
        self.continue_btn.setText("Insufficient Paper")

    def clear_paper_warning(self):
        """Clears the paper warning and resets the display."""
        self.continue_btn.setEnabled(True)
        self.continue_btn.setText("Continue to Payment →")
        self._refresh_status_banner("info")

    def update_supplies_status(self, status):
        """Surfaces low-paper/low-coin/low-ink warnings reported by the supplies check."""
        warnings = status.get('warnings') or []
        if warnings:
            self.supplies_banner.show_message("\n".join(warnings), "warning")
        else:
            self.supplies_banner.show_message("")


def _stepper_button(text):
    btn = QPushButton(text)
    btn.setStyleSheet(STEPPER_BUTTON_QSS)
    btn.setFixedSize(STEPPER_SIZE, STEPPER_SIZE)
    return btn
