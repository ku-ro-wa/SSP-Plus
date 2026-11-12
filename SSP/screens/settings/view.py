# screens/settings/view.py

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ui.theme import COLORS, FONT, INPUT_QSS
from ui.widgets import BackButton, CodeKeypad, Header, PrimaryButton, nav_row


class SettingsScreenView(QWidget):
    """One row per setting and a keypad. Tap a field, type, Save. No logic.
    Kept within 800 logical px tall (tests/test_screen_render.py)."""

    back_clicked = pyqtSignal()
    save_clicked = pyqtSignal(dict)   # {key: text as typed}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fields = {}
        self._rows = {}
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(40, 20, 40, 12)
        self.body_layout.setSpacing(8)
        outer.addWidget(body, 1)

        title = QLabel("Settings")
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;")
        self.body_layout.addWidget(title)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        self.body_layout.addLayout(self.rows_layout)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(24)
        self.body_layout.addWidget(self.status_label)

        self.keypad = CodeKeypad(self._focused_field, "0123456789", columns=11, key_size=48)
        self.body_layout.addWidget(self.keypad, alignment=Qt.AlignHCenter)
        self.body_layout.addStretch(1)

        self.back_button = BackButton("Back to Admin")
        self.save_button = PrimaryButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.back_button.clicked.connect(self.back_clicked.emit)
        self.body_layout.addLayout(nav_row(self.back_button, self.save_button))

    def set_entries(self, entries):
        """Build the rows once, then just refresh the values on later visits."""
        if not self.fields:
            for setting, _ in entries:
                self._add_row(setting)
        for setting, value in entries:
            self.fields[setting.key].setText(str(value))
            self._mark(setting.key, False)
        first = next(iter(self.fields.values()), None)
        if first is not None:
            first.setFocus()

    def _add_row(self, setting):
        row = QHBoxLayout()
        row.setSpacing(12)
        unit = f" ({setting.unit})" if setting.unit else ""
        label = QLabel(f"{setting.label}{unit}")
        label.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; font-weight: 600;")
        hint = QLabel(f"{setting.minimum}–{setting.maximum}, default {setting.current_default()}")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: {FONT['size_sm']}px;")
        field = QLineEdit()
        field.setMinimumHeight(44)
        field.setFixedWidth(140)
        field.setAlignment(Qt.AlignRight)
        field.setStyleSheet(INPUT_QSS)
        row.addWidget(label, 1)
        row.addWidget(hint)
        row.addWidget(field)
        self.rows_layout.addLayout(row)
        self.fields[setting.key] = field

    def _focused_field(self):
        focused = self.focusWidget()
        return focused if focused in self.fields.values() else None

    def _mark(self, key, bad):
        border = f"QLineEdit {{ border-color: {COLORS['danger']}; }}" if bad else ""
        self.fields[key].setStyleSheet(INPUT_QSS + border)

    def _on_save(self):
        self.save_clicked.emit({k: f.text() for k, f in self.fields.items()})

    def show_saved(self):
        self._tint(COLORS["success"])
        self.status_label.setText("Saved. Changes apply straight away.")

    def show_errors(self, errors):
        """`errors` is {key: message}; mark those fields and say nothing was saved."""
        for key in self.fields:
            self._mark(key, key in errors)
        self._tint(COLORS["danger"])
        self.status_label.setText("Nothing saved. " + " ".join(errors.values()))

    def clear_status(self):
        self.status_label.setText("")

    def _tint(self, colour):
        self.status_label.setStyleSheet(f"color: {colour}; font-size: {FONT['size_md']}px; font-weight: 600;")
