# managers/printer_status.py
#
# Kiosk Admin's one-line printer status, read from CUPS (`lpstat -l -p`).
# The printer's own sensors report paper-out, jams and an open door, but not
# a sheet count or (on the Smart Tank, which has no tank sensors) real ink
# levels — those stay the DB estimates on the admin screen.

import subprocess

from config import get_config
from managers.printer_ipp import has_reason, ipp_reasons
from managers.printer_thread import parse_printer_alerts


def _has_alert(alerts, *prefixes):
    """CUPS alert keywords carry a severity suffix (media-jam-error,
    door-open-report, ...), so match on the reason before it."""
    return has_reason(alerts, prefixes)


# Consecutive 1-minute status reads where the printer's IPP didn't answer before
# the status stops trusting CUPS' idle line. On 2026-11-13 a jammed printer timed
# out for 20+ minutes while CUPS kept saying "idle", i.e. "Ready".
IPP_TIMEOUTS_BEFORE_NOT_RESPONDING = 3
_ipp_timeouts = 0


def _reset_ipp_timeouts():
    global _ipp_timeouts
    _ipp_timeouts = 0


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
    global _ipp_timeouts
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
    output = result.stdout
    if result.returncode == 0:
        try:
            reasons = ipp_reasons(config.printer_name)
            _ipp_timeouts = 0
        except (OSError, subprocess.TimeoutExpired) as e:
            _ipp_timeouts += 1
            print(f"Printer IPP status check failed ({_ipp_timeouts} in a row), using CUPS alone: {e}")
            if _ipp_timeouts >= IPP_TIMEOUTS_BEFORE_NOT_RESPONDING:
                return "Not responding", "error"
            reasons = None
        if reasons is not None:
            # The printer answered, so what it says replaces CUPS' own Alerts line, which
            # can be stale (media-empty-report lingering after paper was loaded again)
            lines = [line for line in output.split("\n") if not line.strip().startswith("Alerts:")]
            output = "\n".join(lines) + "\n\tAlerts: " + (" ".join(reasons) or "none") + "\n"
    return describe_printer_status(output, found=result.returncode == 0)
