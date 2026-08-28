# Session Summary — Wire Wifi/Email GUI Screens to the Real Backend

**Date:** 2026-07-23 (commit `1ec1098`)
**Scope:** Connects PR #6's GUI Integration (homepage + wifi/email/scanner upload screens) to the intake pipeline built in the prior session (`SessionManager`, `WifiAdapter`, `EmailAdapter`) — closing the gap between UI and backend documented as future work in `SESSION_MANAGER_SESSION_SUMMARY.md` items 2 and 4.

## What this session built

PR #6 ("GUI Integration") had already been merged into `main`: a new homepage with USB/Wi-Fi/Email/Scanner cards, plus wifi/email/scanner screens with a global 60-second countdown timer. But the wifi and email screens were pure UI scaffolding — each had a `# --- DEV BYPASS ---` block that accepted *any* 6-digit code and loaded whichever PDF happened to be sitting in `test_pdfs/`, never touching the real backend. Meanwhile the FastAPI webapp (`WebAppThreadManager`) was already running unconditionally in `main_app.py` and a phone hitting the kiosk's `:8000/upload` already created a real, DB-backed session — the GUI just never read it back. `EmailPollerThreadManager` existed and was fully tested but was never imported or started anywhere — dead code.

This session replaced both DEV BYPASS blocks with real `SessionManager` lookups and started the email poller thread. Scanner was left untouched (no backend exists for it at all), and swapping to a production Gmail account / real captive-portal infra was explicitly deferred to a separate future plan.

```
 Kiosk OTP screen (wifi or email)
        |
        v
 WifiModel/EmailModel.validate_otp(otp_text)
        |
        v
 SessionManager.verify_otp_for_source(source, otp)   <-- new
        |                                  \
        | (hash-match found)                \ (no match)
        v                                     v
 SessionManager.verify_otp(session_id, otp)   "Incorrect or expired code"
        |
        v
 USBFileManager.scan_and_copy_single_pdf_file(file_path)   <-- new
        |
        v
 file_browser screen (source == 'wifi'/'email')
```

### 1. The core design problem: matching a typed OTP to a session

`SessionManager.verify_otp(session_id, otp)` needs a `session_id`, but the kiosk's OTP screen only collects a 6-digit code — unlike the QR path, there's no `session_id` in hand. `_hash_otp()` deliberately salts the hash per-`session_id` (per the file's own header comment, so a DB dump alone can't reproduce a valid OTP), so there's no way to index "the session with this OTP" without weakening that scheme.

Resolution — a narrow, read-only candidate scan restricted to the requesting screen's source, delegating the actual (mutating) verification to the existing `verify_otp()` unchanged:

- `DatabaseManager.get_verifiable_sessions(source)` (`SSP/database/db_manager.py`) — returns sessions for `source` still in `'pending'`/`'locked'` status.
- `SessionManager.verify_otp_for_source(source, otp)` (`SSP/managers/session_manager.py`) — loops those candidates, hash-compares, and only a match falls through to `verify_otp()`. The scan itself never mutates a failed-attempt counter, so looping over unrelated pending sessions can't spuriously lock them out.
- Known, accepted tradeoff: a wrong guess that matches no session can't be attributed to any one session, so it doesn't count toward that session's `MAX_FAILED_ATTEMPTS` lockout. Acceptable given there's normally 0-1 pending session per source at a kiosk, and it's not a new brute-force surface (still ~1e6 salted-hash guesses either way).

### 2. Session-isolated single-file copy — `SSP/managers/usb_file_manager.py`

`scan_and_copy_pdf_files(source_dir)` walks a whole directory — pointing it at a session's upload directory would leak other pending users' files (siblings in `wifi_uploads/`/`email_uploads/`) into this user's `file_browser`. Added `scan_and_copy_single_pdf_file(source_path)`: copies exactly one already-validated file into a fresh temp session directory (no `_auto_eject_usb_drive()` call — nothing to eject), returning the same list-of-dict shape the directory-walk method returns, so `file_browser/model.py`/`view.py` needed no changes. The original file under `wifi_uploads/`/`email_uploads/` stays put and is later swept by `SessionManager.cleanup_expired_sessions()` on natural expiry.

### 3. GUI wiring — `screens/wifi/*`, `screens/email/*`

