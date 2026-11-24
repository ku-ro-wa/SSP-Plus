# ui/dialogs.py
"""Pop-ups for the kiosk, drawn inside the app window instead of as separate windows.

A separate window gets the window manager's title bar, and on the kiosk maximising then
minimising one left the customer on the Pi desktop, outside the app. An overlay is part
of the main window, so there is nothing to minimise: it is a dimmed layer over the whole
screen (nothing underneath can be tapped) with a card in the middle, like the
"Still there?" prompt (ui/timeout_warning.py), and it is left only through its buttons.

OverlayDialog keeps QDialog's calling style, so callers don't change: exec_() waits
(in a local event loop) and returns QDialog.Accepted or QDialog.Rejected; accept(),
reject(), result() and the finished signal behave the same.

Use MessageDialog, or the warning/information/critical helpers, for messages and
questions, never QMessageBox (tests/test_kiosk_dialogs.py checks).
"""

from PyQt5.QtCore import QEvent, QEventLoop, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.theme import COLORS, FONT, RADIUS

DIALOG_BUTTON_HEIGHT = 56
CARD_WIDTH = 600

_BACKDROP_QSS = "QFrame#OverlayBackdrop { background-color: rgba(0, 0, 0, 140); }"
_CARD_QSS = f"""
QFrame#OverlayCard {{
    background-color: {COLORS["bg"]};
    border-radius: {RADIUS["lg"]}px;
}}
"""
_PRIMARY_QSS = f"""
QPushButton {{
    background-color: {COLORS["primary"]}; color: {COLORS["bg"]};
    font-size: {FONT["size_md"]}px; font-weight: 600;
    border: none; border-radius: {RADIUS["md"]}px; padding: 0 20px;
}}
QPushButton:pressed {{ background-color: {COLORS["primary_pressed"]}; }}
"""
_SECONDARY_QSS = f"""
QPushButton {{
    background-color: {COLORS["bg_subtle"]}; color: {COLORS["text"]};
    font-size: {FONT["size_md"]}px; font-weight: 600;
    border: 1px solid {COLORS["border_strong"]}; border-radius: {RADIUS["md"]}px; padding: 0 20px;
}}
QPushButton:pressed {{ background-color: {COLORS["border"]}; }}
"""


class OverlayDialog(QFrame):
    """A dimmed layer over the whole app window with a card (`self.card`, laid out by
    `self.card_layout`) in the middle. Behaves like a modal QDialog for its callers."""

    finished = pyqtSignal(int)

    _open = []  # open overlays, newest last

    def __init__(self, parent=None, card_width=CARD_WIDTH):
        host = parent.window() if parent is not None else None
        super().__init__(host)
        if host is None:
            # No app window to sit in (a test, or a screen built on its own). Still no
            # title bar; there is no kiosk window around it to escape from.
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        else:
            host.installEventFilter(self)  # follow the window's size
        self.setObjectName("OverlayBackdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_BACKDROP_QSS)
        self._result = QDialog.Rejected
        self._loop = None

        # Centred with stretches, not setAlignment(): an aligned layout sizes wrapped
        # text by its one-line height and cuts the rest off (see ui/widgets.py's Card).
        outer = QVBoxLayout(self)
        middle = QHBoxLayout()
        self.card = QFrame()
        self.card.setObjectName("OverlayCard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        self.card.setStyleSheet(_CARD_QSS)
        self.card.setFixedWidth(card_width)
        middle.addStretch(1)
        middle.addWidget(self.card)
        middle.addStretch(1)
        outer.addStretch(1)
        outer.addLayout(middle)
        outer.addStretch(1)
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(36, 32, 36, 32)
        self.card_layout.setSpacing(12)
        self.hide()

    # ---- QDialog-style API -------------------------------------------------

    def exec_(self):
        self.open()
        self._loop = QEventLoop()
        self._loop.exec_()
        self._loop = None
        return self._result

    exec = exec_

    def open(self):
        host = self.parentWidget()
        if host is not None:
            self.setGeometry(host.rect())
        self.show()
        self.raise_()
        OverlayDialog._open.append(self)

    def done(self, result):
        if self not in OverlayDialog._open:
            return  # already closed
        OverlayDialog._open.remove(self)
        self._result = result
        self.hide()
        self.finished.emit(result)
        if self._loop is not None:
            self._loop.quit()
        QTimer.singleShot(0, self.deleteLater)

    def accept(self):
        self.done(QDialog.Accepted)

    def reject(self):
        self.done(QDialog.Rejected)

    def result(self):
        return self._result

    @classmethod
    def active(cls):
        """The overlay on top, or None (for tests: QApplication.activeModalWidget()
        doesn't see an overlay)."""
        return cls._open[-1] if cls._open else None

    # ---- Qt plumbing ----------------------------------------------------------

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(watched.rect())
        return False

    def mousePressEvent(self, event):
        event.accept()  # a tap on the backdrop does nothing (and doesn't reach the screen)


class MessageDialog(OverlayDialog):
    """A heading, a message and a row of buttons. add_button() in display order; the
    `primary` one is green. exec_() returns Accepted for any button but one added with
    `cancel=True`; clicked_button() says which was tapped."""

    def __init__(self, parent=None, title="", text=""):
        super().__init__(parent)
        self._clicked = None

        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;"
        )
        self.text_label = QLabel(text)
        self.text_label.setTextFormat(Qt.PlainText)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;"
        )
        self.card_layout.addWidget(self.title_label)
        self.card_layout.addWidget(self.text_label)
        self.card_layout.addSpacing(12)

        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(12)
        self.card_layout.addLayout(self._buttons)

    def add_button(self, text, primary=False, cancel=False):
        button = QPushButton(text)
        button.setMinimumHeight(DIALOG_BUTTON_HEIGHT)
        button.setFocusPolicy(Qt.NoFocus)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(_PRIMARY_QSS if primary else _SECONDARY_QSS)
        button.clicked.connect(lambda: self._on_clicked(button, cancel))
        self._buttons.addWidget(button, 1)
        return button

    def buttons(self):
        return [self._buttons.itemAt(i).widget() for i in range(self._buttons.count())]

    def text(self):
        return f"{self.title_label.text()}\n{self.text_label.text()}"

    def clicked_button(self):
        return self._clicked

    def _on_clicked(self, button, cancel):
        self._clicked = button
        self.reject() if cancel else self.accept()


def _show(parent, title, text):
    dialog = MessageDialog(parent, title, text)
    dialog.add_button("OK", primary=True)
    return dialog.exec_()


def information(parent, title, text):
    return _show(parent, title, text)


def warning(parent, title, text):
    return _show(parent, title, text)


def critical(parent, title, text):
    return _show(parent, title, text)
