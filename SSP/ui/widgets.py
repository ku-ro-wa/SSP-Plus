# ui/widgets.py
"""Shared, presentation-only widgets used by view.py files across screens.

No imports from managers/, database/, or any model — these are part of the
view layer, just factored out of per-screen duplication.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ui.icons import icon, icon_path, svg_widget
from ui.theme import (
    CARD_QSS, COLORS, FONT, HEADER_QSS, PRIMARY_BUTTON_QSS, RADIUS,
    SECONDARY_BUTTON_QSS, status_banner_qss,
)


class LogoMark(QFrame):
    """Small square brand tile, styled after Notion's icon-tile pattern."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setStyleSheet(
            f"background-color: {COLORS['text']}; border-radius: {RADIUS['sm']}px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        mark_label = QLabel("AIO")
        mark_label.setAlignment(Qt.AlignCenter)
        mark_label.setStyleSheet(
            f"color: {COLORS['bg']}; font-size: 9px; font-weight: 700; "
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
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(10)

        layout.addWidget(LogoMark())

        wordmark_label = QLabel("AIO SPARK")
        wordmark_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
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
        self.setFixedSize(300, 200)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

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
