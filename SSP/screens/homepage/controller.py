from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from .model import HomepageModel
from .view import HomepageScreenView


class HomepageController(QWidget):
    """Manages the Landing (upload method selection) screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = HomepageModel()
        self.view = HomepageScreenView()

        # Setup timeout timer (1 minute), matches other screens
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""

        self.view.method_card_clicked.connect(self._handle_method_selected)
        self.view.method_card_clicked.connect(self._reset_timeout)

        self.model.method_selected.connect(self._route_method)

    def _handle_method_selected(self, method_key):
        """Passes the selected method to the model."""
        self.model.select_method(method_key)

    def _route_method(self, method_key):
        """Routes to the correct screen based on the selected method."""
        if method_key == 'usb':
            self.main_app.show_screen('usb')
        elif method_key == 'wifi':
            # TODO: Wire up Wi-Fi transfer flow (project_objectives.txt module 5)
           # print("Landing screen: WiFi method selected — not implemented yet")
            self.main_app.show_screen('wifi')
        elif method_key == 'email':
            # TODO: Wire up email submission flow (project_objectives.txt module 6)
            self.main_app.show_screen('email')
            print("Landing screen: Email method selected — not implemented yet")
        elif method_key == 'scanner':
            # TODO: Wire up scanner flow (project_objectives.txt module 8)
            print("Landing screen: Scanner method selected — not implemented yet")
            self.main_app.show_screen('scanner')
        else:
            print(f"Landing screen: Unknown method selected: {method_key}")

    def _go_back(self):
        """Navigates back to the idle screen."""
        self.main_app.show_screen('idle')

    # --- Public API for main_app ---

    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Homepage screen entered")
        self.timeout_timer.start(60000)
        print("Homepage screen timeout started (1 minute)")

    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("Homepage screen leaving")
        self.timeout_timer.stop()

    def _on_timeout(self):
        """Handle timeout - return to idle screen."""
        print("Homepage screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')

    def _reset_timeout(self):
        """Reset the timeout timer (call on user activity)."""
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)