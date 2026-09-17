# screens/idle/view.py

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.icons import icon
from ui.theme import COLORS, FONT
from ui.widgets import Header, SecondaryButton


class IdleScreenView(QWidget):
    """The user interface for the Idle Screen. Contains no logic."""
    screen_touched = pyqtSignal(object)  # Emits mouse event
    admin_button_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface components."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QFrame()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        frame_layout = QVBoxLayout(content)
        frame_layout.setContentsMargins(50, 50, 50, 30)
        frame_layout.setSpacing(10)
        outer_layout.addWidget(content, 1)

        # --- "Touch to Start" Label ---
        self.touch_to_start_label = QLabel("Touch Screen to Start")
        self.touch_to_start_label.setAlignment(Qt.AlignCenter)
        self.touch_to_start_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_display']}px; "
            f"font-weight: 700; padding: 20px;"
        )

        # --- Supported Formats Label ---
        self.bottom_info = QLabel("Supported Format: PDF Files Only")
        self.bottom_info.setAlignment(Qt.AlignCenter)
        self.bottom_info.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;"
        )

        # --- Layout Adjustments for Centering ---
        frame_layout.addStretch(2)
        frame_layout.addWidget(self.touch_to_start_label)
        frame_layout.addWidget(self.bottom_info)
        frame_layout.addStretch(2)

        # --- Admin Button ---
        self.admin_button = SecondaryButton("Admin")
        self.admin_button.setIcon(icon('admin'))
        self.admin_button.setFixedSize(100, 36)
        self.admin_button.clicked.connect(self.admin_button_clicked.emit)

        admin_layout = QHBoxLayout()
        admin_layout.addStretch(1)
        admin_layout.addWidget(self.admin_button)
        frame_layout.addLayout(admin_layout)

    def mousePressEvent(self, event):
        """Handles mouse press events and emits signal."""
        self.screen_touched.emit(event)

    def get_admin_button_geometry(self):
        """Returns the geometry of the admin button for touch validation."""
        return self.admin_button.geometry()
