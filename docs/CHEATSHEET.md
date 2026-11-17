# Kiosk cheatsheet

Commands by situation. Run from the repo root (`SSP-Plus/`) unless noted.
`scripts/check_cheatsheet.py` fails if a path or `make` target named here stops existing.

Key: **[sim]** works on a laptop in SIM_MODE · **[pi]** needs the kiosk · **[stop]** the kiosk app must be stopped first · **[live]** safe while customers use it.

## 1. Run, stop, restart (on the kiosk, the app is a user service)

```bash
systemctl --user status ssp-kiosk          # [pi][live]
systemctl --user restart ssp-kiosk         # [pi] cleanup() runs, takes up to 30 s
systemctl --user stop ssp-kiosk            # [pi] stays stopped until started or reboot
systemctl --user start ssp-kiosk           # [pi]
cat /tmp/ssp-kiosk.lock                    # [pi][live] pid of the running copy
pkill -f SSP/main_app.py                   # [pi] crash test: service brings it back in ~10 s
scripts/install_kiosk_service.sh           # [pi][stop] install / repair (safe to re-run)
scripts/install_kiosk_service.sh --uninstall
```

- To run by hand (`make run`), **stop the service first**. A second copy refuses to start (exit 3).
- Alt+F4 on the panel only brings the app straight back. Use `systemctl --user stop` to reach the desktop.
- Over SSH there is no screen: `make run` picks `DISPLAY=:0` or goes headless by itself.

## 2. Dev loop

```bash
cp .env.example .env     # first time; .env must be at the repo root
make run-sim             # [sim] GUI with simulated hardware
make run                 # [pi] real hardware
make test                # [sim] pytest tests/ -v
make lint                # [sim] flake8 SSP/ scripts/
make screenshots         # [sim] every screen -> screenshots/<screen>.png (1920x1080)
make test-hotspot        # needs Docker
make intake-sheet        # writes intake_sheet.pdf; ARGS=--print also prints it
```

```bash
python -m pytest tests/test_payment_algorithm.py -v
python -m pytest tests/test_payment_algorithm.py::TestCalculateChangeBreakdown::test_mixed -v
python -m pytest tests/ -k voucher -v
python scripts/render_screens.py payment idle --out /tmp/shots   # just some screens
make PYTHON=/path/to/python test
```

- SIM_MODE: `SIM_MODE=true make run` (a shell var beats `.env`). **Ctrl+Shift+Q** injects a QR payload. Fake USB drive: `SSP/database/sim_usb_drive`.
- Headless on a Pi over SSH: `QT_QPA_PLATFORM=offscreen make run-sim`.

## 3. Logs

```bash
tail -f SSP/logs/app.log                   # everything the app prints, timestamped
journalctl --user -u ssp-kiosk -f          # [pi] the service's own output
cat SSP/logs/crash.log                     # native crashes; look under each "--- pid N ---" marker
```

A dump below a run's "event loop ended" line happened after the app closed.

## 4. Won't start

| Symptom | Check |
|---|---|
| `.env` not found / exits at once | `.env` must be at the repo root; `cp .env.example .env` |
| "already running (pid N)" / exit 3 | `systemctl --user stop ssp-kiosk`, then `make run` |
| Refuses to start with SIM_MODE off | `systemctl status pigpiod`; `systemctl cat pigpiod \| grep ExecStart` must end in `-l` |
| Qt plugin "xcb" error with cv2 | `.venv/bin/pip uninstall -y opencv-python && .venv/bin/pip install "opencv-python-headless>=4.8"` |
| Restart loop | `journalctl --user -u ssp-kiosk -n 50`; the unit restarts every 5 s |
| Dashboard: "ADMIN_DASHBOARD_SECRET_KEY is unset" | set a generated key in `.env` |

## 5. Coins, bills, hoppers  [pi][stop]

```bash
systemctl --user stop ssp-kiosk
python scripts/gpio_scan.py baseline            # nothing happening, motors off
python scripts/gpio_scan.py coins               # acceptors on; insert coins/bills
python scripts/gpio_scan.py hopper A            # runs hopper A for 1 s (B for the other)
python scripts/gpio_scan.py hopper B --seconds 2
python scripts/gpio_scan.py empty A             # run until Ctrl+C
python scripts/gpio_scan.py --help              # also --gap, --no-filter
systemctl --user start ssp-kiosk
```

- Log lines to grep in `app.log`: `Coin ignored`, `Bill ignored` (a count that matched no coin or bill, or pulses outside the width window).
- Wiring comes from `KIOSK_MODEL` (`old` or `new`) in `.env`; single pins can be overridden there.
- `COIN_PULSE_FILTER=false` / `BILL_PULSE_FILTER=false` checks the wiring without the filter.
- A hopper that doesn't see a coin for 1.5 s stops; the rest of the change becomes a Voucher.

