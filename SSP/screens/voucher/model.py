# screens/voucher/model.py
#
# State and copy for the voucher-issued screen, shown after change dispensing
# when the kiosk owed more change than it could dispense (ADR 0003).
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

    def __init__(self):
        self.clear()

    def clear(self):
        self.state = self.EMPTY
        self.value = 0
        self.display_code = ""
        self.qr_bytes = None
        self.expires_at = None

    # ---- loading --------------------------------------------------------

    def set_voucher(self, voucher):
        """Show a successfully issued voucher (an IssuedVoucher)."""
        self.state = self.ISSUED
        self.value = int(voucher.value)
        self.display_code = voucher.display_code
        self.qr_bytes = voucher.qr_bytes
        self.expires_at = voucher.expires_at

    def set_failure(self, amount):
        """The voucher could not be saved, so no code exists. The customer is
        told the amount and sent to the attendant."""
        self.clear()
        self.state = self.FAILED
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
        return "Here's your change voucher"

    def body(self) -> str:
        amount = f"{PESO}{self.value}"
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
