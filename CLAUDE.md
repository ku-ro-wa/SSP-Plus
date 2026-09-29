# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run everything from the **repo root** (`SSP-Plus/`), not from `SSP/`:

```bash
make test      # pytest tests/ -v  (177 tests, no hardware/DB required)
make lint      # flake8 SSP/ --max-line-length=120
make run-sim   # launches the GUI with SIM_MODE=true (no GPIO/CUPS/modem needed)
make run       # launches the GUI against real hardware (kiosk only)
make run-admin-dashboard   # launches the Admin Dashboard (separate process, own port — see below)
```

Run a single test: `python -m pytest tests/test_payment_algorithm.py::TestCalculateChangeBreakdown::test_mixed -v`

`make` auto-detects Python (falls back to `python3`, or the first Windows Python with `pytest` installed when invoked from WSL — see `Makefile`). Override with `make PYTHON=/path/to/python test`.

First-time setup: `cp .env.example .env` and set `SIM_MODE=true` for laptop development. `.env` **must live at the repo root** — `config.py`'s `Config` class resolves it relative to the process's working directory (`.env` by default), and both Makefile targets invoke `python SSP/main_app.py` from the repo root. Running `main_app.py` directly from inside `SSP/` will fail because `.env` isn't there. If `.env` is missing, `config.py` calls `sys.exit(1)` immediately.

SIM_MODE (set via `.env` or as a shell var, which takes precedence — see `make run-sim`) disables GPIO, the CUPS printer submission, and the GSM modem, replacing them with console-logged simulation. It also makes `USBFileManager.get_usb_drives()` (`managers/usb_file_manager.py`) report a fake USB drive instead of doing real OS-level detection, so the `usb` screen auto-navigates to `file_browser` without a physical drive — the fake drive is a local directory (`SIM_USB_DIR` in `.env`, default `SSP/database/sim_usb_drive`) auto-seeded with a placeholder PDF on first run.

## Architecture

### Screen navigation (MVC + QStackedWidget)

`PrintingSystemApp` (`SSP/main_app.py`) owns a `QStackedWidget` and navigates via `show_screen(screen_name)`. `SCREEN_MAP` maps name → index: `idle`, `usb`, `file_browser`, `printing_options`, `payment`, `admin`, `data_viewer`, `thank_you`. Always navigate through `show_screen()` — it calls `on_leave()` on the outgoing screen and `on_enter()` on the incoming one, and (except for `admin`/`thank_you`) redirects to `thank_you` with an error if paper is low (`paper_count <= 3`) or any CMYK cartridge is critically low (`<= 20%`).

Each screen under `screens/<name>/` follows MVC with three files:
- `controller.py` — wires view signals to model methods, calls `show_screen()` for navigation
- `model.py` — business logic, hardware interaction, data
- `view.py` — PyQt5 widgets and layout

Customer flow: `idle` → `usb` → `file_browser` → `printing_options` → `payment` → `thank_you`. `admin` and `data_viewer` are side-paths reached via a PIN dialog (`screens/dialogs/pin_dialog/`).

### Background threads

Two persistent `QThread` managers are started in `PrintingSystemApp.__init__` and stopped in `cleanup()`:
- `DatabaseThreadManager` (`managers/db_threader.py`) — serializes SQLite writes to avoid cross-thread conflicts
- `InkAnalysisThreadManager` (`managers/ink_analysis_threader.py`) — runs PDF ink analysis off the main thread

### Hardware integration

| Component | Manager | Library |
|-----------|---------|---------|
| Printer (CUPS) | `managers/printer_manager.py` + `managers/printer_thread.py` | `subprocess` (`lp`/`lpstat`) |
| Coin/bill acceptors | `managers/persistent_gpio.py` | `pigpio` (GPIO pulse counting) |
| Coin hoppers (change dispenser) | `managers/hopper_manager.py` (`ChangeDispenser`, `HopperController`) | `pigpio` |
| SMS alerts | `managers/sms_manager.py` | `pyserial` (AT commands to GSM modem) |

`pigpio` requires the `pigpiod` daemon. All GPIO code degrades gracefully (simulated mode with console warnings) when `pigpio`/`pigpiod` is unavailable, independent of `SIM_MODE`.

**`managers/payment_handler.py` is dead code.** It's a newer, `.env`-configurable rewrite of the coin/bill acceptor logic (with pulse-width noise filtering) but nothing imports it — `screens/payment/model.py` still wires up `managers/persistent_gpio.py`, whose pins are hardcoded in `__init__` rather than read from config. If you're changing acceptor behavior, edit `persistent_gpio.py`, not `payment_handler.py`.

GPIO pin assignments (hardcoded in `persistent_gpio.py` / `hopper_manager.py`, **not** read from `.env` despite `.env.example` defining `COIN_PIN`/`BILL_PIN`/etc. — those config values are only consumed by the unused `payment_handler.py`):
- Coin acceptor input: GPIO 17; inhibit (active high, HIGH=enabled): GPIO 22
- Bill acceptor input: GPIO 18; inhibit (active low, LOW=enabled): GPIO 23
- Hopper A (₱1 coins): signal GPIO 10, enable GPIO 24 (active low)
- Hopper B (₱5 coins): signal GPIO 11, enable GPIO 25 (active low)

### Database

