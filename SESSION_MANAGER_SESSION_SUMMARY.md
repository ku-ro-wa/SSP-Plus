# Session Summary — Intake Pipeline (Session Manager, Wi-Fi Upload, Email Adapter)

**Date:** 2026-07-16
**Scope:** Phase 3 (Session Manager) and the intake side of Phase 4 (Wi-Fi Transfer) and Phase 5 (Email Submission) from `roadmap-planning.txt`.

## What this session built

A three-layer intake pipeline: two adapters (Wi-Fi, email) that each validate
input from their modality and hand off to a shared, modality-agnostic
`SessionManager`, which issues an OTP + QR code and tracks pickup state.
Neither adapter talks to the database directly, and `SessionManager` never
branches on which adapter called it.

```
 Wi-Fi captive portal          Dedicated Gmail inbox (via greenmail in dev)
        |                                |
        v                                v
 webapp/routers/upload.py        EmailPollerThreadManager (background thread)
        |                                |
        v                                v
 WifiAdapter.handle_upload()     EmailAdapter.poll_inbox() -> _handle_message()
        |                                |
        +--------------> SessionManager.create_session() <------+
                                  |
                                  v
                    sessions table (OTP hash, QR bytes returned once)
                                  |
                    WifiAdapter renders QR on the       EmailAdapter emails
                    upload confirmation page             the QR/OTP back via
                                                           EmailAdapter.send_response()
```

### 1. Session Manager — `SSP/managers/session_manager.py`

The core of the pipeline, built first since both adapters depend on it.

- `SessionManager.create_session(source, file_path, original_filename, metadata)` — generates a 16-char `session_id` (`secrets.token_hex`) and a 6-digit OTP (`secrets.randbelow`), computes expiry from the operator-configurable `session_expiry_minutes` setting (DB `settings` table, defaults to 15 min), and returns a `Session` dataclass (`session_id`, `otp`, `qr_bytes`, `file_path`, `expires_at`).
- The OTP is **only ever returned once**, at creation time. The DB stores `sha256(f"{session_id}:{otp}")` — salted with `session_id` so a DB dump alone can't be turned into valid OTPs via a precomputed table (a bare 6-digit OTP is only 1,000,000 possibilities).
- `verify_otp(session_id, otp)` / `verify_qr_payload("session_id:otp")` — the single verification path for both a QR scan and manual entry. Handles locked/expired/already-verified/wrong-OTP branches; locks the session after `MAX_FAILED_ATTEMPTS = 5` (fixed per `project_objectives.txt`, not configurable).
- `cleanup_expired_sessions()` — deletes expired sessions' files and DB rows. **Not yet wired to a scheduler** (see Future Considerations).
- New `sessions` table added to `SSP/database/models.py`, with matching CRUD methods on `DatabaseManager` (`SSP/database/db_manager.py`).

### 2. Wi-Fi Upload — `SSP/managers/adapters/wifi_adapter.py` + `SSP/webapp/routers/upload.py`

- `WifiAdapter.handle_upload(file_obj, filename, content_type, metadata)` — validates MIME type and the `%PDF` magic-byte header (both required per `project_objectives.txt`), enforces a configurable max size, saves the file under a fresh UUID name (the original filename is stored as metadata only, never used to build a path — the incoming filename otherwise means the multipart request offers a path-traversal vector), and calls `session_manager.create_session(source='wifi', ...)`.
- `webapp/routers/upload.py` — `GET /upload` serves the form, `POST /upload` wires the request to `WifiAdapter` via a new `get_wifi_adapter()` FastAPI dependency (`webapp/dependencies.py`), and renders the OTP + base64 QR PNG in the confirmation page.
- No FastAPI import anywhere in `WifiAdapter` — it's plain Python, testable the same way as the existing `PaymentAlgorithmManager`.

### 3. Email Intake — `SSP/managers/adapters/email_adapter.py` + `email_client.py` + `SSP/managers/email_poller_thread.py`

Built from your existing prototype scripts (`email_test.py`, `email_check.py`, `email_system.py` in the scratch `email_test/` folder) and your in-progress `EmailAdapter` skeleton, adapted rather than ported 1:1:

