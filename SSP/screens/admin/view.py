# screens/admin/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QLineEdit, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator

from ui.theme import COLORS, FONT, GROUPBOX_QSS, INPUT_QSS, RADIUS, severity_color
from ui.widgets import BackButton, Header, PrimaryButton, SecondaryButton

# Thresholds mirror screens/admin/model.py's own display logic.
PAPER_WARN, PAPER_CRIT = 50, 20
COIN_WARN, COIN_CRIT = 50, 20
INK_WARN, INK_CRIT = 25.0, 10.0

STEPPER_QSS = f"""
QPushButton {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-size: {FONT['size_lg']}px;
    font-weight: 700;
    border: 1px solid {COLORS['border_strong']};
    border-radius: {RADIUS['sm']}px;
}}
QPushButton:hover {{
    border-color: {COLORS['primary']};
    color: {COLORS['primary']};
}}
QPushButton:pressed {{
    background-color: {COLORS['bg_subtle']};
}}
"""


class AdminScreenView(QWidget):
    """The user interface for the Admin Panel. Contains no logic."""
    back_clicked = pyqtSignal()
    view_data_logs_clicked = pyqtSignal()
    update_paper_clicked = pyqtSignal(str)
    reset_paper_clicked = pyqtSignal()
    update_coin_1_clicked = pyqtSignal(str)
    update_coin_5_clicked = pyqtSignal(str)
    reset_coins_clicked = pyqtSignal()
    update_cmyk_clicked = pyqtSignal(float, float, float, float)
    reset_cmyk_clicked = pyqtSignal()
    refresh_cmyk_clicked = pyqtSignal()

    # +/- button functionality
    paper_decreased = pyqtSignal()
    paper_increased = pyqtSignal()
    coin_1_decreased = pyqtSignal()
    coin_1_increased = pyqtSignal()
    coin_5_decreased = pyqtSignal()
    coin_5_increased = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    # ------------------------------------------------------------------ layout

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(40, 24, 40, 24)
        body_layout.setSpacing(14)
        outer_layout.addWidget(body, 1)

        body_layout.addWidget(self._create_paper_management_group())
        body_layout.addWidget(self._create_coin_management_group())
        body_layout.addWidget(self._create_cmyk_management_group())
        body_layout.addStretch(1)

        self.back_button = BackButton("Back to Main Screen")
        self.back_button.setMinimumHeight(44)
        self.back_button.clicked.connect(self.back_clicked.emit)

        self.view_logs_button = SecondaryButton("View Data Logs")
        self.view_logs_button.setMinimumHeight(44)
        self.view_logs_button.clicked.connect(self.view_data_logs_clicked.emit)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.back_button, 0)
        nav_row.addStretch()
        nav_row.addWidget(self.view_logs_button, 0)
        body_layout.addLayout(nav_row)

    def _section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; font-weight: 600;"
        )
        return label

    def _stepper(self, text, slot):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(44, 44)
        btn.setStyleSheet(STEPPER_QSS)
        btn.clicked.connect(slot)
        return btn

    def _count_label(self):
        label = QLabel("0")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumWidth(56)
        label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )
        return label

    def _create_paper_management_group(self):
        group = QGroupBox("Paper Management")
        group.setStyleSheet(GROUPBOX_QSS)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._section_label("Paper Count"))
        row.addWidget(self._stepper("−", self.paper_decreased.emit))
        self.paper_count_label = self._count_label()
        row.addWidget(self.paper_count_label)
        row.addWidget(self._stepper("+", self.paper_increased.emit))
        row.addStretch()

        reset_paper_btn = PrimaryButton("Refill")
        reset_paper_btn.setMinimumHeight(44)
        reset_paper_btn.clicked.connect(self.reset_paper_clicked.emit)
        row.addWidget(reset_paper_btn)

        layout.addLayout(row)
        return group

    def _create_coin_management_group(self):
        group = QGroupBox("Coin Inventory")
        group.setStyleSheet(GROUPBOX_QSS)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        p1_row = QHBoxLayout()
        p1_row.setSpacing(10)
        p1_row.addWidget(self._section_label("₱1 Coins"))
        p1_row.addWidget(self._stepper("−", self.coin_1_decreased.emit))
        self.coin_1_label = self._count_label()
        p1_row.addWidget(self.coin_1_label)
        p1_row.addWidget(self._stepper("+", self.coin_1_increased.emit))
        p1_row.addStretch()
        layout.addLayout(p1_row)

        p5_row = QHBoxLayout()
        p5_row.setSpacing(10)
        p5_row.addWidget(self._section_label("₱5 Coins"))
        p5_row.addWidget(self._stepper("−", self.coin_5_decreased.emit))
        self.coin_5_label = self._count_label()
        p5_row.addWidget(self.coin_5_label)
        p5_row.addWidget(self._stepper("+", self.coin_5_increased.emit))
        p5_row.addStretch()

        reset_coins_btn = PrimaryButton("Refill All")
        reset_coins_btn.setMinimumHeight(44)
        reset_coins_btn.clicked.connect(self.reset_coins_clicked.emit)
        p5_row.addWidget(reset_coins_btn)
        layout.addLayout(p5_row)
        return group

    def _cmyk_field(self, label_text):
        col = QHBoxLayout()
        col.setSpacing(8)
        label = self._section_label(label_text)
        label.setMinimumWidth(80)
        col.addWidget(label)

        field = QLineEdit()
        field.setValidator(QDoubleValidator(0.0, 100.0, 2))
        field.setAlignment(Qt.AlignLeft)
        field.setMinimumHeight(44)
        field.setMaximumWidth(140)
        field.setStyleSheet(INPUT_QSS)
        col.addWidget(field)
        col.addStretch()
        return col, field

    def _create_cmyk_management_group(self):
        group = QGroupBox("CMYK Ink Levels")
        group.setStyleSheet(GROUPBOX_QSS)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        cm_row = QHBoxLayout()
        cm_row.setSpacing(20)
        cyan_col, self.cyan_input = self._cmyk_field("Cyan")
        magenta_col, self.magenta_input = self._cmyk_field("Magenta")
        cm_row.addLayout(cyan_col)
        cm_row.addLayout(magenta_col)
        layout.addLayout(cm_row)

        yk_row = QHBoxLayout()
        yk_row.setSpacing(20)
        yellow_col, self.yellow_input = self._cmyk_field("Yellow")
        black_col, self.black_input = self._cmyk_field("Black")
        yk_row.addLayout(yellow_col)
        yk_row.addLayout(black_col)
        layout.addLayout(yk_row)

        button_row = QHBoxLayout()
        button_row.addStretch()

        update_cmyk_btn = PrimaryButton("Update")
        update_cmyk_btn.setMinimumHeight(44)
        update_cmyk_btn.clicked.connect(self._update_cmyk_levels)
        button_row.addWidget(update_cmyk_btn)

        reset_cmyk_btn = PrimaryButton("Refill All")
        reset_cmyk_btn.setMinimumHeight(44)
        reset_cmyk_btn.clicked.connect(self.reset_cmyk_clicked.emit)
        button_row.addWidget(reset_cmyk_btn)

        refresh_cmyk_btn = SecondaryButton("Refresh")
        refresh_cmyk_btn.setMinimumHeight(44)
        refresh_cmyk_btn.clicked.connect(self.refresh_cmyk_clicked.emit)
        button_row.addWidget(refresh_cmyk_btn)

        layout.addLayout(button_row)
        return group

    # ------------------------------------------------------------- model -> view

    def update_paper_count_display(self, count, color=None):
        """Updates the paper count label, tinted by remaining level."""
        self.paper_count_label.setText(str(count))
        tint = severity_color(count, PAPER_WARN, PAPER_CRIT)
        self.paper_count_label.setStyleSheet(
            f"color: {tint}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )

    def update_coin_count_display(self, coin_1_count, coin_5_count):
        """Updates both coin count labels, tinted by remaining level."""
        for label, value in ((self.coin_1_label, coin_1_count), (self.coin_5_label, coin_5_count)):
            label.setText(str(value))
            tint = severity_color(value, COIN_WARN, COIN_CRIT)
            label.setStyleSheet(
                f"color: {tint}; font-size: {FONT['size_lg']}px; font-weight: 700;"
            )

    def update_cmyk_display(self, cyan, magenta, yellow, black):
        """Updates the CMYK input fields with current values."""
        self.cyan_input.setText(f"{cyan:.1f}")
        self.magenta_input.setText(f"{magenta:.1f}")
        self.yellow_input.setText(f"{yellow:.1f}")
        self.black_input.setText(f"{black:.1f}")
        self._update_cmyk_styling(cyan, magenta, yellow, black)

    def _update_cmyk_styling(self, cyan, magenta, yellow, black):
        """Colours each ink field's border by remaining level."""
        for field, level in (
            (self.cyan_input, cyan), (self.magenta_input, magenta),
            (self.yellow_input, yellow), (self.black_input, black),
        ):
            tint = severity_color(level, INK_WARN, INK_CRIT)
            field.setStyleSheet(INPUT_QSS + f"QLineEdit {{ border-color: {tint}; }}")

    # --------------------------------------------------------------- view -> model

    def _update_cmyk_levels(self):
        """Reads the four fields, validates, and emits update_cmyk_clicked."""
        try:
            cyan = float(self.cyan_input.text()) if self.cyan_input.text() else 0.0
            magenta = float(self.magenta_input.text()) if self.magenta_input.text() else 0.0
            yellow = float(self.yellow_input.text()) if self.yellow_input.text() else 0.0
            black = float(self.black_input.text()) if self.black_input.text() else 0.0

            if not (0.0 <= cyan <= 100.0 and 0.0 <= magenta <= 100.0 and
                    0.0 <= yellow <= 100.0 and 0.0 <= black <= 100.0):
                self.show_message_box("Invalid Input", "CMYK values must be between 0.0 and 100.0")
                return

            self.update_cmyk_clicked.emit(cyan, magenta, yellow, black)
        except ValueError:
            self.show_message_box("Invalid Input", "Please enter valid decimal numbers for CMYK levels")

    def show_message_box(self, title: str, text: str):
        QMessageBox.warning(self, title, text)
