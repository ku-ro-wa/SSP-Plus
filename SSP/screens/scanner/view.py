# screens/scanner/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QStackedLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


class ClickableCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scanCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._normal_style())

    def _normal_style(self):
        return """
            #scanCard {
                background-color: white;
                border: 2px solid #d9d9d9;
                border-radius: 14px;
            }
        """

    def _hover_style(self):
        return """
            #scanCard {
                background-color: #f7f7f7;
                border: 2px solid #1e440a;
                border-radius: 14px;
            }
        """

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_style())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._normal_style())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ScannerScreenView(QWidget):
    """The user interface for the Scanner screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    start_scan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QStackedLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setStackingMode(QStackedLayout.StackAll)
        self.setLayout(main_layout)

        self.background_label = QLabel()
        self._load_background_image()

        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")
        fg_layout = QVBoxLayout(foreground_widget)
        fg_layout.setContentsMargins(0, 0, 0, 30)
        fg_layout.setSpacing(0)

        fg_layout.addSpacing(80)
        self.back_button = QPushButton("← Back")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.setStyleSheet(self.get_back_button_style())
        self.back_button.clicked.connect(self.back_button_clicked.emit)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(20, 20, 20, 0)
        top_row.addWidget(self.back_button)
        top_row.addStretch()

        fg_layout.addLayout(top_row)

        # Body
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(60, 25, 60, 0)
        body_layout.setSpacing(10)

        guide_title = QLabel("Usage Guide:")
        guide_title.setAlignment(Qt.AlignCenter)
        guide_title.setStyleSheet("color: #36454F; font-size: 24px; font-weight: bold;")

        guide_text = QLabel(
            '1. Place your document face-down on the scanner glass.<br><br>'
            '2. Press "Start Scan" below. Your document will be scanned<br>'
            'and prepared for printing.<br><br>'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #36454F; font-size: 16px; line-height: 1.5;")

        body_layout.addSpacing(20)
        body_layout.addWidget(guide_title)
        body_layout.addSpacing(26)
        body_layout.addWidget(guide_text)
        body_layout.addSpacing(30)

        # Single Start Scan card
        cards_row = QHBoxLayout()
        cards_row.addStretch()

        scan_card = ClickableCard()
        scan_card.setFixedSize(300, 200)
        scan_card.clicked.connect(self.start_scan_clicked.emit)

        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(5, 5, 5, 5)
        scan_title = QLabel("Start Scan")
        scan_title.setAlignment(Qt.AlignCenter)
        scan_title.setStyleSheet("color: #36454F; font-size: 22px; font-weight: bold; background: transparent; border: none;")
        scan_desc = QLabel("Tap to begin scanning your document.")
        scan_desc.setAlignment(Qt.AlignCenter)
        scan_desc.setWordWrap(True)
        scan_desc.setStyleSheet("color: #36454F; font-size: 13px; background: transparent; border: none;")

        scan_layout.addStretch()
        scan_layout.addWidget(scan_title)
        scan_layout.addSpacing(8)
        scan_layout.addWidget(scan_desc)
        scan_layout.addStretch()

        cards_row.addWidget(scan_card)
        cards_row.addStretch()

        body_layout.addLayout(cards_row)

        # Status/error message label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #dc3545; font-size: 14px; font-weight: bold; margin-top: 12px;")
        body_layout.addWidget(self.status_label)

        body_layout.addStretch(1)
        fg_layout.addLayout(body_layout, 1)

        main_layout.addWidget(self.background_label)
        main_layout.addWidget(foreground_widget)
        main_layout.setCurrentWidget(foreground_widget)

    def _load_background_image(self):
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'scanner_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'")
            self.background_label.setStyleSheet("background-color: #ffffff;")

    def show_status(self, message, is_error=True):
        color = "#dc3545" if is_error else "#28a745"
        self.status_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold; margin-top: 12px;")
        self.status_label.setText(message)

    def get_back_button_style(self):
        return """
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 14px;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """