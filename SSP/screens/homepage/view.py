# screens/landing/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QStackedLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))


class MethodCard(QFrame):
    """A clickable card representing an upload/scan method."""
    clicked = pyqtSignal(str)

    def __init__(self, method_key, title, description, parent=None):
        super().__init__(parent)
        self.method_key = method_key
        self.setCursor(Qt.PointingHandCursor)
       # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
       # self.setMinimumSize(200, 160)
        self.setFixedSize(300,200)
        self.setStyleSheet(self._normal_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "color: #36454F; font-size: 24px; font-weight: bold; background: transparent; border: none;"
        )
        title_label.setWordWrap(True)

        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            "color: #36454F; font-size: 14px; background: transparent; border: none;"
        )

        layout.addStretch(1)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addStretch(1)

    def _normal_style(self):
        return """
            MethodCard {
                background-color: white;
                border: 2px solid #d9d9d9;
                border-radius: 14px;
            }
        """

    def _hover_style(self):
        return """
            MethodCard {
                background-color: #f5f5f5;
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
            self.clicked.emit(self.method_key)
        super().mousePressEvent(event)


class HomepageScreenView(QWidget):
    """The user interface for the Landing (upload method selection) screen. Contains no logic."""
    
    method_card_clicked = pyqtSignal(str)  # method_key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QStackedLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setStackingMode(QStackedLayout.StackAll)
        self.setLayout(main_layout)

        # Background
        self.background_label = QLabel()
        self._load_background_image()

        # Foreground
        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")
        fg_layout = QVBoxLayout(foreground_widget)
        fg_layout.setContentsMargins(120, 40, 120, 30)
        fg_layout.setSpacing(12)

        title = QLabel("Select Upload Method")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #36454F; font-size: 24px; font-weight: bold;")

        subtitle = QLabel("Please select the desired file upload method or the scanning function.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #36454F; font-size: 18px;")

        disclaimer = QLabel("Disclaimer: This kiosk only accepts files in the PDF format.")
        disclaimer.setAlignment(Qt.AlignCenter)
        disclaimer.setStyleSheet("color: #36454F; font-size: 15px; font-weight: bold;")

        fg_layout.addSpacing(52)
        fg_layout.addWidget(title)
        fg_layout.addSpacing(12)
        fg_layout.addWidget(subtitle)
        fg_layout.addWidget(disclaimer)
        fg_layout.addSpacing(40)

        # Cards grid
        grid = QGridLayout()
        # grid.setSpacing(20)

        grid.setHorizontalSpacing(15)   # distance between USB, WiFi, Email
        grid.setVerticalSpacing(15)  

        self.usb_card = MethodCard('usb', "USB", "Upload files via USB.")
        self.wifi_card = MethodCard('wifi', "WiFi", 'Connect to the local network:\n"usc_printer_kiosk"')
        self.email_card = MethodCard('email', "Email", "Email address:\nprinter_kiosk@usc.edu.ph")
        self.scanner_card = MethodCard('scanner', "Scanner", "Scan documents via the printer's built-in scanner.")

        for card in (self.usb_card, self.wifi_card, self.email_card, self.scanner_card):
            card.clicked.connect(self.method_card_clicked.emit)

        grid.addWidget(self.usb_card, 0, 0)
        grid.addWidget(self.wifi_card, 0, 1)
        grid.addWidget(self.email_card, 0, 2)
        grid.addWidget(self.scanner_card, 1, 1, Qt.AlignTop | Qt.AlignHCenter)

      #  grid.setColumnStretch(0, 1)
      #  grid.setColumnStretch(1, 1)
      #  grid.setColumnStretch(2, 1)

      #  fg_layout.addLayout(grid, 1)
        grid_wrapper = QHBoxLayout()
        grid_wrapper.addStretch()
        grid_wrapper.addLayout(grid)
        grid_wrapper.addStretch()
        fg_layout.addLayout(grid_wrapper)


        main_layout.addWidget(self.background_label)
        main_layout.addWidget(foreground_widget)
        main_layout.setCurrentWidget(foreground_widget)

    def _load_background_image(self):
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'upload_method_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'")
            self.background_label.setStyleSheet("background-color: #ffffff;")

