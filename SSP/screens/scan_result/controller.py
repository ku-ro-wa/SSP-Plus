# screens/scan_result/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from managers.webapp_thread import scan_redeem_portal_url

from .model import ScanResultModel
from .view import ScanResultScreenView


class ScanResultController(QWidget):
    """Manages the post-scan Wi-Fi pickup screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = ScanResultModel()
        self.view = ScanResultScreenView()

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self.view.done_clicked.connect(self._handle_done)
        self.view.done_clicked.connect(self._reset_timeout)

    # --- Public API for main_app ---

    def set_session(self, session, pending_print=None):
        self.model.set_session(session, pending_print)
        self.view.set_otp(session.otp)
        self.view.set_continue_mode(self.model.has_pending_print())

    def _handle_done(self):
        if self.model.has_pending_print():
            pdf_data = self.model.pending_print['pdf_data']
            selected_pages = self.model.pending_print['selected_pages']
            self.main_app.printing_options_screen.set_pdf_data(pdf_data, selected_pages, "scanner")
            self.main_app.show_screen('printing_options')
        else:
            self.main_app.show_screen('homepage')

    def on_enter(self):
        print("Scan result screen entered")
        try:
            webapp_thread = getattr(self.main_app, "webapp_thread", None)
            tls = getattr(webapp_thread, "tls_enabled", None)
            self.view.set_portal_hint(scan_redeem_portal_url(tls=tls))
        except Exception as e:
            print(f"Could not resolve scan redeem portal URL: {e}")
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("Scan result screen leaving")
        self.timeout_timer.stop()

    def _on_timeout(self):
        print("⏰ Scan result screen timeout - returning to homepage")
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        if self.main_app.stacked_widget.currentWidget() is not self:
            return
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)
