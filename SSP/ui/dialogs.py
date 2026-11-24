# ui/dialogs.py
"""Pop-up message boxes for the kiosk.

Frameless: a normal dialog gets the window manager's title bar, and on the kiosk
maximising then minimising one left the customer on the Pi desktop, outside the app.
With no title bar there is nothing to minimise or close; the box is left only through
its own buttons. Themed like the rest of the app, with touch-sized buttons (the
native ones were 32 px tall).

Use these instead of QMessageBox's static helpers or a bare QMessageBox.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QPushButton

from ui.theme import COLORS, FONT, RADIUS

KIOSK_DIALOG_FLAGS = Qt.Dialog | Qt.FramelessWindowHint
DIALOG_BUTTON_HEIGHT = 56
DIALOG_BUTTON_MIN_WIDTH = 160

_QSS = f"""
QMessageBox {{
    background-color: {COLORS["bg"]};
    border: 2px solid {COLORS["text_muted"]};
}}
QMessageBox QLabel#qt_msgbox_label {{
    color: {COLORS["text"]};
    font-size: {FONT["size_lg"]}px;
    font-weight: 700;
    min-width: 460px;
}}
QMessageBox QLabel#qt_msgbox_informativelabel {{
    color: {COLORS["text"]};
    font-size: {FONT["size_md"]}px;
    min-width: 460px;
}}
QMessageBox QPushButton {{
    background-color: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-size: {FONT["size_md"]}px;
    font-weight: 600;
    border: 1px solid {COLORS["text_muted"]};
    border-radius: {RADIUS["md"]}px;
    padding: 0 {DIALOG_BUTTON_HEIGHT // 3}px;
    min-height: {DIALOG_BUTTON_HEIGHT}px;
    min-width: {DIALOG_BUTTON_MIN_WIDTH}px;
}}
QMessageBox QPushButton:pressed {{
    background-color: {COLORS["border"]};
}}
"""


class KioskMessageBox(QMessageBox):
    """A QMessageBox with no title bar. The title, which a title bar would have shown,
    is the box's heading instead, with `text` under it."""

    def __init__(self, parent=None, title="", text="", icon=QMessageBox.NoIcon):
        super().__init__(parent)
        # Modality first: QMessageBox.setWindowModality() resets the window flags
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(KIOSK_DIALOG_FLAGS)
        self.setStyleSheet(_QSS)
        self.setIcon(icon)
        self.setWindowTitle(title)
        self.setTextFormat(Qt.PlainText)
        if title:
            self.setText(title)
            self.setInformativeText(text)
        else:
            self.setText(text)

    def showEvent(self, event):
        # Buttons are created by addButton()/setStandardButtons() after __init__
        for button in self.findChildren(QPushButton):
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
        super().showEvent(event)


def _show(parent, title, text, icon):
    box = KioskMessageBox(parent, title, text, icon)
    box.addButton("OK", QMessageBox.AcceptRole)
    return box.exec_()


def information(parent, title, text):
    return _show(parent, title, text, QMessageBox.Information)


def warning(parent, title, text):
    return _show(parent, title, text, QMessageBox.Warning)


def critical(parent, title, text):
    return _show(parent, title, text, QMessageBox.Critical)
