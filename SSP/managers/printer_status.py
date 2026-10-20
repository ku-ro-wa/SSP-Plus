# managers/printer_status.py
#
# Kiosk Admin's one-line printer status, read from CUPS (`lpstat -l -p`).
# The printer's own sensors report paper-out, jams and an open door, but not
# a sheet count or (on the Smart Tank, which has no tank sensors) real ink
# levels — those stay the DB estimates on the admin screen.

import subprocess

from config import get_config
from managers.printer_thread import parse_printer_alerts


def _has_alert(alerts, *prefixes):
    """CUPS alert keywords carry a severity suffix (media-jam-error,
    door-open-report, ...), so match on the reason before it."""
    return any(alert.startswith(prefix) for alert in alerts for prefix in prefixes)


def describe_printer_status(lpstat_output: str, found: bool = True) -> tuple[str, str]:
    """(text, level) for `lpstat -l -p <printer>` output; level is a
    status_banner variant: 'success' | 'warning' | 'error'."""
    if not found:
        return "Not found", "error"

    alerts = parse_printer_alerts(lpstat_output)
    output = lpstat_output.lower()
    if _has_alert(alerts, "media-jam", "paper-jam"):
        return "Paper jam", "error"
    if _has_alert(alerts, "media-empty", "media-needed"):
        return "Out of paper", "error"
    if _has_alert(alerts, "door-open", "cover-open"):
        return "Door open", "error"
    if _has_alert(alerts, "offline", "stopped") or "offline" in output:
        return "Offline", "error"
    if "paused" in alerts or " disabled " in output:
        return "Paused (queue disabled)", "error"
    if _has_alert(alerts, "media-low"):
        return "Paper low", "warning"
    if "now printing" in output:
        return "Printing", "success"
    if " is idle" in output:
        return "Ready", "success"
    return "Unknown", "warning"


def read_printer_status() -> tuple[str, str]:
    """The configured printer's status, or a fixed 'Ready (SIM)' in SIM_MODE."""
    config = get_config()
    if config.sim_mode:
        return "Ready (SIM)", "success"
    try:
        result = subprocess.run(
            ['lpstat', '-l', '-p', config.printer_name],
            capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Printer status check failed: {e}")
        return "Not responding", "error"
    return describe_printer_status(result.stdout, found=result.returncode == 0)
