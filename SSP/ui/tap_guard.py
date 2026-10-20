# ui/tap_guard.py
"""Drop taps that land right after a screen change.

The kiosk's touch panel sometimes reports one light press as two taps. The first
tap changes the screen; the second lands on whatever button the new screen has
in the same spot (file_browser's "Set Print Options" sits where print_options'
"Continue to Payment" does), so a customer skips a screen. Nobody taps a screen's
buttons within a few hundred ms of it appearing, so taps in that window are dropped.
"""

from PyQt5.QtCore import QElapsedTimer, QEvent, QObject

SCREEN_CHANGE_GUARD_MS = 300

_TAP_EVENTS = {
    QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick,
    QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd,
}


class ScreenChangeTapGuard(QObject):
    """Application event filter: call arm() on every screen change."""

    def __init__(self, guard_ms=SCREEN_CHANGE_GUARD_MS, parent=None):
        super().__init__(parent)
        self.guard_ms = guard_ms
        self._since_change = QElapsedTimer()

    def arm(self):
        self._since_change.start()

    def is_guarding(self):
        return self._since_change.isValid() and self._since_change.elapsed() < self.guard_ms

    def eventFilter(self, obj, event):
        return event.type() in _TAP_EVENTS and self.is_guarding()
