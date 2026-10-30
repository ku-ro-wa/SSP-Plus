"""
What happens to a paid job once the printer reports back (issue #59).

Money is settled before printing starts (the transactions row is `paid`), so
the print outcome only moves that row on: `completed` on success, or
`print_failed` plus a refund Voucher worth the job's total_cost on failure.
Each outcome applies at most once per payment_ref.
"""
from dataclasses import dataclass
from typing import Optional

from managers.sms_manager import send_operator_alert
from managers.voucher_manager import IssuedVoucher, VoucherManager
from utils.error_logger import log_error

PAID = 'paid'
COMPLETED = 'completed'
PRINT_FAILED = 'print_failed'
DIGITAL_FAILED = 'digital_failed'  # a digital-only sale whose copy couldn't be made


@dataclass
class RefundOutcome:
    applied: bool = False              # False: no paid row for this ref, or already settled
    voucher: Optional[IssuedVoucher] = None
    voucher_failed: bool = False       # a refund was owed but no code could be given
    amount: int = 0


def record_print_success(db, payment_ref):
    """paid -> completed. Returns True if the row moved."""
    return db.update_transaction_outcome(payment_ref, COMPLETED, from_status=PAID)


def record_digital_refund(db, payment_ref, refunded, digital_only, error_message=""):
    """A paid Digital Copy couldn't be made; `refunded` is the fee given back as a
    Voucher (0 if that failed too). Adds it to the row's voucher_issued. A
    digital-only sale ends here as `digital_failed` (not revenue); with a print
    the row stays `paid` for the print outcome to settle. Returns True if it applied."""
    row = db.get_transaction_by_ref(payment_ref)
    if not row or row['status'] != PAID:
        return False
    return db.update_transaction_outcome(
        payment_ref, DIGITAL_FAILED if digital_only else PAID, from_status=PAID,
        voucher_issued=(row['voucher_issued'] or 0) + refunded,
        error_message=error_message or None)


def refund_failed_print(db, payment_ref, error_message="", already_refunded=0):
    """paid -> print_failed, issuing one refund Voucher for the job's total_cost,
    less `already_refunded` (a digital fee whose copy failed and was refunded
    on its own, so it isn't refunded twice)."""
    row = db.get_transaction_by_ref(payment_ref)
    if not row or row['status'] != PAID:
        return RefundOutcome()

    amount = max(0, int(round(row['total_cost'] or 0)) - int(already_refunded or 0))
    outcome = RefundOutcome(amount=amount)
    if amount > 0 and db.get_setting('vouchers_enabled', 1):
        try:
            outcome.voucher = VoucherManager(db).issue(amount, payment_ref=payment_ref)
        except Exception as e:
            outcome.voucher_failed = True
            _alert(f"Could not issue a P{amount} refund voucher for a failed print "
                   f"(payment_ref={payment_ref}): {e}", amount, payment_ref)
    elif amount > 0:
        outcome.voucher_failed = True
        _alert(f"Vouchers are off: P{amount} not refunded for a failed print "
               f"(payment_ref={payment_ref})", amount, payment_ref)

    issued = (row['voucher_issued'] or 0) + (outcome.voucher.value if outcome.voucher else 0)
    outcome.applied = db.update_transaction_outcome(
        payment_ref, PRINT_FAILED, from_status=PAID,
        voucher_issued=issued, error_message=error_message or None)
    return outcome


def _alert(message, amount, payment_ref):
    try:
        log_error("Refund Voucher Failed", message, "print_refund")
    except Exception:
        pass
    try:
        send_operator_alert(f"Print failed and the P{amount} refund could not be given. "
                            f"Customer was told to see the attendant. Ref {(payment_ref or '')[:8]}")
    except Exception as e:
        print(f"WARNING: could not send operator alert: {e}")
