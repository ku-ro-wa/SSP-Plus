"""Shared attempt limit for a guessable secret.

N consecutive wrong guesses lock further entry for M minutes. The deadline is a
wall-clock timestamp in the `settings` table, so closing the screen, recreating
the model or restarting the app never shortens or restarts it.

Subclasses name their `settings` rows, their `error_log` source and the wording
of the logged message; the behaviour lives here once.
`managers/pin_lockout.py` (the touchscreen admin PIN, #98) and
`managers/pickup_code_lockout.py` (typed pickup codes, #104) are the users.
"""
from datetime import datetime, timedelta


class AttemptLockout:
    # Set by every subclass.
    setting_failed = ""         # settings row holding the consecutive misses
    setting_locked_until = ""   # settings row holding the ISO deadline
    error_source = ""           # error_log error_type (and context)
    label = ""                  # 'PIN dialog', 'Typed pickup codes'
    wrong = ""                  # 'wrong PINs', 'wrong codes'

    def __init__(self, db, max_attempts=5, lockout_minutes=5, clock=datetime.now, on_lockout=None):
        self.db = db
        self.max_attempts = max(1, int(max_attempts))
        self.lockout = timedelta(minutes=lockout_minutes)
        self.clock = clock
        self.on_lockout = on_lockout

    def _locked_until(self):
        raw = self.db.get_setting(self.setting_locked_until, "")
        try:
            return datetime.fromisoformat(str(raw)) if raw else None
        except ValueError:
            return None

    def _failed(self):
        try:
            return int(self.db.get_setting(self.setting_failed, 0))
        except (TypeError, ValueError):
            return 0

    def remaining(self):
        """Seconds of lockout left (0 when not locked)."""
        until = self._locked_until()
        if until is None:
            return 0
        return max(0, int((until - self.clock()).total_seconds() + 0.999))

    def is_locked(self):
        return self.remaining() > 0

    def record_success(self):
        if self._failed():
            self.db.update_setting(self.setting_failed, 0)

    def record_failure(self):
        """Count a wrong guess; returns True if this one started a lockout."""
        failed = self._failed() + 1
        if failed < self.max_attempts:
            self.db.update_setting(self.setting_failed, failed)
            return False
        self.db.update_setting(self.setting_failed, 0)
        self.db.update_setting(
            self.setting_locked_until, (self.clock() + self.lockout).isoformat()
        )
        minutes = self.lockout.total_seconds() / 60
        message = f"{self.label} locked for {minutes:g} min after {self.max_attempts} {self.wrong}"
        try:
            self.db.log_error(self.error_source, message, self.error_source)
        except Exception as e:
            print(f"{self.label} lockout: could not log error: {e}")
        if self.on_lockout:
            try:
                self.on_lockout(message)
            except Exception as e:
                print(f"{self.label} lockout: alert failed: {e}")
        return True
