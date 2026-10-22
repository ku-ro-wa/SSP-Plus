# screens/voucher/controller.py
#
# Sits between change dispensing and the thank-you screen. The payment model
# hands it an IssuedVoucher (or a failure amount) via show_issued() /
# show_failure(), navigates here, and this screen calls
# PaymentModel.continue_to_thank_you() when the customer is done, which is
# what actually starts the print job. A Voucher for an abandoned payment's cash
# (reason 'unspent') passes on_continue instead, to go where the customer was
# going; nothing is printed. The print therefore waits for the
# customer to see their code, and main_app's "print finished on the wrong
# screen" redirect can't yank them off it.

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from .model import VoucherModel
from .view import VoucherScreenView

# Longer than the usual 60s screens: this is the only time the code is shown,
# and the customer needs time to photograph it.
TIMEOUT_MS = 180000


class VoucherController(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = VoucherModel()
        self.view = VoucherScreenView()

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._continue)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._continuing = False
        self._on_continue = None
        self.view.continue_clicked.connect(self._continue)

    # --- Public API for the payment model ---

    def show_issued(self, voucher, reason=VoucherModel.CHANGE, on_continue=None):
        self._continuing = False
        self._on_continue = on_continue
        self.model.set_voucher(voucher, reason)
        self.view.render(self.model)

    def show_failure(self, amount, reason=VoucherModel.CHANGE, on_continue=None):
        self._continuing = False
        self._on_continue = on_continue
        self.model.set_failure(amount, reason)
        self.view.render(self.model)

    # --- Lifecycle (called by main_app.show_screen) ---

    def on_enter(self):
        print("Voucher screen entered")
        # show_screen() just started the usual 60s countdown; show this screen's
        # longer one instead, so the customer can see how long they have.
        self.main_app.start_global_countdown(TIMEOUT_MS // 1000)
        self.timeout_timer.start(TIMEOUT_MS)

    def on_leave(self):
        print("Voucher screen leaving")
        self.timeout_timer.stop()
        # The code must not outlive the screen.
        self.model.clear()
        self.view.clear()

    # --- Internals ---

    def _continue(self):
        # Guard: a tap racing the timeout (or a double tap) must not emit
        # payment_completed twice, which would print the job twice.
        if self._continuing:
            return
        self._continuing = True
        self.timeout_timer.stop()
        self.view.set_busy()
        on_continue, self._on_continue = self._on_continue, None
        if on_continue:
            on_continue()
        else:
            self.main_app.payment_screen.model.continue_to_thank_you()
