#!/usr/bin/env bash
# Start the kiosk app when the desktop logs in, and restart it if it dies
# (docs/KIOSK_PI_SETUP.md step 14). Run on the kiosk as the desktop user, from
# the repo, with the app stopped:
#
#   scripts/install_kiosk_service.sh              # install (safe to re-run)
#   scripts/install_kiosk_service.sh --uninstall  # back to starting it by hand
#
# Writes ~/.config/systemd/user/ssp-kiosk.service and one line in
# ~/.config/labwc/autostart (created from the system one if missing, so the
# desktop and taskbar still start).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/ssp-kiosk.service"
AUTOSTART="$HOME/.config/labwc/autostart"
MARKER="ssp-kiosk.service"
LINE="systemctl --user start $MARKER  # SSP kiosk app (scripts/install_kiosk_service.sh)"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user stop "$MARKER" 2>/dev/null || true
    if [ -f "$AUTOSTART" ]; then
        sed -i "/$MARKER/d" "$AUTOSTART"
    fi
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "Removed $UNIT and its autostart line. Start the app by hand with: make run"
    exit 0
fi

[ -x "$REPO/.venv/bin/python" ] || { echo "No $REPO/.venv: do KIOSK_PI_SETUP.md step 6 first." >&2; exit 1; }
[ -f "$REPO/.env" ] || { echo "No $REPO/.env: do KIOSK_PI_SETUP.md step 7 first." >&2; exit 1; }
pgrep -x labwc >/dev/null || { echo "labwc isn't running: this setup is for the labwc desktop." >&2; exit 1; }
if pgrep -f "SSP/main_app.py" >/dev/null; then
    echo "The app is running ($(cat /tmp/ssp-kiosk.lock 2>/dev/null || echo 'pid unknown')). Stop it first (Ctrl+C in its terminal)." >&2
    exit 1
fi

mkdir -p "$UNIT_DIR"
cat > "$UNIT" <<EOF
# Written by scripts/install_kiosk_service.sh; see docs/KIOSK_PI_SETUP.md step 14.
[Unit]
Description=SSP kiosk app

[Service]
WorkingDirectory=$REPO
# The app draws through Xwayland on the panel (ui/scaling.py pins xcb).
Environment=DISPLAY=:0
Environment=PYTHONUNBUFFERED=1
ExecStart=$REPO/.venv/bin/python -X utf8 SSP/main_app.py
# Back 5 s after a crash, a kill or a closed window (also covers pigpiod or
# Xwayland not being up yet at login). Exit 3 = another copy is running
# (managers/instance_lock.py): leave that one alone instead of retrying.
Restart=always
RestartSec=5
RestartPreventExitStatus=3
# SIGTERM runs cleanup() (acceptors off, hoppers stopped); give it time.
TimeoutStopSec=30
EOF
systemctl --user daemon-reload
echo "Wrote $UNIT"

mkdir -p "$(dirname "$AUTOSTART")"
if [ ! -f "$AUTOSTART" ]; then
    cp /etc/xdg/labwc/autostart "$AUTOSTART"
    echo "Created $AUTOSTART from /etc/xdg/labwc/autostart"
fi
if grep -q "$MARKER" "$AUTOSTART"; then
    echo "$AUTOSTART already starts the app"
else
    echo "$LINE" >> "$AUTOSTART"
    echo "Added to $AUTOSTART: $LINE"
fi

systemctl --user start "$MARKER"
sleep 8
systemctl --user --no-pager --lines=0 status "$MARKER" || true
echo
echo "Next: the app should be on the panel now. Check a restart with"
echo "  pkill -f SSP/main_app.py; sleep 10; cat /tmp/ssp-kiosk.lock"
echo "(a new pid), then reboot and check it comes up on its own."
