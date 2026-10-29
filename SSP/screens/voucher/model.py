# screens/voucher/model.py
#
# State and copy for the voucher-issued screen, shown after change dispensing
# when the kiosk owed more change than it could dispense (ADR 0003), or when a
# customer abandoned a payment with cash in (reason UNSPENT).
#
# Pure Python on purpose (no PyQt import), like ScannerManager, so it is
# directly unit-testable. It copies the fields it needs out of the
# IssuedVoucher instead of keeping the object, and clear() wipes them, so the
# raw code lives only as long as the screen is showing it.

PESO = "\u20b1"  # ₱ (print_options already renders this glyph)
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


class VoucherModel:
    ISSUED = "issued"
    FAILED = "failed"
    EMPTY = "empty"

    # Why the Voucher was issued
    CHANGE = "change"    # change the hoppers couldn't give (a Shortfall)
    REFUND = "refund"    # a paid-for digital copy that couldn't be delivered
    UNSPENT = "unspent"  # cash put in for a payment that wasn't completed

    def __init__(self):
        self.clear()

    def clear(self):
        self.state = self.EMPTY
        self.reason = self.CHANGE
        self.value = 0
        self.display_code = ""
        self.qr_bytes = None
        self.expires_at = None

    # ---- loading --------------------------------------------------------

    def set_voucher(self, voucher, reason=CHANGE):
        """Show a successfully issued voucher (an IssuedVoucher)."""
        self.state = self.ISSUED
        self.reason = reason
        self.value = int(voucher.value)
        self.display_code = voucher.display_code
        self.qr_bytes = voucher.qr_bytes
        self.expires_at = voucher.expires_at

    def set_failure(self, amount, reason=CHANGE):
        """The voucher could not be saved, so no code exists. The customer is
        told the amount and sent to the attendant."""
        self.clear()
        self.state = self.FAILED
        self.reason = reason
        self.value = int(round(amount))

    # ---- copy -----------------------------------------------------------

    @property
    def has_code(self) -> bool:
        return self.state == self.ISSUED and bool(self.display_code)

    @property
    def has_qr(self) -> bool:
        return self.has_code and bool(self.qr_bytes)

    def title(self) -> str:
        if self.state == self.FAILED:
            return "We couldn't issue your voucher"
        if self.reason == self.REFUND:
            return "Here's your refund voucher"
        return "Here's your voucher" if self.reason == self.UNSPENT else "Here's your change voucher"

    def body(self) -> str:
        amount = f"{PESO}{self.value}"
        if self.reason == self.REFUND:
            if self.state == self.FAILED:
                return (
                    f"We couldn't prepare your digital copy and couldn't issue a voucher for the "
                    f"{amount} fee. Please contact the attendant and mention this amount."
                )
            return (
                f"We couldn't prepare your digital copy, so we've issued a voucher worth "
                f"{amount} for the fee."
            )
        if self.reason == self.UNSPENT:
            if self.state == self.FAILED:
                return (
                    f"Your payment wasn't finished and we couldn't issue a voucher for the "
                    f"{amount} you put in. Please contact the attendant and mention this amount."
                )
            return (
                f"Your payment wasn't finished, so we've issued a voucher worth {amount} "
                "for the money you put in."
            )
        if self.state == self.FAILED:
            return (
                f"We owe you {amount} in change but couldn't give it to you. "
                "Please contact the attendant and mention this amount."
            )
        return (
            f"We couldn't dispense all of your change, so we've issued a voucher "
            f"worth {amount}."
        )

    def footnote(self) -> str:
        if not self.has_code:
            return ""
        return (
            f"Enter this code at payment to use it on any future print. "
            f"Valid until {self._expiry_text()}. "
            "This code is shown only once, so take a photo or write it down."
        )

    def button_text(self) -> str:
        return "I've saved it, continue" if self.has_code else "Continue"

    def _expiry_text(self) -> str:
        d = self.expires_at
        # Not %B: QApplication applies the system locale, and this copy is English.
        return f"{MONTHS[d.month - 1]} {d.day}, {d.year}" if d else "the date shown by the attendant"
