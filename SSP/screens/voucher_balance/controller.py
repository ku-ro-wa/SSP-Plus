# screens/voucher_balance/controller.py
#
# "Check voucher balance", reached from the homepage without starting a print
# job. Returns to the homepage on Back or after the usual 60s of inactivity.

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from .model import VoucherBalanceModel
from .view import VoucherBalanceScreenView

TIMEOUT_MS = 60000


class VoucherBalanceController(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = VoucherBalanceModel()
        self.view = VoucherBalanceScreenView()

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self.view.check_clicked.connect(self._handle_check)
        self.view.check_clicked.connect(self._reset_timeout)
        self.view.input_edited.connect(self._reset_timeout)
        self.view.back_button_clicked.connect(self._go_back)

    def _handle_check(self, code_text):
        self.model.check(code_text)
        self.view.render(self.model)

    def _go_back(self):
        self.main_app.show_screen('homepage')

    # --- Lifecycle (called by main_app.show_screen) ---

    def on_enter(self):
        print("Voucher balance screen entered")
        self.model.clear()
        self.view.clear()
        self.timeout_timer.start(TIMEOUT_MS)

    def on_leave(self):
        print("Voucher balance screen leaving")
        self.timeout_timer.stop()
        self.model.clear()
        self.view.clear()

    def _on_timeout(self):
        print("Voucher balance screen timeout - returning to homepage")
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        if self.main_app.stacked_widget.currentWidget() is not self:
            return
        self.timeout_timer.stop()
        self.timeout_timer.start(TIMEOUT_MS)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(TIMEOUT_MS // 1000)
