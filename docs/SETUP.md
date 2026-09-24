# Dev Environment Setup

This guide gets you from a fresh clone to a working local dev environment. No kiosk hardware required — everything runs in simulation mode on your laptop.

---

## Windows

The recommended approach uses **Windows Python** (for native GUI rendering) with **WSL** (for `make` and bash tooling). You do not need to install Python inside WSL.

### 1. Install WSL2

If you don't have WSL2 yet, open PowerShell as Administrator and run:

```powershell
wsl --install
```

Restart when prompted. This installs Ubuntu by default. Open the Ubuntu app once to finish the initial setup (create a username/password).

To check your WSL version later: `wsl --list --verbose`

### 2. Install Python 3.11 for Windows

Download the **Windows installer** from [python.org/downloads](https://www.python.org/downloads/) — pick Python **3.11.x** (scroll past the latest if needed).

During install:

- Check **"Add python.exe to PATH"** on the first screen
- Use the default install location (`C:\Users\<you>\AppData\Local\Programs\Python\Python311\`)

Verify from PowerShell:
```powershell
py -3.11 --version   # should print Python 3.11.x
```

### 3. Install `make` in WSL

Open your WSL (Ubuntu) terminal:

```bash
sudo apt update && sudo apt install make -y
```

### 4. Clone the repo and install dependencies

From your WSL terminal:

```bash
# Clone into a Windows path so both WSL and Windows can access it
cd /mnt/c/Users/<your-windows-username>/Documents
git clone <repo-url> SSP-Plus
cd SSP-Plus
```

Install Python packages using the Windows Python (note: run this from WSL or PowerShell, same result):

```bash
/mnt/c/Users/<your-windows-username>/AppData/Local/Programs/Python/Python311/python.exe -m pip install -r requirements.txt
```

Or from PowerShell:

```powershell
py -3.11 -m pip install -r requirements.txt
```

### 5. Configure your environment (Windows)

```bash
cp .env.example .env
```

Open `.env` and set `SIM_MODE=true`. This disables GPIO, CUPS, and the GSM modem so the app runs on your laptop without any hardware attached.

```env
SIM_MODE=true
```

Leave all other values at their defaults for now — they only matter when running on the actual kiosk.

### 6. Verify on Windows

From your WSL terminal in the repo root:

```bash
make test      # should show 16 passed
make lint      # style check, a few warnings are OK
make run-sim   # opens the kiosk GUI on your Windows desktop
```

The `make run-sim` command launches `python.exe` as a native Windows process, so the PyQt5 window appears directly on your Windows desktop — no X11 server needed.

---

## macOS

### 1. Install Xcode Command Line Tools

```bash
xcode-select --install
```

This gives you `git`, `make`, and the C compiler. If it says already installed, skip it.

### 2. Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the prompts. On Apple Silicon (M1/M2/M3), the installer will ask you to add Homebrew to your PATH — do that step.

### 3. Install Python and system dependencies

```bash
brew install python poppler
```

- `python` gives you `python3` and `pip3`
- `poppler` is required by `pdf2image` for PDF rendering

### 4. Clone the repo and install dependencies

```bash
cd ~/Documents   # or wherever you keep projects
git clone <repo-url> SSP-Plus
cd SSP-Plus
pip3 install -r requirements.txt
```

### 5. Configure your environment (macOS)

```bash
cp .env.example .env
```

Open `.env` and set `SIM_MODE=true`:

```env
SIM_MODE=true
```

### 6. Verify on macOS

```bash
make test      # should show 16 passed
make lint      # style check
make run-sim   # opens the kiosk GUI on your Mac
```

---

## How `make` targets work

| Command | What it does | Hardware needed? |
| --------- | ------------- | ----------------- |
| `make test` | Runs the pytest suite | No |
| `make lint` | Runs flake8 static analysis | No |
| `make run-sim` | Launches the full GUI in simulation mode | No |
| `make run` | Launches the full GUI with real hardware | Yes (kiosk only) |

**`make lint`** checks Python style: line length, unused imports, undefined names. It won't catch logic bugs, but it's a quick sanity check before pushing.

**SIM_MODE** disables three hardware interfaces:
- GPIO (coin/bill acceptors, hoppers) — simulated with console output
- CUPS printer — print jobs are logged but not sent
- GSM modem — SMS alerts are logged but not sent

---

## Testing the FastAPI backend (`SSP/webapp`)

The webapp is a normal FastAPI app mounted inside the kiosk GUI (`WebAppThreadManager` starts it on a background thread), so you can test it at three levels depending on what you're checking.

### 1. Automated tests (fastest — no server, no GUI)

```bash
make test
```

`tests/test_webapp.py` uses FastAPI's `TestClient` to drive the app in-process — no port is actually opened. This is what CI/reviewers will run, so it should be your first check after any webapp change.

### 2. Standalone server with auto-reload (fastest way to poke at it manually)

You don't need to launch the full kiosk GUI to hit an endpoint. Run Uvicorn directly against the `webapp` package:

```bash
SIM_MODE=true .venv/Scripts/python.exe -m uvicorn webapp.main:app --app-dir SSP --reload
```

(`python3 -m uvicorn ...` on Mac/Linux.) `--app-dir SSP` puts `SSP/` on the import path — the same thing that happens implicitly when you run `SSP/main_app.py` directly — so `config`, `webapp`, and `database` all resolve. `--reload` restarts the server on file changes.

Then, with the server running:
- `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- `http://127.0.0.1:8000/docs` → interactive Swagger UI (auto-generated from route type hints; only served when `API_DOCS_ENABLED=true` in `.env` — it's off by default, per `project_objectives.txt`'s "disabled in production" requirement)

### 3. Full integration (GUI + webapp thread together — closest to production)

```bash
make run-sim
```

This is the real startup path: `WebAppThreadManager` boots Uvicorn on a background thread as part of `PrintingSystemApp.__init__`. Same `/health` / `/docs` URLs work while the kiosk window is open. Use this to confirm the webapp thread starts/stops cleanly alongside the GUI (`cleanup()` calls `webapp_thread.stop()`), not just that the routes work in isolation.

---

## Email + Wi-Fi end-to-end (on a laptop)

Drives both intake workflows all the way through to a simulated print + a logged
transaction, using `make run-sim` — no kiosk hardware, no RaspAP/Nodogsplash, no
4G modem. The Wi-Fi portal is served by the same in-process Uvicorn thread the
kiosk already runs (see `docs/adr/0001-wifi-portal-in-process-uvicorn-self-signed-tls.md`).

### One-time setup

**1. TLS cert for the Wi-Fi portal** (optional — skip for plain HTTP):

```bash
python scripts/generate_tls_cert.py          # writes certs/cert.pem + certs/key.pem
```

`.env` already points `WIFI_TLS_CERTFILE` / `WIFI_TLS_KEYFILE` at those paths.
When both files exist the portal serves HTTPS; otherwise it logs one line and
serves plain HTTP. The cert is self-signed, so phones show a "not private"
warning — click through it.

**2. Dedicated Gmail account** (for the email workflow):

- Use a throwaway Google account, not a personal one.
- Turn on 2-Step Verification (Google Account → Security).
- Create an **App Password** (Security → 2-Step Verification → App passwords).
  It's 16 characters; paste it into `.env` with the spaces removed.
- In `.env`, set:

  ```env
  EMAIL_USER=your-dedicated-address@gmail.com
  EMAIL_PASSWORD=your16charapppassword
  ```

  The host/port/SSL lines in `.env` are already set for Gmail
  (`imap.gmail.com:993`, `smtp.gmail.com:465`, `EMAIL_USE_SSL=true`). Leaving
  `EMAIL_USER` / `EMAIL_PASSWORD` blank falls back to the greenmail dev server.

### Run it

```bash
make run-sim
```

At boot you'll see one line telling you whether the portal came up on HTTP or
HTTPS, and (if `EMAIL_USER` is set) the email poller starts on a 20s interval.

**Wi-Fi workflow:**

1. On the kiosk, go to **Wi-Fi** from the homepage — the screen shows the portal
   URL (`http(s)://<this-machine-LAN-IP>:8000/upload`) and a QR of it.
2. From a phone on the same network (or from this machine, using
   `https://127.0.0.1:8000/upload` as a quick check), open that URL, stage one or
   more PDFs, and press **Confirm Upload**.
3. The success page shows a 6-digit code. Type it into the kiosk Wi-Fi screen.
4. You land on `file_browser` with the uploaded file(s) → pick pages →
   `print_options` → `payment`. With no `pigpio` on the laptop, the payment
   screen shows **simulation buttons** — click coins until the total is covered.
5. The job "prints" (logged to the console in sim mode), a `transactions` row is
   written, and the paper count decrements. `thank_you` screen confirms.

**Email workflow:**

1. From any mail client, send an email **to the dedicated Gmail address** with
   `DEMO_TRIGGER` somewhere in the subject and a **PDF attached**.
2. Within ~20s the poller extracts the PDF and emails a reply back to the sender
   with the 6-digit code and a QR. (The reply can land in spam.)
3. On the kiosk, go to **Email** — the screen shows the address + keyword. Type
   the code from the reply.
4. Same as Wi-Fi from step 4 onward.

### Negative checks

- Wrong code on either screen → "Incorrect or expired code".
- 5 wrong attempts against a real pending session → session locked.
- Email with no `DEMO_TRIGGER` in the subject, or no PDF attached → no reply,
  nothing queued (logged in `email_intake_log` as `rejected_subject` /
  `rejected_attachment`).
- Non-PDF upload, or a `.pdf` without a real `%PDF` header → the portal rejects
  the whole batch with an error banner, nothing written to disk.

### Repeating a run

Each email run needs a **freshly-sent** email: Gmail marks handled messages
`\Seen` and `email_intake_log` dedupes by IMAP UID, so re-sending the same
message won't re-trigger. Wi-Fi has no such constraint — just upload again.

---

## Admin Dashboard (`SSP/admin_dashboard`)

A separate, authenticated FastAPI/Uvicorn process for kiosk revenue reporting — not
started by `make run-sim`/`make run`, and not part of the kiosk GUI or the Wi-Fi
portal. It has its own port so a bug or compromise in the low-trust, unauthenticated
Wi-Fi portal can never become a path into this DB-write-capable surface.

### 1. Configure your environment

Same `.env` as everything else (`cp .env.example .env`, `SIM_MODE=true`). Relevant
dashboard-specific vars, already set to sane defaults in `.env.example`:

```env
ADMIN_DASHBOARD_PORT=8100
ADMIN_DASHBOARD_SESSION_HOURS=10
ADMIN_DASHBOARD_LOCKOUT_MINUTES=15
```

### 2. Create an account

There's no self-service signup — accounts are created by hand via the CLI:

```bash
PYTHONPATH=SSP python -m admin_dashboard.cli create-account --username you --password yourpassword --role dev
```

The CLI writes to the same DB file the dashboard reads: with `SIM_MODE=true` that's the
demo file `SSP/database/ssp_database.sim.db`, not the real `ssp_database.db` (it prints
which one on every run). Create accounts with the same `SIM_MODE` you'll run the
dashboard with.

(From the repo root, same as `make run-admin-dashboard` — `PYTHONPATH=SSP` is what lets
`admin_dashboard`/`database` resolve as importable packages.) Roles are `dev` (full
read/write, including the dev-only `/paper-reset` endpoint) and `admin` (read-only) —
unrelated to, and less privileged than, the touchscreen's own `Kiosk Admin`/`ADMIN_PIN`.
The password is Argon2id-hashed before it's stored in the `users` table. Reset a
forgotten password the same way:

```bash
PYTHONPATH=SSP python -m admin_dashboard.cli reset-password --username you --password newpassword
```

### 3. Run it

```bash
make run-admin-dashboard
```

This launches Uvicorn directly against the `admin_dashboard` package on
`ADMIN_DASHBOARD_PORT` (default 8100). It's a standalone process — run it alongside
`make run-sim` in a separate terminal if you want real transactions to show up, or on
its own against whatever's already in `SSP/database/ssp_database.db`.

- `http://127.0.0.1:8100/` → redirects to `/accounting`; any dashboard page visited
  without a valid session redirects to the `/login` sign-in form
- `http://127.0.0.1:8100/login` → sign in with the account you created above
- `http://127.0.0.1:8100/accounting` → per-source (`usb`/`wifi`/`email`/`scanner`)
  revenue and transaction-count view, with a `range=today|week|month|all` filter
- Five consecutive failed logins locks that account for
  `ADMIN_DASHBOARD_LOCKOUT_MINUTES`; every attempt is written to
  `dashboard_login_log`

### 4. Seed demo data (optional)

To see the accounting view populated without running real transactions through the
kiosk, seed a separate demo database (never touches your real `ssp_database.db`):

```bash
make seed-demo-data
```

This writes fixture rows to `SSP/database/ssp_database.sim.db`, which the dashboard
reads instead of the real DB when `SIM_MODE=true`.

### 5. Automated tests

```bash
make test
```

`tests/test_admin_dashboard.py` drives `admin_dashboard.main:app` in-process via
FastAPI's `TestClient` — auth, sessions, lockout, role-gating, and the accounting
aggregate queries all run through real HTTP requests against the real app, no
mocked business logic, no port actually opened.

See `docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md` for the
full design (why a separate process/port, the auth model, what's deferred to a
later remote-access phase).

---

## Workflow

```
main ← PRs only (one review required before merge)
feature/<module> ← your working branch
```

1. Branch off main: `git checkout -b feature/your-module`
2. Develop and test locally with `make test`
3. Open a PR to main; another dev reviews before it merges
4. Hardware-dependent PRs need a confirmed run on the kiosk before merge

---

## Troubleshooting

**`make test` — module not found**
Run `pip install -r requirements.txt` (or `py -3.11 -m pip install -r requirements.txt` on Windows). On Mac also check `brew install poppler`.

**`make run-sim` — `.env` not found**
Run `cp .env.example .env` from the repo root. The app expects `.env` in the same directory you run `make` from.

**`make run-sim` — SIM_MODE isn't respected (hardware still errors)**
Make sure `SIM_MODE=true` is in your `.env`, OR that you're running `make run-sim` (not `make run`). The shell env set by `make run-sim` takes precedence over `.env`.

**Windows: emoji / Unicode crash on startup (`UnicodeEncodeError: 'charmap'`)**
The Makefile already passes `-X utf8` to Python which fixes this. If you're running Python directly (not via `make`), add the flag: `python.exe -X utf8 SSP/main_app.py`.

**Windows: `make` says "Permission denied" for a Python command**
The Makefile auto-detects the first Windows Python that has `pytest` installed. If you installed Python 3.13 but only have `pytest` in 3.11, make sure you ran `pip install` for the right version (`py -3.11 -m pip install -r requirements.txt`).

**Mac: `PyQt5` install fails on Apple Silicon**
Try: `pip3 install --upgrade pip && pip3 install PyQt5`. The wheels include Qt bundled and support arm64.
