"""Attempt limit for the touchscreen admin PIN dialog.

N consecutive wrong PINs lock the dialog for M minutes. The deadline is a
wall-clock timestamp in the `settings` table, so closing the dialog, recreating
the model or restarting the app never shortens or restarts it. The lock only
blocks PIN entry; no customer screen consults it.
"""
from managers.attempt_lockout import AttemptLockout

SETTING_FAILED = "pin_failed_attempts"
SETTING_LOCKED_UNTIL = "pin_locked_until"
ERROR_SOURCE = "PIN Dialog"


class PinLockout(AttemptLockout):
    setting_failed = SETTING_FAILED
    setting_locked_until = SETTING_LOCKED_UNTIL
    error_source = ERROR_SOURCE
    label = "PIN dialog"
    wrong = "wrong PINs"
