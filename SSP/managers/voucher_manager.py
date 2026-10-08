
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from managers.session_manager import _generate_qr_bytes

# Crockford base32: digits + letters minus I, L, O, U (no look-alikes).
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 8
QR_PREFIX = "V1:"  # type tag so a future scanner can tell this from "session_id:otp"

# Shared by payment-time entry AND balance checks (one counter, one lockout),
# so the 30-day lifetime can't be used to brute-force codes at the touchscreen.
MAX_FAILED_ATTEMPTS = 5
DEFAULT_LOCKOUT_MINUTES = 5  # fallback if 'voucher_lockout_minutes' is unset
DEFAULT_EXPIRY_DAYS = 30     # fallback if 'voucher_expiry_days' is unset

# Crockford decoding: commonly mistyped characters map to their look-alikes.
_CROCKFORD_FIXES = str.maketrans({"O": "0", "I": "1", "L": "1"})

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


class LookupStatus:
    """Why a lookup succeeded or failed, so screens can react without parsing
    the message. Only UNKNOWN counts toward the shared lockout: EXPIRED and
    USED codes are real codes, and MALFORMED input can't be a guess at one."""
    FOUND = "found"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    USED = "used"
    MALFORMED = "malformed"
    LOCKED = "locked"


def normalize_code(raw) -> Optional[str]:
    """Canonical 8-char code from whatever the customer typed or scanned
    ('abcd-1234', 'V1:ABCD1234', ...), or None if it can't be a code."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().upper()
    if s.startswith(QR_PREFIX):
        s = s[len(QR_PREFIX):]
    s = s.replace("-", "").replace(" ", "").translate(_CROCKFORD_FIXES)
    if len(s) != CODE_LENGTH or any(c not in CODE_ALPHABET for c in s):
        return None
    return s


def format_code(code: str) -> str:
    """'ABCD1234' -> 'ABCD-1234' (the typeable on-screen form)."""
    return f"{code[:4]}-{code[4:]}"


def format_expiry(d: datetime) -> str:
    """'October 8, 2026'. Not %B: QApplication applies the system locale, and
    the kiosk's copy is English."""
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _hash_code(voucher_id: str, code: str) -> str:
    # Salted with voucher_id, same scheme as the Session OTP.
    return hashlib.sha256(f"{voucher_id}:{code}".encode()).hexdigest()


@dataclass
class IssuedVoucher:
    voucher_id: str
    code: str            # raw code: show it once, never persisted
    display_code: str    # 'XXXX-XXXX'
    value: int           # pesos
    qr_bytes: Optional[bytes]  # PNG of 'V1:<code>'; None if QR rendering failed
    expires_at: datetime


@dataclass
class VoucherLookup:
    success: bool
    message: str
    remaining: int = 0
    expires_at: Optional[datetime] = None
    locked: bool = False
    status: str = LookupStatus.FOUND


@dataclass
class ApplyResult:
    success: bool
    message: str
    total_applied: int = 0
    # [{"voucher_id": ..., "amount": ..., "remaining": ...}], in the order used
    applications: list = field(default_factory=list)
    locked: bool = False
    status: str = LookupStatus.FOUND  # on failure, the failing code's LookupStatus


