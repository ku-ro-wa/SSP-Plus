from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT
from ui.widgets import DangerButton, Header


class ThankYouScreenView(QWidget):
    """View for the Thank You screen - handles UI components and presentation."""

    # Signals for user interactions
    admin_override_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface for the screen."""
        # Built here, applied on the controller (self.setLayout(self.view.main_layout)).
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.main_layout.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(60, 40, 60, 40)
        body_layout.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(body, 1)

        self.status_label = QLabel("Thank you for printing with us")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_display']}px; font-weight: 700;"
        )

        self.subtitle_label = QLabel("You may now remove your USB")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_xl']}px;"
        )

        # --- Admin Override Button (hidden by default, shown for errors) ---
        self.admin_override_button = DangerButton("Admin Override")
        self.admin_override_button.setMinimumHeight(50)
        self.admin_override_button.setMaximumWidth(240)
        self.admin_override_button.clicked.connect(self.admin_override_clicked.emit)
        self.admin_override_button.hide()

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.admin_override_button)
        button_layout.addStretch()

        body_layout.addStretch(1)
        body_layout.addWidget(self.status_label)
        body_layout.addWidget(self.subtitle_label)
        body_layout.addSpacing(40)
        body_layout.addLayout(button_layout)
        body_layout.addStretch(1)

    def update_status(self, status_text, subtitle_text, status_style):
        """Updates the status and subtitle labels with the provided text and style."""
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(status_style)
        self.subtitle_label.setText(subtitle_text)

    def show_admin_override_button(self):
        """Shows the admin override button."""
        self.admin_override_button.show()

    def hide_admin_override_button(self):
        """Hides the admin override button."""
        self.admin_override_button.hide()
