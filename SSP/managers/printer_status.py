# managers/printer_status.py
#
# Kiosk Admin's one-line printer status, read from CUPS (`lpstat -l -p`).
# The printer's own sensors report paper-out, jams and an open door, but not
# a sheet count or (on the Smart Tank, which has no tank sensors) real ink
# levels — those stay the DB estimates on the admin screen.

import re
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


def _device_uri(printer_name: str):
    """The queue's device URI from `lpstat -v`, if it is an IPP one (e.g. the USB bridge)."""
    result = subprocess.run(['lpstat', '-v', printer_name], capture_output=True, text=True, timeout=5)
    match = re.search(r'\b(ipps?://\S+)', result.stdout)
    return match.group(1) if match else None


def _ipp_reasons(printer_name: str) -> list:
    """printer-state-reasons straight from the printer. CUPS copies these into
    its queue's `Alerts:` only some of the time (the HP Smart Tank over its USB
    bridge shows `Alerts: none` with the tray out), so ask the printer itself.
    Empty when it can't be asked or reports none."""
    uri = _device_uri(printer_name)
    if not uri:
        return []
    result = subprocess.run(['ipptool', '-tv', uri, 'get-printer-attributes.test'],
                            capture_output=True, text=True, timeout=5)
    match = re.search(r'printer-state-reasons \([^)]*\) = (\S+)', result.stdout)
    if not match or match.group(1) == 'none':
        return []
    return match.group(1).split(',')


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
    output = result.stdout
    if result.returncode == 0:
        try:
            reasons = _ipp_reasons(config.printer_name)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"Printer IPP status check failed, using CUPS alone: {e}")
            reasons = []
        if reasons:
            # CUPS' own (empty) Alerts line is replaced by what the printer reported
            lines = [line for line in output.split("\n") if not line.strip().startswith("Alerts:")]
            output = "\n".join(lines) + "\n\tAlerts: " + " ".join(reasons) + "\n"
    return describe_printer_status(output, found=result.returncode == 0)