- `ImapClient` / `SmtpClient` (`email_client.py`) — thin wrappers around `imaplib`/`smtplib`, injected into `EmailAdapter` rather than called directly, so `_handle_message`/`poll_inbox`/`send_response` are testable with fakes and no real IMAP/SMTP server. Greenmail (dev) and the eventual dedicated Gmail account are both just different `EMAIL_*` config values passed to these constructors — no code branches on which one is active.
- `EmailAdapter._handle_message(raw_bytes)` — parses the message, checks the subject for `EMAIL_SUBJECT_KEYWORD` (case-insensitive), extracts the first `application/pdf` part, re-validates it against the `%PDF` magic bytes (email `Content-Type` headers are just as spoofable as the wifi upload's), saves it, and calls `session_manager.create_session(source='email', ...)`. Returns a `MessageResult(outcome, session, message_id, sender)` — outcome is one of `accepted` / `rejected_subject` / `rejected_attachment` / `error`, matching the `email_intake_log` table's schema exactly. Never raises.
- `EmailAdapter.send_response(recipient_email, session)` — emails back the OTP and QR **that `SessionManager` already generated**. This is the one place the prototype couldn't be ported 1:1: the prototype's `send_response` minted its own OTP/QR inline, which would have meant two independent, disagreeing sources of truth. Here, OTP/QR generation is exclusively `SessionManager`'s job.
- `EmailAdapter.poll_inbox()` — one full poll cycle: UID SEARCH UNSEEN, process each new message, log the outcome, mark it Seen, reply if accepted. Uses **IMAP UID + UIDVALIDITY** (not sequence numbers, which the prototype used and which aren't stable across sessions) for dedup against the new `email_intake_log` table.
- `EmailPollerThreadManager` (`managers/email_poller_thread.py`) — runs `poll_inbox()` on a `threading.Event`-driven interval loop in a background thread (same `start()`/`stop()` shape as `WebAppThreadManager`, so it can drop into `main_app.py`'s `__init__`/`cleanup()` unchanged when wired in). A single failed poll cycle is logged, not fatal. `EmailPollerThreadManager.from_config()` builds the whole `ImapClient`→`SmtpClient`→`SessionManager`→`EmailAdapter` chain from `config.py`/`.env` in one call.

### Bugs fixed along the way (not new work, but worth recording)

- `webapp/dependencies.py` had a **duplicate `get_wifi_adapter()`** at the bottom of the file (a stub importing from a nonexistent `adapters.wifi_adapter` path). Since Python keeps the last definition of a function in a module, this silently shadowed the real dependency and would have crashed the route on first use. Removed.
- The original `email_adapter.py` sketch called `self.imap_client` and `self.db.execute(raw SQL)` without either being defined — `imap_client` is now constructor-injected, and the raw SQL became proper `db_manager.get_email_intake_log()` / `log_email_intake()` methods, matching how every other table (`sessions`, `cash_inventory`, etc.) is accessed in this codebase.
- Added a pre-check (`get_email_intake_log` before doing any work in `poll_inbox`) that "only mark Seen if inserted" alone didn't fully cover: if `mark_seen` fails *after* the log insert succeeds (crash, dropped connection), the message looks UNSEEN again next cycle. Without the pre-check, that would silently create a second session for the same email.
- `.gitignore` was only ignoring `SSP/database/wifi_uploads/`, not `SSP/database/email_uploads/` — fixed before writing this doc.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/managers/session_manager.py` | new (162 lines) | OTP + QR session core |
| `SSP/managers/adapters/wifi_adapter.py` | new (60 lines) | Wi-Fi upload validation |
| `SSP/managers/adapters/email_adapter.py` | new (143 lines) | Email intake logic |
| `SSP/managers/adapters/email_client.py` | new (93 lines) | IMAP/SMTP wrappers |
| `SSP/managers/adapters/__init__.py` | new | package marker |
| `SSP/managers/email_poller_thread.py` | new (83 lines) | background polling loop |
| `SSP/webapp/routers/upload.py` | new (53 lines) | `GET`/`POST /upload` |
| `SSP/webapp/dependencies.py` | modified | `get_wifi_adapter()` (+ removed stray duplicate) |
| `SSP/webapp/main.py` | modified | mounts `upload.router` |
| `SSP/database/models.py` | modified | `sessions`, `email_intake_log` tables |
| `SSP/database/db_manager.py` | modified | CRUD for both new tables |
| `SSP/config.py` | modified | Wi-Fi/email settings, all safely defaulted |
| `.env.example` | modified | documents new settings, greenmail defaults |
| `.gitignore` | modified | ignore uploaded/extracted files |
| `requirements.txt` | modified | `qrcode[pil]`, `python-multipart` |
| `tests/test_session_manager.py` | new (198 lines) | + shared `FakeDBManager` |
| `tests/test_wifi_adapter.py` | new (97 lines) | |
| `tests/test_upload_route.py` | new (74 lines) | |
| `tests/test_email_adapter.py` | new (214 lines) | |
| `tests/test_email_poller_thread.py` | new (101 lines) | |

## Testing guide

Everything below runs offline — no greenmail, no real Gmail, no Wi-Fi AP, no kiosk hardware.

```bash
# from the repo root (SSP-Plus/)
make test                                      # full suite (63 tests)
.venv/bin/python -m pytest tests/ -v           # same, verbose
.venv/bin/python -m pytest tests/test_session_manager.py -v
.venv/bin/python -m pytest tests/test_wifi_adapter.py tests/test_upload_route.py -v
.venv/bin/python -m pytest tests/test_email_adapter.py tests/test_email_poller_thread.py -v
make lint                                      # flake8, clean on everything touched this session
```

What's covered:
- `SessionManager`: OTP format, expiry (default + operator-configured), lockout after 5 failed attempts, QR payload round-trip, expired-session file cleanup, salted-hash storage.
- `WifiAdapter`: valid/invalid MIME, missing/wrong magic bytes, oversized file, empty file, path-traversal filename safety, metadata passthrough. `test_upload_route.py` drives the actual FastAPI route via `TestClient` with `get_wifi_adapter` overridden to a temp-dir-backed adapter.
- `EmailAdapter`: subject/attachment validation (including case-insensitive subject match and spoofed-MIME rejection), oversized attachments, `_handle_message` exception safety, full `poll_inbox()` cycles (accept+reply, reject+no-reply, dedup-on-relog, multiple messages in one cycle), and `send_response`'s actual MIME structure (OTP in body, QR as attachment).
- `EmailPollerThreadManager`: start/stop lifecycle, polling at interval, survives an exception mid-cycle, thread is a daemon, `from_config()` wiring (with `EMAIL_UPLOAD_DIR` etc. overridden via `monkeypatch.setenv` so it never touches a real path or opens a real connection).

What's **not** covered (needs the real thing running):
- No test exercises a real greenmail container end-to-end. `managers/adapters/greenmail/docker-compose.yml` exists (`docker compose up`) but nothing in `tests/` starts it — would need a separate, opt-in integration test marked to skip when Docker isn't available.
- No test exercises the FastAPI app behind real TLS/Uvicorn (`webapp_thread.py`) or a real captive portal.
- No test of the Wi-Fi upload path from an actual phone/browser on the kiosk's AP.

## Future considerations

1. **Migrate off greenmail to the real dedicated Gmail account.** By design this should be a pure `.env` change — set `EMAIL_USE_SSL=true`, `EMAIL_IMAP_PORT=993`, `EMAIL_SMTP_PORT=465`, `EMAIL_USER`/`EMAIL_PASSWORD` to a Gmail app password, and `EMAIL_SUBJECT_KEYWORD` to whatever real customers will type. No code should need to change. Verify this claim early — Gmail's IMAP has quirks (e.g. `\Seen` flag handling, folder naming) that greenmail may not perfectly emulate. `roadmap-planning.txt`'s Phase 5 also calls for the SIM7600G-H 4G HAT as the physical data path once off Wi-Fi — that's a networking/hardware concern below `ImapClient`, not a code change to it.

2. **Wire `EmailPollerThreadManager` into `main_app.py`.** Deliberately left undone this session (per your call — no screens depend on it yet). When ready: `self.email_poller = EmailPollerThreadManager.from_config()` + `.start()` in `__init__`, `.stop()` in `cleanup()`, mirroring `webapp_thread`.

3. **Captive portal (RaspAP + Nodogsplash).** `webapp_thread.py` + `scripts/generate_tls_cert.py` already give the Wi-Fi upload portal TLS; what's missing is the actual AP/DNS-interception layer that redirects a connecting phone to `/upload`. That's Pi-specific infrastructure config, not application code — document as a deployment script per the roadmap, can be mocked with a regular laptop hotspot during dev.

4. **No GUI screens consume any of this yet.** Concretely still needed:
   - A kiosk screen that accepts OTP entry (manual keypad, mirroring `screens/dialogs/pin_dialog/`) or a QR scan from the LogicOwl OJ-HS-23 (HID keyboard-emulation input in real deployment, mocked as keyboard input in `SIM_MODE`) and calls `session_manager.verify_qr_payload()` / `verify_otp()` to retrieve the file for printing.
   - An admin-dashboard view into `sessions` and `email_intake_log` (accepted/rejected counts, lockouts) — natural fit for the Phase 7 Admin Dashboard work already scoped in the roadmap.
   - Wi-Fi upload's confirmation page currently *is* the only "UI" (rendered HTML in `upload.py`) — decide whether that's the permanent design or whether the kiosk itself should show something once the file's picked up.

5. **`cleanup_expired_sessions()` has no scheduler.** Needs the same background-thread treatment as `EmailPollerThreadManager` (or could piggyback on it) — currently callable but nothing calls it periodically, so expired session files/rows will accumulate until something does.

6. **`SmtpClient` only supports SSL (port 465) or fully plaintext (greenmail).** No STARTTLS (port 587) path. Add it if the real Gmail deployment ends up needing 587 instead of 465.
