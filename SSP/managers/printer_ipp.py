# managers/printer_ipp.py
#
# What the printer itself reports (IPP `printer-state-reasons`), as opposed to
# the copy CUPS keeps in its queue's `Alerts:` line. CUPS only refreshes that
# line some of the time (and over the HP Smart Tank's USB bridge it can show
# `Alerts: none` with the tray out, or keep `media-empty-report` after paper
# was loaded again), so anything deciding "is the tray empty / jammed" should
# ask the printer.

import re
import subprocess

# The reasons that mean the tray is empty, as the printer or CUPS spells them.
MEDIA_EMPTY_REASONS = ("media-empty", "media-needed")


def device_uri(printer_name: str):
    """The queue's device URI from `lpstat -v`, if it is an IPP one (e.g. the USB bridge)."""
    result = subprocess.run(['lpstat', '-v', printer_name], capture_output=True, text=True, timeout=5)
    match = re.search(r'\b(ipps?://\S+)', result.stdout)
    return match.group(1) if match else None


def ipp_reasons(printer_name: str):
    """printer-state-reasons straight from the printer.

    A list when the printer answered (empty when it reports `none`), or None
    when it couldn't be asked or gave no state-reasons line, so a caller can
    tell "reports nothing wrong" from "didn't answer". Raises OSError or
    subprocess.TimeoutExpired when ipptool itself fails or hangs."""
    uri = device_uri(printer_name)
    if not uri:
        return None
    result = subprocess.run(['ipptool', '-tv', uri, 'get-printer-attributes.test'],
                            capture_output=True, text=True, timeout=5)
    match = re.search(r'printer-state-reasons \([^)]*\) = (\S+)', result.stdout)
    if not match:
        return None
    if match.group(1) == 'none':
        return []
    return match.group(1).split(',')


def has_reason(reasons, prefixes) -> bool:
    """Reasons carry a severity suffix (media-empty-error, media-empty-report, ...)."""
    return any(reason.startswith(prefix) for reason in reasons for prefix in prefixes)
