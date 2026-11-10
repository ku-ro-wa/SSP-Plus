# admin_dashboard/kiosk_overview.py
#
# What /kiosk shows (docs/adr/0005): the kiosk's supplies, QR reader status and
# whether the kiosk app is alive, all read from the shared SQLite DB. Pure
# functions over a DatabaseManager so they can be tested without HTTP.

from datetime import datetime

from managers.kiosk_status import SETTING_LAST_SEEN, SETTING_QR_STATUS
from managers.supply_levels import (
    COIN_CRIT, COIN_WARN, INK_CRIT, INK_WARN, PAPER_CRIT, PAPER_WARN, severity,
)

# The kiosk writes its heartbeat about every 60 s; three missed beats means it is down.
ONLINE_WITHIN_SECONDS = 180

ERRORS_SHOWN = 10

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


def _ink(db):
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
            "band": severity(level, INK_WARN, INK_CRIT),
            "empty": level <= 0,
        })
    return {"tanks": tanks, "last_updated": str(levels.get("last_updated") or "")}


def build_overview(db, now=None):
    supplies = db.get_supplies_status() or {"paper_count": 0, "coins": {"peso_1": 0, "peso_5": 0}}
    online, seen_text = describe_last_seen(db.get_setting(SETTING_LAST_SEEN), now)
    errors, error_total = db.get_error_page(ERRORS_SHOWN, unresolved_only=True)

    return {
        "online": online,
        "last_seen": seen_text,
        "qr_reader": db.get_setting(SETTING_QR_STATUS) or "Unknown",
        "paper": {
            "count": supplies["paper_count"],
            "band": severity(supplies["paper_count"], PAPER_WARN, PAPER_CRIT),
        },
        "coins": {
            "peso_1": supplies["coins"]["peso_1"],
            "peso_5": supplies["coins"]["peso_5"],
            "peso_1_band": severity(supplies["coins"]["peso_1"], COIN_WARN, COIN_CRIT),
            "peso_5_band": severity(supplies["coins"]["peso_5"], COIN_WARN, COIN_CRIT),
        },
        "ink": _ink(db),
        "ink_warn": INK_WARN,
        "ink_crit": INK_CRIT,
        "errors": errors,
        "error_total": error_total,
    }