## 6. Printer and scanner  [pi]

```bash
lpstat -p                                  # [live] queue state; "disabled" = nothing prints
lpstat -l -p HP_Smart_Tank                 # [live] alerts (media-empty, jam, paused)
lpstat -v                                  # [live] must be ipp://localhost:60000/ipp/print
lpstat -o                                  # [live] jobs still queued
sudo cupsenable HP_Smart_Tank              # re-enable a disabled queue
cancel -a HP_Smart_Tank                    # clear stuck jobs
scanimage -L                               # scanner names (SCANNER_DEVICE in .env)
scripts/printer_watch.sh [seconds] [file]  # [stop] log printer/CUPS signal changes; Ctrl+C
```

Use the fixed `HP_Smart_Tank` queue, not the auto-made one from cups-browsed (`sudo systemctl disable --now cups-browsed`). Full recipe: `docs/KIOSK_PI_SETUP.md` step 8.

## 7. SMS and QR reader  [pi]

```bash
cd SSP && python -c "from managers.sms_manager import get_sms_manager as g; print(g().send_sms_and_close('test'))"   # [stop]
```

- `PHONE_NUMBER` blank or `09XXXXXXXXX` sends nothing.
- QR reader off when `QR_READER_PORT` is blank. Its status shows in Kiosk Admin and in `settings.qr_reader_status`.

## 8. Admin Dashboard (port 8100, separate process)

```bash
make run-admin-dashboard                                    # [sim]
make seed-demo-data                                         # [sim] fills ssp_database.sim.db only
PYTHONPATH=SSP python -m admin_dashboard.cli --help
PYTHONPATH=SSP python -m admin_dashboard.cli create-account --username alice --password '...' --role admin    # or operator
PYTHONPATH=SSP python -m admin_dashboard.cli reset-password --username alice --password '...'
scripts/install_dashboard_service.sh                        # [pi] run at boot (--uninstall to remove)
journalctl -u ssp-admin-dashboard -f                        # [pi] if installed as a system service
ss -ltnp | grep 8100                                        # [pi] expect 127.0.0.1:8100, never 0.0.0.0
```

**Open it from your laptop over SSH** (`localhost` in a laptop browser is the laptop, not the kiosk, so tunnel the port):

```bash
ssh -L 8100:127.0.0.1:8100 <user>@<kiosk-host>              # leave open, then browse to:
# http://127.0.0.1:8100/login
```

The kiosk's own browser uses `http://127.0.0.1:8100/login` directly. It listens on loopback only (`ADMIN_DASHBOARD_HOST`), so `http://<kiosk-ip>:8100` doesn't work, by design.

Accounts exist only through this CLI. With `SIM_MODE=true` it writes to the demo DB, not the real one. Run it from the repo root with `PYTHONPATH=SSP`, not as `python SSP/admin_dashboard/cli.py` (import error).

## 9. Wi-Fi hotspot and portal  [pi]

```bash
sudo python3 scripts/setup_hotspot.py --dry-run     # print what it would do
sudo python3 scripts/setup_hotspot.py               # apply from .env (WIFI_HOTSPOT_ENABLED)
python3 scripts/setup_hotspot.py --root /tmp/stage  # write files under /tmp/stage, run nothing
python scripts/generate_tls_cert.py [output_dir]    # self-signed cert for the portal
```

## 10. Database

```bash
DB=SSP/database/ssp_database.db
sqlite3 $DB ".tables"
sqlite3 $DB "select id,timestamp,error_type,error_message,resolved from error_log order by id desc limit 10;"
sqlite3 $DB "select id,timestamp,status,total_cost,source from transactions order by id desc limit 10;"
sqlite3 $DB "select key,value from settings;"
cp $DB ~/ssp-backup-$(date +%F).db      # copy before any manual edit; the app is writing, so stop it for a clean copy
```

Prefer Kiosk Admin or the Dashboard for edits; they write the `admin_actions` audit row, a raw `sqlite3` update doesn't. Printing statuses: `paid`, `completed`, `print_failed`, `partly_printed`, `digital_failed`.

## 11. Crash hunting  [pi][stop]

```bash
systemctl --user stop ssp-kiosk
UP_SECONDS=25 scripts/exit_crash_loop.sh 40    # start/close the app 40x, count crashes on exit
systemctl --user start ssp-kiosk
```

Exit codes: 139 segfault, 134 abort, 0 clean. Summary goes to `SSP/logs/exit-loop-<time>.txt`.

## Gotchas

- Always navigate with `show_screen()`.
- `managers/payment_handler.py` is dead code; edit `persistent_gpio.py`.
- Keep every screen within 800 logical px tall (`tests/test_screen_render.py`).
- Hardware PRs need a confirmed run on the real kiosk before merge.
