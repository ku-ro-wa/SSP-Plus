"""
The operator's edits to paper, coins and ink, and Collect cash, in one place
(issue #135). The touchscreen's `AdminModel` and the Admin Dashboard's `/kiosk`
both call these, so the two sides check the same ranges, write the same rows
and record the same `admin_actions` entry. No Qt, so the dashboard process can
import it.

`who` says who is acting: `TOUCHSCREEN`, or `dashboard_actor(username, ip)`.
"""
from managers.admin_actions import (
    ACTION_COINS_1, ACTION_COINS_5, ACTION_COLLECT_CASH, ACTION_INK, ACTION_PAPER,
    ACTOR_KIOSK, WHERE_DASHBOARD, WHERE_TOUCHSCREEN, format_ink, record_action,
)

PAPER_MIN, PAPER_FULL = 0, 100
COIN_MIN, COIN_MAX = 0, 1000
COIN_REFILL = {1: 100, 5: 50}   # "Refill All": the hoppers' full counts
INK_MIN, INK_FULL = 0.0, 100.0
INK_NAMES = ("cyan", "magenta", "yellow", "black")

TOUCHSCREEN = {"actor": ACTOR_KIOSK, "where": WHERE_TOUCHSCREEN}


def dashboard_actor(username, ip=None):
    return {"actor": username, "where": WHERE_DASHBOARD, "ip": ip}


class EditError(ValueError):
    """An edit refused; the message is shown to the operator as is."""


class CollectionChanged(EditError):
    """The counts changed since the operator saw the collection preview."""

    def __init__(self, preview):
        super().__init__("The counts changed since you looked. Check the new total and try again.")
        self.preview = preview


# ------------------------------------------------------------------ validation

def parse_paper(raw):
    try:
        count = int(str(raw).strip())
    except ValueError:
        raise EditError("Please enter a valid number.")
    if not PAPER_MIN <= count <= PAPER_FULL:
        raise EditError(f"Paper count must be between {PAPER_MIN} and {PAPER_FULL}.")
    return count


def parse_coin_count(raw, denomination):
    try:
        count = int(str(raw).strip())
    except ValueError:
        raise EditError(f"Please enter a valid number for ₱{denomination} coins.")
    if not COIN_MIN <= count <= COIN_MAX:
        raise EditError(f"₱{denomination} coin count must be between {COIN_MIN} and {COIN_MAX}.")
    return count


def check_ink(levels):
    """`levels` maps cyan/magenta/yellow/black to numbers; returns them as floats."""
    try:
        cleaned = {name: float(levels[name]) for name in INK_NAMES}
    except (KeyError, TypeError, ValueError):
        raise EditError("Please enter valid decimal numbers for CMYK levels")
    if not all(INK_MIN <= v <= INK_FULL for v in cleaned.values()):
        raise EditError(f"CMYK values must be between {INK_MIN} and {INK_FULL}")
    return cleaned


# --------------------------------------------------------------------- reading

def current_paper(db):
    value = db.get_setting("paper_count", default=PAPER_FULL)
    try:
        return int(value)
    except (TypeError, ValueError):
        return PAPER_FULL


def current_coins(db):
    """{1: count, 5: count} of the hoppers' coins, zero when there's no row yet."""
    counts = {1: 0, 5: 0}
    for item in db.get_cash_inventory() or []:
        if item["type"] == "coin" and int(item["denomination"]) in counts:
            counts[int(item["denomination"])] = int(item["count"])
    return counts


# --------------------------------------------------------------------- writing

def set_paper(db, count, who):
    """Store the paper count (already validated). Returns (old, new)."""
    old = current_paper(db)
    db.update_setting("paper_count", count)
    record_action(db, ACTION_PAPER, old, count, **who)
    return old, count


def set_coin_count(db, denomination, count, who, coin_type="coin"):
    """Store one hopper's count (already validated). Returns (old, new)."""
    old = current_coins(db).get(denomination, 0) if coin_type == "coin" else None
    db.update_cash_inventory(denomination, count, coin_type)
    record_action(db, ACTION_COINS_1 if denomination == 1 else ACTION_COINS_5, old, count, **who)
    return old, count


def refill_coins(db, who):
    for denomination, count in COIN_REFILL.items():
        set_coin_count(db, denomination, count, who)
    return dict(COIN_REFILL)


def set_ink(db, levels, who):
    """Store the four ink levels (already validated). Raises EditError if the
    database refuses. Returns the new levels."""
    old = format_ink(db.get_cmyk_ink_levels())
    if not db.update_cmyk_ink_levels(*(levels[name] for name in INK_NAMES)):
        raise EditError("Failed to update CMYK levels")
    record_action(db, ACTION_INK, old, format_ink(levels), **who)
    return levels


def refill_ink(db, who):
    return set_ink(db, {name: INK_FULL for name in INK_NAMES}, who)


def collect_cash(db, who, expected_total=None):
    """Record the current counts as a collection and zero them (issue #110).
    With `expected_total`, refuses (CollectionChanged) if the counts no longer
    add up to what the operator confirmed. Returns the collection id."""
    preview = db.get_collection_preview()
    if expected_total is not None and abs(float(preview["total"]) - float(expected_total)) > 1e-9:
        raise CollectionChanged(preview)
    collection_id = db.record_cash_collection()
    if collection_id is None:
        raise EditError("Could not record the cash collection. Nothing was changed.")
    record_action(db, ACTION_COLLECT_CASH, f"₱{preview['total']:g} counted", f"collection #{collection_id}", **who)
    return collection_id