class VoucherManager:
    def __init__(self, db_manager, now_fn=datetime.now):
        self.db_manager = db_manager
        self._now = now_fn

    # ---- settings -------------------------------------------------------

    def _int_setting(self, key: str, default: int) -> int:
        try:
            return int(self.db_manager.get_setting(key, default))
        except (TypeError, ValueError):
            return default

    def _expiry_days(self) -> int:
        return self._int_setting('voucher_expiry_days', DEFAULT_EXPIRY_DAYS)

    def _lockout_minutes(self) -> int:
        return self._int_setting('voucher_lockout_minutes', DEFAULT_LOCKOUT_MINUTES)

    # ---- issue ----------------------------------------------------------

    def issue(self, shortfall, payment_ref: Optional[str] = None) -> IssuedVoucher:
        """
        Create a Voucher worth `shortfall` pesos. The row is committed BEFORE
        the code is returned ("persist, then show"): if the write fails this
        raises RuntimeError and no code exists. The caller must then tell the
        customer the Shortfall amount, send them to the attendant, and log it
        to error_log + raise an operator alert.
        """
        value = int(round(shortfall))
        if value <= 0:
            raise ValueError("A Voucher's value is the Shortfall, which must be positive")

        voucher_id = secrets.token_hex(8)
        code = self._new_unique_code()
        created_at = self._now()
        expires_at = created_at + timedelta(days=self._expiry_days())

        inserted = self.db_manager.create_voucher(
            voucher_id=voucher_id,
            code_hash=_hash_code(voucher_id, code),
            value=value,
            created_at=created_at,
            expires_at=expires_at,
            payment_ref=payment_ref,
        )
        if not inserted:
            raise RuntimeError(f"Failed to persist voucher {voucher_id} to the database")

        # Row is safely stored. A QR rendering problem must not stop the
        # customer getting the typeable code, so degrade to qr_bytes=None.
        try:
            qr_bytes = _generate_qr_bytes(QR_PREFIX + code)
        except Exception as e:
            print(f"Voucher QR generation failed (typeable code still valid): {e}")
            qr_bytes = None

        return IssuedVoucher(
            voucher_id=voucher_id,
            code=code,
            display_code=format_code(code),
            value=value,
            qr_bytes=qr_bytes,
            expires_at=expires_at,
        )

    def _new_unique_code(self) -> str:
        # 40 bits makes a clash astronomically unlikely, but a clash between
        # two ACTIVE vouchers would make lookup ambiguous, so check anyway.
        for _ in range(10):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if self._resolve(code) is None:
                return code
        raise RuntimeError("Could not generate a unique voucher code")

    # ---- lookup / lockout ----------------------------------------------

    def _resolve(self, code: str):
        """Active voucher row matching a canonical code, or None. Read-only."""
        return _match(self.db_manager.get_active_vouchers(self._now()), code)

    def _resolve_inactive(self, code: str):
        """Fully-used or expired voucher row matching a canonical code, or None."""
        return _match(self.db_manager.get_inactive_vouchers(self._now()), code)

    def _lockout_remaining(self) -> Optional[timedelta]:
        raw = self.db_manager.get_setting('voucher_locked_until', '')
        if not raw:
            return None
        try:
            until = datetime.fromisoformat(str(raw))
        except ValueError:
            return None
        remaining = until - self._now()
        return remaining if remaining > timedelta(0) else None

    @staticmethod
    def _locked_message(remaining: timedelta) -> str:
        minutes = max(1, -(-int(remaining.total_seconds()) // 60))  # ceil
        return f"Too many incorrect codes. Voucher entry is locked for {minutes} more minute(s)."

    def _register_failure(self) -> bool:
        """Count one wrong code. Returns True if this tripped the lockout."""
        attempts = self._int_setting('voucher_failed_attempts', 0) + 1
        if attempts >= MAX_FAILED_ATTEMPTS:
            until = self._now() + timedelta(minutes=self._lockout_minutes())
            self.db_manager.update_setting('voucher_locked_until', until.isoformat())
            self.db_manager.update_setting('voucher_failed_attempts', 0)
            return True
        self.db_manager.update_setting('voucher_failed_attempts', attempts)
        return False

    def _reset_failures(self):
        if self._int_setting('voucher_failed_attempts', 0) != 0:
            self.db_manager.update_setting('voucher_failed_attempts', 0)

    def _lookup(self, raw_code):
        """
        Resolve typed/scanned input to an active voucher row, honouring the
        shared lockout. Returns (row, None) or (None, VoucherLookup-failure).
        A malformed string can't be a guess at a real code, so it is rejected
        without counting toward the lockout.
        """
        remaining = self._lockout_remaining()
        if remaining:
            return None, VoucherLookup(False, self._locked_message(remaining), locked=True,
                                       status=LookupStatus.LOCKED)

        code = normalize_code(raw_code)
        if code is None:
            return None, VoucherLookup(False, "That doesn't look like a voucher code",
                                       status=LookupStatus.MALFORMED)

        row = self._resolve(code)
        if row is not None:
            return row, None

        # A real code that's spent or expired isn't a guess, so it gets its own
        # message and doesn't count toward the lockout.
        spent = self._resolve_inactive(code)
        if spent is not None:
            if int(spent['remaining_value']) <= 0:
                return None, VoucherLookup(False, "This voucher has already been fully used",
                                           status=LookupStatus.USED)
            expired = format_expiry(_as_datetime(spent['expires_at']))
            return None, VoucherLookup(False, f"This voucher expired on {expired}",
                                       expires_at=_as_datetime(spent['expires_at']),
                                       status=LookupStatus.EXPIRED)

        if self._register_failure():
            remaining = self._lockout_remaining()
            msg = self._locked_message(remaining) if remaining else "Too many incorrect codes"
            return None, VoucherLookup(False, msg, locked=True, status=LookupStatus.LOCKED)
        return None, VoucherLookup(False, "We don't recognise that voucher code. Please check it and try again",
                                   status=LookupStatus.UNKNOWN)

    # ---- public lookups -------------------------------------------------

    def balance(self, raw_code) -> VoucherLookup:
        """Balance check: no state change beyond the shared failure counter."""
        row, failure = self._lookup(raw_code)
        if failure:
            return failure
        self._reset_failures()
        return VoucherLookup(
            True, "Voucher found",
            remaining=int(row['remaining_value']),
            expires_at=_as_datetime(row['expires_at']),
        )

    def apply(self, raw_codes, amount_due, payment_ref: Optional[str] = None) -> ApplyResult:
        """
        Apply Vouchers toward `amount_due` (whole pesos), in the order entered,
        so at most the last one used is partly used (it keeps its code and its
        original expiry). Vouchers entered after the amount is covered are
        left untouched. All-or-nothing: if any code is bad, nothing is applied.

        A result with total_applied < amount_due is still a success; the
        caller collects the rest in cash.
        """
        due = int(round(amount_due))
        if due <= 0 or not raw_codes:
            return ApplyResult(True, "Nothing to apply")

        rows, seen = [], set()
        for raw in raw_codes:
            row, failure = self._lookup(raw)
            if failure:
                return ApplyResult(False, failure.message, locked=failure.locked,
                                   status=failure.status)
            if row['voucher_id'] in seen:
                continue  # same voucher entered twice
            seen.add(row['voucher_id'])
            rows.append(row)

        plan, still_due = [], due
        for row in rows:
            if still_due <= 0:
                break
            take = min(int(row['remaining_value']), still_due)
            plan.append((row['voucher_id'], take, int(row['remaining_value']) - take))
            still_due -= take

        if not self.db_manager.apply_vouchers(
            [(vid, take) for vid, take, _ in plan], payment_ref, self._now()
        ):
            return ApplyResult(False, "Could not apply the voucher, please try again")

        self._reset_failures()
        return ApplyResult(
            True, "Voucher applied",
            total_applied=sum(take for _, take, _ in plan),
            applications=[
                {"voucher_id": vid, "amount": take, "remaining": left}
                for vid, take, left in plan
            ],
        )


def _match(rows, code):
    for row in rows:
        if hmac.compare_digest(_hash_code(row['voucher_id'], code), row['code_hash']):
            return row
    return None


def _as_datetime(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value