SQLite at `SSP/database/ssp_database.db` (path is derived from `models.py`'s own location, so it's stable regardless of CWD — unlike `.env`). Schema is created by `database/models.py:init_db()`, called once at startup from `main()`. Tables: `transactions` (has a `source` column, see Admin Dashboard below), `cash_inventory`,
`error_log`, `printer_status`, `cmyk_ink_levels`, `settings`, `sessions`, `email_intake_log`,
`users`, `dashboard_login_log` (the last two are Admin Dashboard accounts/login-audit, unrelated
to the touchscreen's own `ADMIN_PIN`).

All DB access goes through `DatabaseManager` (`database/db_manager.py`). Writes triggered from non-main threads must go through `DatabaseThreadManager` (`db_threader`) to avoid SQLite's same-thread restriction.

### Admin Dashboard (`SSP/admin_dashboard/`)

A separate, authenticated FastAPI/Uvicorn process for kiosk revenue reporting — sibling to
`SSP/webapp/` (the Wi-Fi portal), never started by `main_app.py` or `WebAppThreadManager`.
Start it with `make run-admin-dashboard`; it runs on its own port (`ADMIN_DASHBOARD_PORT`,
default 8100, distinct from the Wi-Fi portal's 8000) so a bug or compromise in the low-trust,
unauthenticated portal can never become a path into this DB-write-capable surface.

Auth is individual accounts in a `users` table, Argon2id-hashed passwords, two roles: `dev`
(full read/write) and `admin` (read-only — unrelated to, and less privileged than, the
touchscreen's `Kiosk Admin`/`ADMIN_PIN`). Accounts are created and passwords reset only via
`admin_dashboard/cli.py`, run by hand on the kiosk — no self-service signup or reset flow.
Login issues a signed cookie session with a 10-hour sliding inactivity timeout
(`ADMIN_DASHBOARD_SESSION_HOURS`); 5 consecutive failed attempts locks the account for
`ADMIN_DASHBOARD_LOCKOUT_MINUTES`; every attempt (success or failure) is written to
`dashboard_login_log`.

`/accounting` (HTML) and `/accounting/data?range=today|week|month|all` (JSON) show per-Source
(`usb`/`wifi`/`email`/`scanner`) revenue and transaction-count aggregates via
`DatabaseManager.get_accounting_summary()` — a `scanner`-sourced row only exists when the scan's
destination was print (a Photocopy); scan-to-email/session-download never produce a
transactions row. `/paper-reset` (the SMS fuzzy-match reset fallback) is `dev`-only.
Real transactions get their `source` value from `screens/print_options/controller.py`'s
`self.source` (set per intake screen — usb/wifi/email/scanner controllers all call
`set_pdf_data(..., source=...)`), carried through `payment/model.py`'s `transaction_data` dict
into `DatabaseManager.log_transaction`, which persists it to `transactions.source`.

Demo/fixture data for developing the dashboard's visuals lives in a completely separate,
`SIM_MODE`-gated SQLite file (`SSP/database/ssp_database.sim.db`), populated by
`admin_dashboard/seed_demo_data.py` — the real `ssp_database.db` is never touched by it.

Tests (`tests/test_admin_dashboard.py`) drive `admin_dashboard.main:app` in-process via
`fastapi.testclient.TestClient`, overriding only the `get_db` dependency (pointed at a temp
SQLite file) — auth, sessions, lockout, role-gating, and aggregate queries all run through
real HTTP requests against the real app, no mocked business logic.

See `docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md` and CONTEXT.md's
"Admin Dashboard" glossary section for the full design and rationale.

### Configuration

All runtime config comes from `.env` via `config.py`'s `get_config()` (global `Config` singleton). `Config._load_env_file()` uses `os.environ.setdefault`, so a shell-exported var always overrides `.env` (this is how `make run-sim` forces `SIM_MODE=true` without editing `.env`). Accessing an unset key raises `KeyError` (see `Config.get`) — there are no silent defaults except `sim_mode`, which returns `False` if unset.

### Print job flow

1. `file_browser` (select file) → `printing_options` (set copies/color/pages) → `payment` (insert coins/bills)
2. `payment` model emits `payment_completed` → `main_app.on_payment_completed()` calls `printer_manager.print_file(...)`
3. `PrinterThread.run()` builds a temp PDF containing only the selected pages (via PyMuPDF/`fitz`), submits it to CUPS with `lp`, then polls `lpstat -l -p <printer>` for job completion, paper jams, and media-empty alerts (sends SMS on jam/no-paper via `sms_manager`)
4. On success, `main_app` decrements paper count and updates coin inventory (received coins added, dispensed change subtracted) directly against the DB, *then* triggers ink analysis
5. `InkAnalysisThreadManager` uses `pdf2image` + OpenCV on the temp PDF to estimate CMYK consumption and updates `cmyk_ink_levels`
6. The temp PDF is deleted only after ink analysis completes (`PrinterManager.cleanup_last_temp_pdf`), since analysis needs it even if the original USB drive was removed

### Payment logic

`PaymentAlgorithmManager` (`managers/payment_algorithm_manager.py`) calculates change feasibility from current ₱1/₱5 coin inventory and suggests payment amounts when exact change can't be made. Min coin thresholds and max change limits are configurable via the `settings` DB table. This is the only manager with dedicated unit tests (`tests/test_payment_algorithm.py`) — it's pure logic with a mocked `DatabaseManager`, no hardware or real DB needed.

## Workflow

`main` is protected — PRs require one review before merge. Branch as `feature/<module>`. Hardware-dependent PRs (GPIO, printer, SMS) need a confirmed run on actual kiosk hardware before merge, since `make run-sim`/CI only exercise the simulated paths.

## Agent skills

### Issue tracker

Issues live as GitHub issues in ku-ro-wa/SSP-Plus, via the gh CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root CONTEXT.md + docs/adr/. See `docs/agents/domain.md`.
