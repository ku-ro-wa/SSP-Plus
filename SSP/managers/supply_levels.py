# managers/supply_levels.py
#
# Warning / critical bands for paper, coin and ink readouts. Qt-free so the
# touchscreen's Kiosk Admin (screens/admin/view.py) and the Admin Dashboard's
# /kiosk page share one definition.

PAPER_WARN, PAPER_CRIT = 50, 20
COIN_WARN, COIN_CRIT = 50, 20
INK_WARN, INK_CRIT = 25.0, 10.0

OK, WARN, CRIT = "ok", "warn", "crit"


def severity(value: float, warn_at: float, crit_at: float) -> str:
    """CRIT at/below crit_at, WARN at/below warn_at, else OK."""
    if value <= crit_at:
        return CRIT
    if value <= warn_at:
        return WARN
    return OK
