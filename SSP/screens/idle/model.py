# screens/idle/model.py

from PyQt5.QtCore import QObject, pyqtSignal


class IdleModel(QObject):
    """Handles the data and business logic for the idle screen."""
    show_message = pyqtSignal(str, str)        # Emits message title and text

    def __init__(self):
        super().__init__()

    def validate_touch_interaction(self, event_pos, admin_button_geometry):
        """Validates if the touch interaction should start printing or not."""
        # If the touch is on the admin button, don't start printing
        if admin_button_geometry and admin_button_geometry.contains(event_pos):
            return False
        return True
