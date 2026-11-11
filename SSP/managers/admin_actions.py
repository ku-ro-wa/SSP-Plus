"""
The audit trail of operator changes (issue #134, ADR 0005): one `admin_actions`
row per change made from either side, so "who set paper to 100?" has an answer.

A row holds the time, who (a dashboard username, or `kiosk` for a touchscreen
action behind ADMIN_PIN), where (`dashboard` with the source IP, or
`touchscreen`), the action, and the old and new values as text.

A save that doesn't change the value writes nothing. Recording is best effort:
a failure is logged and never raised, so an audit write can't undo or block
the change it describes.

Action names: `paper`, `paper_reset` (the dashboard's /paper-reset), `coins_1`,
`coins_5`, `ink`, `collect_cash` and `setting:<key>`.
"""
from utils.error_logger import log_error

PAGE_SIZE = 25  # rows per page on /logs and in the touchscreen data viewer

ACTOR_KIOSK = "kiosk"
WHERE_TOUCHSCREEN = "touchscreen"
WHERE_DASHBOARD = "dashboard"

ACTION_PAPER = "paper"
ACTION_PAPER_RESET = "paper_reset"
ACTION_COINS_1 = "coins_1"
ACTION_COINS_5 = "coins_5"
ACTION_INK = "ink"
ACTION_COLLECT_CASH = "collect_cash"
ACTION_SETTING_PREFIX = "setting:"


def _text(value):
    return "" if value is None else str(value)


def format_ink(levels):
    """One-line ink levels, e.g. 'C 80% M 60% Y 5% K 0%', for old/new values."""
    if not levels:
        return "unset"
    return " ".join(f"{initial} {levels[name]:g}%" for initial, name in
                    (("C", "cyan"), ("M", "magenta"), ("Y", "yellow"), ("K", "black")))


def where_text(row):
    """'touchscreen', or 'dashboard (<ip>)': the same wording on both views."""
    where = row["location"]
    ip = row["source_ip"]
    return f"{where} ({ip})" if ip else where


def record_action(db, action, old, new, *, actor, where, ip=None):
    """Write one row. Returns True if written, False if skipped (old == new) or
    the write failed (logged, not raised)."""
    if _text(old) == _text(new):
        return False
    try:
        return bool(db.record_admin_action(actor, where, ip, action, _text(old), _text(new)))
    except Exception as e:
        try:
            log_error("Admin Actions", f"Failed to record '{action}': {e}", "admin_actions")
        except Exception:
            pass
        return False


def record_touchscreen_action(db, action, old, new):
    return record_action(db, action, old, new, actor=ACTOR_KIOSK, where=WHERE_TOUCHSCREEN)


def record_setting_changes(db, old, new, **who):
    """One row per setting whose value changed. `old` and `new` map key -> value;
    `who` is the actor/where/ip for record_action. Returns the rows written."""
    written = 0
    for key, value in new.items():
        if record_action(db, ACTION_SETTING_PREFIX + key, old.get(key), value, **who):
            written += 1
    return written
