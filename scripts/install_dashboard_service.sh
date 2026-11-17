#!/usr/bin/env bash
# Run the Admin Dashboard at boot as a system service (issue #45). Run on the
# kiosk as the user that owns the repo (not root; it asks for sudo), from the
# repo, with any `make run-admin-dashboard` stopped:
#
#   scripts/install_dashboard_service.sh              # install (safe to re-run)
#   scripts/install_dashboard_service.sh --uninstall  # back to starting it by hand
#
# Fills in deploy/systemd/ssp-admin-dashboard.service and writes it to
# /etc/systemd/system/. The dashboard listens on 127.0.0.1 only; reach it over
# an SSH tunnel (docs/CHEATSHEET.md §8).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
NAME="ssp-admin-dashboard.service"
TEMPLATE="$REPO/deploy/systemd/$NAME"
UNIT="/etc/systemd/system/$NAME"
RUN_AS="$(id -un)"

if [ "${1:-}" = "--uninstall" ]; then
    sudo systemctl disable --now "$NAME" 2>/dev/null || true
    sudo rm -f "$UNIT"
    sudo systemctl daemon-reload
    echo "Removed $UNIT. Start the dashboard by hand with: make run-admin-dashboard"
    exit 0
fi

[ "$RUN_AS" != "root" ] || { echo "Run as the repo's owner, not root (the service runs as that user)." >&2; exit 1; }
[ -x "$REPO/.venv/bin/python" ] || { echo "No $REPO/.venv: do KIOSK_PI_SETUP.md step 6 first." >&2; exit 1; }
[ -f "$REPO/.env" ] || { echo "No $REPO/.env: do KIOSK_PI_SETUP.md step 7 first." >&2; exit 1; }
if pgrep -f "admin_dashboard.main" >/dev/null && ! systemctl is-active --quiet "$NAME"; then
    echo "The dashboard is already running by hand. Stop it first (Ctrl+C in its terminal)." >&2
    exit 1
fi

sed -e "s|@USER@|$RUN_AS|g" -e "s|@REPO@|$REPO|g" "$TEMPLATE" | sudo tee "$UNIT" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now "$NAME"
sudo systemctl restart "$NAME"
echo "Wrote $UNIT (runs as $RUN_AS from $REPO)"
sleep 3
systemctl --no-pager --lines=5 status "$NAME" || true
echo
echo "Check it listens on loopback only:  ss -ltnp | grep 8100   (expect 127.0.0.1:8100)"
echo "Logs:                               journalctl -u $NAME -f"
