# screens/print_options/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QButtonGroup, QLabel, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, RADIUS, FONT
from ui.widgets import Header, BackButton, PrimaryButton, StatusBanner

STEPPER_BUTTON_QSS = f"""
QPushButton {{
    background-color: {COLORS["primary"]}; color: {COLORS["bg"]}; border: none;
    border-radius: {RADIUS["sm"]}px; font-size: 22px; font-weight: 700;
    min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; padding: 0;
}}
QPushButton:hover {{ background-color: {COLORS["primary_hover"]}; }}
QPushButton:pressed {{ background-color: {COLORS["primary_pressed"]}; }}
"""

SEGMENT_BUTTON_QSS = f"""
QPushButton {{
    background-color: {COLORS["bg"]}; color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border_strong"]}; border-radius: {RADIUS["sm"]}px;
    font-size: {FONT["size_md"]}px; font-weight: 600; min-width: 140px; min-height: 44px;
    padding-left: 12px; padding-right: 12px;
}}
QPushButton:hover {{ border-color: {COLORS["primary"]}; color: {COLORS["primary"]}; }}
QPushButton:checked {{
    background-color: {COLORS["primary"]}; color: {COLORS["bg"]}; border-color: {COLORS["primary"]};
}}
"""


class PrintOptionsScreenView(QWidget):
    """The user interface for the Print Options Screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    continue_button_clicked = pyqtSignal()
    bw_mode_clicked = pyqtSignal()
    color_mode_clicked = pyqtSignal()
    copies_decreased = pyqtSignal()
    copies_increased = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cost_text = "Calculating cost..."
        self._details_text = "Analysis details will appear here."
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
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)
        main_layout.addWidget(body, 1)

        top_row = QHBoxLayout()
        self.back_btn = BackButton("Back to File Browser")
        self.back_btn.clicked.connect(self.back_button_clicked.emit)
        top_row.addWidget(self.back_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        layout.addStretch(1)

        # === Centered container for copies + color mode ===
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(24)
        center_layout.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        # ---- Number of Copies Row ----
        copies_row = QHBoxLayout()
        copies_row.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        copies_label = QLabel("Number of Copies:")
        copies_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )
        copies_row.addWidget(copies_label)

        self.copies_minus_btn = _stepper_button("−")
        self.copies_plus_btn = _stepper_button("+")
        self.copies_minus_btn.clicked.connect(self.copies_decreased.emit)
        self.copies_plus_btn.clicked.connect(self.copies_increased.emit)

        copies_row.addSpacing(20)
        copies_row.addWidget(self.copies_minus_btn)

        self.copies_count_label = QLabel("1")
        self.copies_count_label.setAlignment(Qt.AlignCenter)
        self.copies_count_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 22px; font-weight: 700; "
            f"min-width: 40px; max-width: 40px;"
        )
        copies_row.addWidget(self.copies_count_label)
        copies_row.addWidget(self.copies_plus_btn)
        copies_row.addStretch(1)
        center_layout.addLayout(copies_row)

        # ---- Color Mode Row ----
        color_row = QHBoxLayout()
        color_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        color_label = QLabel("Color Mode:")
        color_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )
        color_row.addWidget(color_label)
        color_row.addStretch(1)

        self.bw_btn = QPushButton("Black and White")
        self.color_btn = QPushButton("Colored")
        self.bw_btn.setCheckable(True)
        self.color_btn.setCheckable(True)
        self.bw_btn.setStyleSheet(SEGMENT_BUTTON_QSS)
        self.color_btn.setStyleSheet(SEGMENT_BUTTON_QSS)
        self.bw_btn.setChecked(True)

        self._color_mode_group = QButtonGroup(self)
        self._color_mode_group.setExclusive(True)
        self._color_mode_group.addButton(self.bw_btn)
        self._color_mode_group.addButton(self.color_btn)

        self.bw_btn.clicked.connect(self.bw_mode_clicked.emit)
        self.color_btn.clicked.connect(self.color_mode_clicked.emit)

        color_row.addWidget(self.bw_btn)
        color_row.addSpacing(8)
        color_row.addWidget(self.color_btn)
        center_layout.addLayout(color_row)

        layout.addWidget(center_container, 0, Qt.AlignHCenter)
        layout.addSpacing(40)

        # ---- Cost / analysis / paper-warning status ----
        self.status_banner = StatusBanner()
        layout.addWidget(self.status_banner)

        # ---- Supplies warnings (low change/ink/paper), separate from cost status ----
        self.supplies_banner = StatusBanner()
        layout.addWidget(self.supplies_banner)

        layout.addStretch(2)

        # ---- Buttons ----
        buttons_layout = QHBoxLayout()
        self.continue_btn = PrimaryButton("Continue to Payment →")
        self.continue_btn.setMinimumHeight(44)
        self.continue_btn.clicked.connect(self.continue_button_clicked.emit)

        buttons_layout.addStretch()
        buttons_layout.addWidget(self.continue_btn)
        layout.addLayout(buttons_layout)

        # Don't set layout here - let the controller handle it
        self.main_layout = main_layout

        self._refresh_status_banner("info")

    def _refresh_status_banner(self, variant):
        self.status_banner.show_message(f"{self._cost_text}\n{self._details_text}", variant)

    def update_copies_display(self, copies):
        """Updates the copies count display."""
        self.copies_count_label.setText(str(copies))

    def set_bw_mode(self):
        """Sets the black and white mode as selected."""
        self.bw_btn.setChecked(True)

    def set_color_mode(self):
        """Sets the color mode as selected."""
        self.color_btn.setChecked(True)

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
    btn.setFixedSize(44, 44)
    return btn
