# admin_dashboard/kiosk_overview.py
#
# What /kiosk shows (docs/adr/0005): the kiosk's supplies, QR reader status and
# whether the kiosk app is alive, all read from the shared SQLite DB. Pure
# functions over a DatabaseManager so they can be tested without HTTP.

from datetime import datetime

from config import get_config
from managers.kiosk_status import SETTING_LAST_SEEN, SETTING_QR_STATUS

# The kiosk writes its heartbeat about every 60 s; three missed beats means it is down.
ONLINE_WITHIN_SECONDS = 180

INK_COLOURS = ("cyan", "magenta", "yellow", "black")


def describe_last_seen(raw, now=None):
    """(online, text) for the stored `kiosk_last_seen` value."""
    now = now or datetime.now()
    try:
        seen = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return False, "never seen"
    age = max(0, int((now - seen).total_seconds()))
    if age <= ONLINE_WITHIN_SECONDS:
        return True, f"online, {age} s ago" if age < 120 else f"online, {age // 60} min ago"
    when = seen.strftime("%H:%M") if seen.date() == now.date() else seen.strftime("%d %b %H:%M")
    return False, f"offline since {when}"


def _ink(db, threshold):
    levels = db.get_cmyk_ink_levels()
    if not levels:
        return None
    tanks = []
    for name in INK_COLOURS:
        level = levels.get(name)
        if level is None:
            continue
        tanks.append({
            "name": name,
            "level": round(level),
            "low": level <= threshold,
            "empty": level <= 0,
        })
    return {"tanks": tanks, "last_updated": str(levels.get("last_updated") or "")}


def build_overview(db, now=None):
    config = get_config()
    paper_threshold = config.low_paper_alert_sheets
    ink_threshold = config.ink_low_alert_percent

    supplies = db.get_supplies_status() or {"paper_count": 0, "coins": {"peso_1": 0, "peso_5": 0}}
    online, seen_text = describe_last_seen(db.get_setting(SETTING_LAST_SEEN), now)
    errors = [e for e in db.get_error_log() if not e.get("resolved")]

    return {
        "online": online,
        "last_seen": seen_text,
        "qr_reader": db.get_setting(SETTING_QR_STATUS) or "Unknown",
        "paper": {
            "count": supplies["paper_count"],
            "low": supplies["paper_count"] <= paper_threshold,
        },
        "coins": supplies["coins"],
        "ink": _ink(db, ink_threshold),
        "ink_threshold": ink_threshold,
        "errors": errors[:20],
        "error_total": len(errors),
    }
