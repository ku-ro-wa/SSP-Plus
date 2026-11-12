# screens/reports/controller.py

from PyQt5.QtWidgets import QGridLayout, QWidget

from .model import ReportsModel
from .view import ReportsScreenView


class ReportsController(QWidget):
    """Kiosk Admin's Reports (issue #130): what the dashboard's /accounting shows.
    No timeout_policy: like admin, it stays until the operator leaves."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.model = ReportsModel(main_app.admin_screen.db_manager)
        self.view = ReportsScreenView()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self.view.back_clicked.connect(lambda: self.main_app.show_screen('admin'))
        self.view.range_selected.connect(self._show_range)

    def on_enter(self):
        self._show_range("today")

    def on_leave(self):
        pass

    def _show_range(self, range_key):
        self.view.render(self.model.report(range_key))
