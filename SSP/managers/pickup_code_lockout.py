"""Attempt limit for typed pickup codes (#104).

A pickup code is only 6 digits, and until this existed the limit only applied to
the QR path, where the payload carries the session id and a miss can be charged
to that one Session. A code typed on the Wi-Fi or Email keypad matched no
candidate in `SessionManager.verify_otp_for_source()`, so a wrong code left no
trace at all: the code space could be walked with no limit and no delay.

Now N consecutive wrong typed codes lock **typed** entry for M minutes. Both
screens share one counter — a customer has one code space and one keypad — and
the deadline is a wall-clock timestamp in `settings` (via `AttemptLockout`), so
closing the screen, opening the other screen or restarting the app never clears
it. QR reads are unaffected: they still lock the individual Session
(`session_manager.MAX_FAILED_ATTEMPTS`) and never consult this.

Only guesses count. A real code that can't be redeemed (expired or locked-out
Session) comes back from `SessionManager.verify_typed_otp()` with
`matched=True`, and retyping it must not lock the keypad — nor can it. Likewise
input that isn't six digits never reaches the lookup, so mashing keys can't lock
entry for the next customer.
"""
from datetime import datetime

from managers.attempt_lockout import AttemptLockout
from managers.session_manager import OtpLookup

SETTING_FAILED = "pickup_code_failed_attempts"
SETTING_LOCKED_UNTIL = "pickup_code_locked_until"
SETTING_MAX_ATTEMPTS = "pickup_code_max_attempts"
SETTING_LOCKOUT_MINUTES = "pickup_code_lockout_minutes"
ERROR_SOURCE = "Pickup Code"

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_MINUTES = 5


def locked_message(seconds: int) -> str:
    """'Too many wrong codes. Try again in 4:32.' — shown while locked, and
    refreshed every second by the screens' countdown timer."""
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"Too many wrong codes. Try again in {minutes}:{secs:02d}."


def _int_setting(db, key, default):
    try:
        return int(db.get_setting(key, default))
    except (TypeError, ValueError):
        return default


class PickupCodeLockout(AttemptLockout):
    setting_failed = SETTING_FAILED
    setting_locked_until = SETTING_LOCKED_UNTIL
    error_source = ERROR_SOURCE
    label = "Typed pickup codes"
    wrong = "wrong codes"

    def __init__(self, db, max_attempts=None, lockout_minutes=None,
                 clock=datetime.now, on_lockout=None):
        # Operator settings (Kiosk Admin writes the `settings` table), read when
        # the screen's model is built; the constants are only fallbacks.
        if max_attempts is None:
            max_attempts = _int_setting(db, SETTING_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS)
        if lockout_minutes is None:
            lockout_minutes = _int_setting(db, SETTING_LOCKOUT_MINUTES, DEFAULT_LOCKOUT_MINUTES)
        super().__init__(db, max_attempts, max(0, lockout_minutes), clock=clock,
                         on_lockout=on_lockout)

    def verify(self, session_manager, source, otp):
        """Look up a typed code for a screen, counting it toward the limit.

        Returns the `OtpLookup` from `SessionManager.verify_typed_otp()`, with
        its message replaced by the lockout notice when this guess tripped the
        limit (or when entry was already locked, where no lookup happens at
        all, so even the right code is refused).
        """
        remaining = self.remaining()
        if remaining:
            return OtpLookup(False, locked_message(remaining))

        result = session_manager.verify_typed_otp(source, otp)
        if result.success:
            self.record_success()
        elif not result.matched and self.record_failure():
            result.message = locked_message(self.remaining())
        return result
