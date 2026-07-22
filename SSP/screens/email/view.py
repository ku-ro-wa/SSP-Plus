# screens/email/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QStackedLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QIntValidator

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

class ClickableCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cancelCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._normal_style())

    def _normal_style(self):
        return """
            #cancelCard {
                background-color: white;
                border: 2px solid #d9d9d9;
                border-radius: 14px;
            }
        """

    def _hover_style(self):
        return """
            #cancelCard {
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

class EmailScreenView(QWidget):
    """The user interface for the Email Upload screen. Contains no logic."""
    cancel_card_clicked = pyqtSignal()
    back_button_clicked = pyqtSignal()
    send_otp_clicked = pyqtSignal(str)
    send_otp_clicked = pyqtSignal(str)  # otp_text

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
            '1. Send your PDF file/s to <b>printer_kiosk@usc.edu.ph</b>.<br><br>'
            '2. Scan the provided QR code or input the provided OTP to proceed to the printing configuration.'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #36454F; font-size: 16px; line-height: 1.5;")

        body_layout.addSpacing(20)
        body_layout.addWidget(guide_title)
        body_layout.addSpacing(26)
        body_layout.addWidget(guide_text)
        body_layout.addSpacing(50)

        # Cancel / Enter Code cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)
        cards_row.addStretch()

        cancel_card = ClickableCard()
        cancel_card.setFixedSize(300, 200)
        cancel_card.clicked.connect(self.cancel_card_clicked.emit)

        cancel_layout = QVBoxLayout(cancel_card)
        cancel_layout.setContentsMargins(5, 5, 5, 5)

        cancel_title = QLabel("QR Code Scan")
        cancel_title.setAlignment(Qt.AlignCenter)
        cancel_title.setStyleSheet(
            "color: #36454F; font-size: 22px; font-weight: bold; background: transparent; border: none;"
        )

        cancel_desc = QLabel(
            'Scan QR code to access files. '
            
        )
        cancel_desc.setAlignment(Qt.AlignCenter)
        cancel_desc.setWordWrap(True)
        cancel_desc.setStyleSheet(
            "color: #36454F; font-size: 13px; background: transparent; border: none;"
        )

        cancel_layout.addStretch()
        cancel_layout.addWidget(cancel_title)
        cancel_layout.addSpacing(8)
        cancel_layout.addWidget(cancel_desc)
        cancel_layout.addStretch()

        enter_code_card = QFrame()
        enter_code_card.setFixedSize(300, 200)
        enter_code_card.setStyleSheet(self._card_style())
        enter_layout = QVBoxLayout(enter_code_card)
        enter_layout.setContentsMargins(5, 5, 5, 5)
        enter_title = QLabel("\nEnter Code")
        enter_title.setAlignment(Qt.AlignCenter)
        enter_title.setStyleSheet("color: #36454F; font-size: 22px; font-weight: bold; background: transparent; border: none;")
        enter_desc = QLabel("Alternatively, enter the OTP that was provided to you.")
        enter_desc.setAlignment(Qt.AlignCenter)
        enter_desc.setWordWrap(True)
        enter_desc.setStyleSheet("color: #36454F; font-size: 13px; background: transparent; border: none;")

        otp_row = QHBoxLayout()
        self.otp_input = QLineEdit()
        self.otp_input.setPlaceholderText("6-digit code")
        self.otp_input.setMaxLength(6)
        self.otp_input.setValidator(QIntValidator(0, 999999))
        self.otp_input.setAlignment(Qt.AlignCenter)
        self.otp_input.setStyleSheet(self._otp_input_style())
        self.send_button = QPushButton("Send")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet(self._send_button_style())
        self.send_button.clicked.connect(lambda: self.send_otp_clicked.emit(self.otp_input.text()))
        self.otp_input.returnPressed.connect(lambda: self.send_otp_clicked.emit(self.otp_input.text()))
        otp_row.addWidget(self.otp_input)
        otp_row.addWidget(self.send_button)

        enter_layout.addStretch()

        enter_layout.addWidget(enter_title)
        enter_layout.addSpacing(8)
        enter_layout.addWidget(enter_desc)

        enter_layout.addStretch()

        enter_layout.addLayout(otp_row)

        cards_row.addWidget(cancel_card)
        cards_row.addWidget(enter_code_card)
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
        image_path = os.path.join(base_dir, 'assets', 'email_screen background.png')
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

    def clear_otp_input(self):
        self.otp_input.clear()


    def _card_style(self):
        return """
            QFrame {
                background-color: white;
                border: 2px solid #d9d9d9;
                border-radius: 14px;
            }
        """

    def _send_button_style(self):
        return """
            QPushButton {
                background-color: #1e440a; color: white; font-size: 13px; font-weight: bold;
                border: none; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background-color: #2a5d1a; }
        """

    def _otp_input_style(self):
        return """
            QLineEdit {
                border: 2px solid #1e440a; border-radius: 6px; padding: 6px;
                font-size: 14px; color: #36454F;
            }
            QLineEdit:focus { border: 2px solid #2a5d1a; }
        """
    
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
