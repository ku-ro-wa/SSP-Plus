"""Drag/touch scrolling for lists on the touchscreen kiosk (file browser, print options)."""
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QTouchEvent
from PyQt5.QtWidgets import QScrollArea

from ui.theme import COLORS, RADIUS

SCROLLBAR_QSS = f"""
QScrollArea {{ border: none; background-color: transparent; }}
QScrollBar:vertical {{
    background-color: {COLORS["bg_subtle"]}; width: 28px; border: none;
    border-radius: {RADIUS["md"]}px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background-color: {COLORS["border_strong"]}; border: none; border-radius: {RADIUS["md"]}px;
    min-height: 30px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {COLORS["text_muted"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: transparent; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


class DragScrollArea(QScrollArea):
    """Custom scroll area that supports mouse/touch drag scrolling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dragging = False
        self.last_drag_position = QPoint()
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_drag_position = event.globalPos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            delta = event.globalPos() - self.last_drag_position
            scroll_value = self.verticalScrollBar().value() - delta.y()
            self.verticalScrollBar().setValue(scroll_value)
            self.last_drag_position = event.globalPos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Handle mouse wheel scrolling."""
        delta = event.angleDelta().y()
        scroll_amount = delta // 8
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - scroll_amount
        )
        event.accept()

    def enterEvent(self, event):
        if not self.dragging:
            self.setCursor(Qt.OpenHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.dragging:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    def touchEvent(self, event):
        """Handle touch events for touch screens."""
        if event.touchPoints():
            touch_point = event.touchPoints()[0]
            if event.type() == QTouchEvent.TouchBegin:
                self.dragging = True
                self.last_drag_position = touch_point.pos().toPoint()
            elif event.type() == QTouchEvent.TouchUpdate and self.dragging:
                delta = touch_point.pos().toPoint() - self.last_drag_position
                scroll_value = self.verticalScrollBar().value() - delta.y()
                self.verticalScrollBar().setValue(scroll_value)
                self.last_drag_position = touch_point.pos().toPoint()
            elif event.type() == QTouchEvent.TouchEnd:
                self.dragging = False
        event.accept()