- `WifiModel`/`EmailModel.validate_otp()` now call `session_manager.verify_otp_for_source(source, otp_text)` against the real DB instead of unconditionally accepting any 6-digit code; `otp_result` signal gains a `file_path` argument.
- `WifiController`/`EmailController._handle_otp_result()` — DEV BYPASS blocks removed; on a valid OTP, the real session's file is copied via `scan_and_copy_single_pdf_file()` and handed to `file_browser`.
- Added `refresh_files()` to both controllers — `file_browser/controller.py` already called `self.main_app.email_screen.refresh_files()` / `wifi_screen.refresh_files()` on rescan/"add another document", but neither method existed yet (a latent crash this change finally starts exercising). Simplest correct behavior: re-show the wifi/email screen so the user re-enters a fresh code.

### 4. Starting the email poller — `SSP/main_app.py`

Mirrors the existing `WebAppThreadManager` start/stop exactly: `EmailPollerThreadManager.from_config()` + `.start()` in `__init__` (wrapped in try/except so a poller construction failure — e.g. greenmail unreachable — doesn't crash kiosk boot), `.stop()` in `cleanup()`.

SIM_MODE is not used to gate any of this — neither the webapp thread nor greenmail is kiosk hardware (the webapp already started unconditionally before this session), so there was nothing hardware-specific to simulate around.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/database/db_manager.py` | modified (+16) | `get_verifiable_sessions(source)` |
| `SSP/managers/session_manager.py` | modified (+14) | `verify_otp_for_source(source, otp)` |
| `SSP/managers/usb_file_manager.py` | modified (+47) | `scan_and_copy_single_pdf_file(source_path)` |
| `SSP/screens/wifi/model.py` | modified | real `validate_otp()`, `file_path` in signal |
| `SSP/screens/wifi/controller.py` | modified | DEV BYPASS removed, `refresh_files()` |
| `SSP/screens/email/model.py` | modified | same as wifi, `source="email"` |
| `SSP/screens/email/controller.py` | modified | same as wifi, drops unused `import os` |
| `SSP/main_app.py` | modified (+14/-2) | start/stop `EmailPollerThreadManager` |
| `tests/test_session_manager.py` | modified (+60) | `get_verifiable_sessions` on `FakeDBManager`, `TestVerifyOtpForSource` (5 cases) |

## Testing guide

```bash
make test    # 68 passed (63 existing + 5 new TestVerifyOtpForSource cases)
make lint    # no new violations
```

Also verified live, not just via unit tests:
- Instantiated the full `PrintingSystemApp` under `SIM_MODE` — confirmed `email_poller_thread` starts and correctly no-ops when greenmail isn't running.
- Created a real wifi-sourced session via `SessionManager.create_session()`, drove `WifiModel.validate_otp()` with both a wrong OTP (rejected) and the correct OTP (verified, returned the real file path, DB status flipped to `verified`).
- Ran `scan_and_copy_single_pdf_file()` against a real PDF from `test_pdfs/`, confirmed correct copy/page-count/cleanup.
- Incidental fix: `psutil` was pinned in `requirements.txt` but missing from `.venv`, which blocked `main_app.py` from importing at all — installed it (already-pinned dependency, not a new one).

Manual, end-to-end (needs the real thing running):
1. **Wi-Fi**: `make run-sim`, then `curl -F "file=@test.pdf;type=application/pdf" http://127.0.0.1:8000/upload`, note the returned OTP, enter it on the kiosk wifi screen → lands on `file_browser` with that file.
2. **Email**: `cd SSP/managers/adapters/greenmail && docker compose up -d`, send a test email to `test@example.com` (subject containing `EMAIL_SUBJECT_KEYWORD`, PDF attached), wait one poll interval, read the OTP from the auto-reply via greenmail's web UI (`localhost:8080`), enter it on the kiosk email screen → lands on `file_browser`.
3. **Negative**: wrong OTP on either screen → "Incorrect or expired code"; 5 wrong attempts against a real pending session → locked.

## Future considerations

1. **Production Gmail SMTP/IMAP swap and WiFi captive-portal infra** — deliberately out of scope this session, planned as a separate future effort.
2. **Scanner screen** — still a stub; no backend exists for it at all.
3. **`cleanup_expired_sessions()` still has no scheduler** (carried over from `SESSION_MANAGER_SESSION_SUMMARY.md` item 5) — unaffected by this session's work.
4. **Single-file assumption baked into `scan_and_copy_single_pdf_file()` and the OTP→file plumbing** — this became the starting point for the very next session's work (see `MULTI_FILE_WIFI_UPLOAD_SESSION_SUMMARY.md`), which generalized the wifi intake path (and, mechanically, the email path) to carry a list of files per session instead of exactly one.
