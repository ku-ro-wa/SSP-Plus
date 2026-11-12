"""
Kiosk heartbeat and QR reader status, persisted to the `settings` table so the
Admin Dashboard (a separate process) can show whether a kiosk is alive and
whether its QR reader is connected. See issue #42.

Two keys:
- `kiosk_last_seen`: ISO 8601 timestamp, refreshed about once a minute and at
  startup.
- `qr_reader_status`: the one-line text Kiosk Admin shows ("Connected",
  "Not connected", "Not configured", "Starting"), written at startup and on
  every status change.

- `printer_status` / `printer_status_level` / `printer_status_at`: Kiosk Admin's
  printer line, its warn/critical level ('success' | 'warning' | 'error') and
  when it was read (ISO 8601), written at startup and on each heartbeat tick.
  See issue #132.

A failed write is logged and never raised — persisting status must never
disturb the kiosk.
"""
from datetime import datetime

from utils.error_logger import log_error

SETTING_LAST_SEEN = "kiosk_last_seen"
SETTING_QR_STATUS = "qr_reader_status"
SETTING_PRINTER_STATUS = "printer_status"
SETTING_PRINTER_LEVEL = "printer_status_level"
SETTING_PRINTER_AT = "printer_status_at"


def heartbeat_timestamp(now=None):
    """ISO 8601 timestamp (seconds precision) for `now`, defaulting to the
    current local time — the same clock every other kiosk timestamp uses, so
    the dashboard reads it with datetime.fromisoformat()."""
    now = now or datetime.now()
    return now.replace(microsecond=0).isoformat()


def write_heartbeat(db, now=None):
    """Write the heartbeat timestamp to settings. Returns False (logged, not
    raised) if the write fails."""
    return write_setting_safely(db, SETTING_LAST_SEEN, heartbeat_timestamp(now))


def write_qr_status(db, status_text):
    """Write the QR reader status text to settings. Returns False (logged, not
    raised) if the write fails."""
    return write_setting_safely(db, SETTING_QR_STATUS, status_text)


def write_printer_status(db, text, level, now=None):
    """Write the printer status text, level and read-time to settings. Returns
    True only if all three writes succeeded; failures are logged, not raised."""
    results = [
        write_setting_safely(db, SETTING_PRINTER_STATUS, text),
        write_setting_safely(db, SETTING_PRINTER_LEVEL, level),
        write_setting_safely(db, SETTING_PRINTER_AT, heartbeat_timestamp(now)),
    ]
    return all(results)


def write_setting_safely(db, key, value):
    """Write one settings key, logging (never raising) on failure."""
    try:
        db.update_setting(key, value)
        return True
    except Exception as e:
        try:
            log_error("Kiosk Status", f"Failed to write '{key}': {e}", "kiosk_status")
        except Exception:
            pass
        return False
