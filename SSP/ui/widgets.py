# ui/widgets.py
"""Shared, presentation-only widgets used by view.py files across screens.

No imports from managers/, database/, or any model — these are part of the
view layer, just factored out of per-screen duplication.
"""

from PyQt5.QtCore import QRegularExpression, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QRegularExpressionValidator
from PyQt5.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from config import get_config
from managers.voucher_manager import MSG_UNGIVEN_CHANGE
from ui.icons import icon, icon_path, svg_widget
from ui.theme import (
    CARD_QSS, COLORS, DANGER_BUTTON_QSS, FONT, HEADER_QSS, PRIMARY_BUTTON_QSS, RADIUS,
    SECONDARY_BUTTON_QSS, status_banner_qss,
)


class LogoMark(QFrame):
    """Small square brand tile, styled after Notion's icon-tile pattern."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(38, 38)
        # Header is now dark, so the tile keeps its dark fill and gains a light
        # border for contrast rather than being inverted like the rest of the bar.
        self.setStyleSheet(
            f"background-color: {COLORS['text']}; border-radius: {RADIUS['sm']}px; "
            f"border: 1px solid {COLORS['border_strong']};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        mark_label = QLabel("AIO")
        mark_label.setAlignment(Qt.AlignCenter)
        mark_label.setStyleSheet(
            f"color: {COLORS['bg']}; font-size: 10px; font-weight: 700; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(mark_label)


class Header(QFrame):
    """App brand header: logo mark + wordmark, consistent across every screen.
    Replaces the graphic banner baked into each screen's legacy background image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Header")
        self.setStyleSheet(HEADER_QSS)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(12)

        layout.addWidget(LogoMark())

        wordmark_label = QLabel("AIO SPARK")
        wordmark_label.setStyleSheet(
            f"color: {COLORS['bg']}; font-size: {FONT['size_xl']}px; font-weight: 700; "
            f"letter-spacing: 0.5px;"
        )
        layout.addWidget(wordmark_label)
        layout.addStretch()


class Card(QFrame):
    """Reusable clickable card. Replaces the MethodCard/ClickableCard pattern
    duplicated across homepage/wifi/scanner/email views."""

    clicked = pyqtSignal(str)

    def __init__(self, key: str, title: str, description: str, icon_name: str = None,
                 extra_widget=None, parent=None):
        super().__init__(parent)
        self._key = key
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(CARD_QSS)
        self.setFixedSize(340, 200)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        # Stretches, not layout.setAlignment(): an aligned layout sizes wrapped labels by
        # their sizeHint, which cuts off a third line of description.
        layout.addStretch()

        if icon_name:
            icon = svg_widget(icon_name, size=(32, 32))
            layout.addWidget(icon, alignment=Qt.AlignCenter)
            layout.addSpacing(4)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 600;"
        )

        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_sm']}px;"
        )

        layout.addWidget(title_label)
        layout.addWidget(desc_label)

        if extra_widget:
            layout.addSpacing(4)
            layout.addWidget(extra_widget)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)


class PrimaryButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("PrimaryButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(PRIMARY_BUTTON_QSS)


class SecondaryButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("SecondaryButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(SECONDARY_BUTTON_QSS)


class BackButton(SecondaryButton):
    """Neutral-styled back/cancel navigation button. Reserves red/danger styling
    for actual errors, not plain navigation."""

    def __init__(self, text: str = "Back", parent=None):
        super().__init__(text, parent)
        self.setIcon(icon('back'))


# The touchscreen registers taps poorly near its edges, so the Back/Continue buttons
# in a screen's corners are bigger than ordinary buttons and kept in from the edge.
NAV_BUTTON_HEIGHT = 56
NAV_BUTTON_MIN_WIDTH = 200
NAV_EDGE_INSET = 16  # on top of the screen's own margins


def nav_button(button):
    """Size `button` as a corner navigation button (bigger touch target and text)."""
    button.setFixedHeight(NAV_BUTTON_HEIGHT)
    button.setMinimumWidth(NAV_BUTTON_MIN_WIDTH)
    button.setStyleSheet(
        button.styleSheet()
        + f"QPushButton#{button.objectName()} {{ font-size: {FONT['size_md']}px; font-weight: 600; }}"
    )
    return button


def nav_row(left=None, *right):
    """A screen's bottom row: `left` in the bottom-left corner, `right` buttons in the
    bottom-right, all sized by nav_button() and inset from the screen edges."""
    row = QHBoxLayout()
    row.setContentsMargins(NAV_EDGE_INSET, 0, NAV_EDGE_INSET, NAV_EDGE_INSET)
    row.setSpacing(12)
    if left is not None:
        row.addWidget(nav_button(left), 0, Qt.AlignLeft)
    row.addStretch()
    for button in right:
        row.addWidget(nav_button(button))
    return row


class DangerButton(QPushButton):
    """Filled red button for genuinely destructive / override actions only.
    Same footprint as PrimaryButton."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("DangerButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(DANGER_BUTTON_QSS)


READER_HINT = "Hold your QR code up to the reader, or type your code."


class ReaderHint(QLabel):
    """The kiosk QR reader's one-line hint, shown on idle, the homepage and both code screens.
    Hidden when QR_READER_PORT is blank: with no reader, nothing reads the QR code it asks for."""

    def __init__(self, parent=None):
        super().__init__(READER_HINT, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px; font-weight: 600;")
        if not get_config().qr_reader_port:
            self.hide()  # only ever hide: showing an unparented label opens it as a window


class StatusBanner(QFrame):
    """Color-coded status message with an icon, replacing ad hoc status QLabels
    duplicated across screens. Hidden when there's no message to show."""

    _ICON_BY_VARIANT = {"success": "check", "warning": "alert-triangle", "error": "alert-triangle"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBanner")
        self.setStyleSheet(status_banner_qss("error"))
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._icon = svg_widget("alert-triangle", size=(16, 16))
        layout.addWidget(self._icon)

        self._label = QLabel("")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, 1)

    def show_message(self, message: str, variant: str = "error"):
        """variant: 'success' | 'warning' | 'error'. Empty message hides the banner."""
        if not message:
            self.setVisible(False)
            return
        self.setStyleSheet(status_banner_qss(variant))
        self._icon.load(icon_path(self._ICON_BY_VARIANT.get(variant, "alert-triangle")))
        self._label.setText(message)
        self.setVisible(True)


LOW_CHANGE_MESSAGE = f"This kiosk is low on change. Please pay the exact amount if you can. {MSG_UNGIVEN_CHANGE}"


class LowChangeBanner(StatusBanner):
    """Warning shown on idle and the homepage while the kiosk's max dispensable change is
    below the 'low_change_warning_threshold' setting."""

    def set_low(self, low: bool):
        self.show_message(LOW_CHANGE_MESSAGE if low else "", variant="warning")


BACKSPACE_KEY = "\u232b"  # ⌫


class CodeKeypad(QWidget):
    """On-screen keypad that types into a QLineEdit, for kiosk code entry
    (the touchscreen has no physical or OS keyboard). `target` is the entry,
    or a callable returning the entry to type into (None types nowhere).
    `keys` is the set of characters offered, laid out `columns` per row with a
    backspace key last unless `keys` places BACKSPACE_KEY itself. A `submit`
    button, if given, takes the cell after the last key.
    Emits `pressed` on every key so the screen can reset its timeout."""

    pressed = pyqtSignal()

    def __init__(self, target, keys: str, columns: int = 11, key_size: int = 48, submit=None, parent=None):
        super().__init__(parent)
        self._target = target
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        values = list(keys) if BACKSPACE_KEY in keys else list(keys) + [BACKSPACE_KEY]
        self.key_buttons = {}
        for i, value in enumerate(values):
            button = SecondaryButton(value)
            button.setMinimumSize(key_size, key_size)
            button.setFocusPolicy(Qt.NoFocus)  # keep the cursor in the target entry
            button.clicked.connect(lambda _, v=value: self._press(v))
            layout.addWidget(button, i // columns, i % columns)
            self.key_buttons[value] = button
        if submit is not None:
            submit.setMinimumSize(key_size, key_size)
            submit.setFocusPolicy(Qt.NoFocus)
            layout.addWidget(submit, len(values) // columns, len(values) % columns)

    def _press(self, value):
        target = self._target() if callable(self._target) else self._target
        if target is None:
            return
        if value == BACKSPACE_KEY:
            target.backspace()
        else:
            target.insert(value)
        self.pressed.emit()


class OtpEntryPanel(QWidget):
    """The wifi/email screens' 6-digit code entry: a field over a phone-style
    keypad whose last key is Send. Emits `submitted` with the field's text
    (Send or Enter) and `activity` on every key, for the screen's timeout."""

    submitted = pyqtSignal(str)
    activity = pyqtSignal()

    KEY_SIZE = 72

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("Enter your code")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;")

        self.input = QLineEdit()
        self.input.setPlaceholderText("6-digit code")
        self.input.setMaxLength(6)
        # Not QIntValidator: a code may start with 0
        self.input.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,6}")))
        self.input.setAlignment(Qt.AlignCenter)
        self.input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {COLORS['border_strong']}; border-radius: 6px; padding: 8px; "
            f"font-size: {FONT['size_xl']}px; font-weight: 700; color: {COLORS['text']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}"
        )
        self.input.returnPressed.connect(self._submit)

        self.send_button = PrimaryButton("Send")
        self.send_button.clicked.connect(self._submit)

        self.keypad = CodeKeypad(
            self.input, "123456789" + BACKSPACE_KEY + "0", columns=3,
            key_size=self.KEY_SIZE, submit=self.send_button,
        )
        self.keypad.pressed.connect(self.activity.emit)
        self.input.setFixedWidth(self.keypad.sizeHint().width())

        layout.addWidget(title)
        layout.addWidget(self.input, alignment=Qt.AlignCenter)
        layout.addWidget(self.keypad, alignment=Qt.AlignCenter)

    def _submit(self):
        self.submitted.emit(self.input.text())

    def clear(self):
        self.input.clear()
