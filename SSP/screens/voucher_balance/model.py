# screens/voucher_balance/model.py
#
# State and copy for the "Check voucher balance" screen, reached from the
# homepage. Read-only: it only calls VoucherManager.balance(), which shares
# the payment screen's wrong-code lockout (ADR 0003) and never changes a
# Voucher's value or expiry.
#
# Pure Python on purpose (no PyQt import), like screens/voucher/model.py, so it
# is directly unit-testable. Only the remaining value and expiry are kept, and
# clear() wipes them when the screen is left.

from database.db_manager import DatabaseManager
from managers.voucher_manager import VoucherManager, format_expiry

PESO = "₱"  # ₱
MSG_EMPTY = "Please enter your voucher code."


class VoucherBalanceModel:
    FOUND = "found"
    FAILED = "failed"
    EMPTY = "empty"

    def __init__(self, voucher_manager=None):
        self.voucher_manager = voucher_manager or VoucherManager(DatabaseManager())
        self.clear()

    def clear(self):
        self.state = self.EMPTY
        self.remaining = 0
        self.expires_at = None
        self.message = ""
        self.locked = False

    def check(self, raw_code):
        """Look up a typed code (or a 'V1:' payload). Blank input isn't a guess,
        so it never reaches the lookup or the lockout."""
        self.clear()
        if not (raw_code or "").strip():
            self.state = self.FAILED
            self.message = MSG_EMPTY
            return
        result = self.voucher_manager.balance(raw_code)
        if result.success:
            self.state = self.FOUND
            self.remaining = result.remaining
            self.expires_at = result.expires_at
        else:
            self.state = self.FAILED
            self.message = result.message
            self.locked = result.locked

    # ---- copy -----------------------------------------------------------

    @property
    def found(self) -> bool:
        return self.state == self.FOUND

    def amount_text(self) -> str:
        return f"{PESO}{self.remaining}" if self.found else ""

    def expiry_text(self) -> str:
        if not self.found or self.expires_at is None:
            return ""
        return f"Valid until {format_expiry(self.expires_at)}"
