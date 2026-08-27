# screens/usb/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

from ui.theme import COLORS, FONT
from ui.widgets import Header, BackButton, StatusBanner

STATUS_VARIANT_BY_KEY = {
    'monitoring': 'info',
    'success': 'success',
    'warning': 'warning',
    'error': 'error',
}


class USBScreenView(QWidget):
    """The user interface for the USB Screen. Contains no logic."""
    back_button_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.blink_timer = QTimer(self)
        self.setup_ui()
        self.setup_timers()

    def setup_ui(self):
        """Initializes the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

        main_layout.addWidget(Header())

        body_widget = QWidget()
        fg_layout = QVBoxLayout(body_widget)
        fg_layout.setContentsMargins(40, 30, 40, 30)
        fg_layout.setSpacing(15)
        main_layout.addWidget(body_widget, 1)

        # --- UI Elements ---
        title = QLabel("INSERT USB FLASHDRIVE")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_display']}px; font-weight: 700;"
        )
        title.setWordWrap(True)

        instruction = QLabel("The system will automatically detect your drive.")
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setWordWrap(True)
        instruction.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_lg']}px;"
        )
        instruction.setMaximumWidth(800)

        self.status_banner = StatusBanner()
        self._blink_effect = QGraphicsOpacityEffect(self.status_banner)
        self._blink_effect.setOpacity(1.0)
        self.status_banner.setGraphicsEffect(self._blink_effect)
        self._blink_opaque = True

        # Safety warning banner (hidden until a warning is raised).
        self.safety_warning_banner = StatusBanner()

        # Button Creation
        self.back_button = BackButton("Back to Main")

        # --- Layout Assembly ---
        fg_layout.addStretch(3)
        fg_layout.addWidget(title, 0, Qt.AlignCenter)
        fg_layout.addSpacing(10)
        fg_layout.addWidget(instruction, 0, Qt.AlignCenter)
        fg_layout.addStretch(1)

        status_layout = QHBoxLayout()
        status_layout.addStretch()
        status_layout.addWidget(self.status_banner)
        status_layout.addStretch()
        fg_layout.addLayout(status_layout)

        safety_layout = QHBoxLayout()
        safety_layout.addStretch()
        safety_layout.addWidget(self.safety_warning_banner)
        safety_layout.addStretch()
        fg_layout.addLayout(safety_layout)

        fg_layout.addSpacing(20)
        fg_layout.addStretch(4)

        nav_buttons_layout = QHBoxLayout()
        nav_buttons_layout.addWidget(self.back_button, 0, Qt.AlignLeft)
        nav_buttons_layout.addStretch()
        fg_layout.addLayout(nav_buttons_layout)

        # Connect button signals
        self.back_button.clicked.connect(self.back_button_clicked.emit)

    def setup_timers(self):
        """Sets up timers for the view."""
        self.blink_timer.timeout.connect(self.blink_status)

    def update_status_indicator(self, text, style_key, color_hex):
        """Updates the text and variant of the status banner."""
        variant = STATUS_VARIANT_BY_KEY.get(style_key, 'info')
        self.status_banner.show_message(text, variant)

    def blink_status(self):
        """Toggles the opacity of the status banner for a blinking effect."""
        self._blink_opaque = not self._blink_opaque
        self._blink_effect.setOpacity(1.0 if self._blink_opaque else 0.4)

    def start_blinking(self):
        """Starts the blinking effect."""
        self.blink_timer.start(700)

    def stop_blinking(self):
        """Stops the blinking effect."""
        self.blink_timer.stop()
        self._blink_opaque = True
        self._blink_effect.setOpacity(1.0)

    def show_message(self, title, text):
        """Shows a message to the user."""
        QMessageBox.information(self, title, text)

    def show_warning(self, title, text):
        """Shows a warning message to the user."""
        QMessageBox.warning(self, title, text)

    def show_safety_warning(self, message):
        """Shows a safety warning message."""
        self.safety_warning_banner.show_message(message, "error")

    def hide_safety_warning(self):
        """Hides the safety warning message."""
        self.safety_warning_banner.show_message("")
