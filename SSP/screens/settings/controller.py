# screens/settings/controller.py

from PyQt5.QtWidgets import QGridLayout, QWidget

from .model import SettingsModel
from .view import SettingsScreenView


class SettingsController(QWidget):
    """Kiosk Admin's runtime settings (issue #106), reached from the admin screen.
    No timeout_policy: like admin, it stays until the operator leaves."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.model = SettingsModel(main_app.admin_screen.db_manager)
        self.view = SettingsScreenView()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self.view.back_clicked.connect(lambda: self.main_app.show_screen('admin'))
        self.view.save_clicked.connect(self._save)

    def on_enter(self):
        self.view.clear_status()
        self.view.set_entries(self.model.entries())

    def on_leave(self):
        pass

    def _save(self, raw_values):
        errors = self.model.save(raw_values)
        if errors:
            self.view.show_errors(errors)
        else:
            self.view.set_entries(self.model.entries())  # show the stored (normalised) values
            self.view.show_saved()
