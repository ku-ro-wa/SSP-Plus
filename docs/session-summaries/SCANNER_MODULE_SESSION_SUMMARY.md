# Session Summary — Scanner Module (Scan-to-Print, Scan-to-Email, Scan-to-Wi-Fi-Download)

**Date:** 2026-09-17
**Scope:** Phase 6 from `docs/roadmap-planning.txt`, implementing objectives-doc
items 6-8 (scanning, photocopying, the scanner module itself) end to end. Builds
directly on the intake infrastructure from `SESSION_MANAGER_SESSION_SUMMARY.md`
and `WIFI_EMAIL_END_TO_END_SESSION_SUMMARY.md` — the `SessionManager`/OTP/QR
pattern proven there for Wi-Fi and email *intake* is reused here in the opposite
direction, for scan *output*. Before this session `screens/scanner/*` was a pure
UI stub that faked a successful scan and dev-bypassed into `test_pdfs/`; there
was no hardware abstraction, no multi-page capture, and no destination routing.

```
 HP Smart Tank 580 (flatbed, no ADF)
        |  scanimage -d <device> --format=png --resolution <dpi>
        v
 SaneAirscanScanner / SimScanner  (managers/scanner.py)
        |
        v
 ScannerManager (start_session / scan_page / rescan_last / cancel / finish)
        |  finish() composes pages -> one PDF via fitz
        v
 screens/scanner  --scan_finished-->  screens/scan_destination
                                            |                    \
                                    "Print Now"              "Send via Wi-Fi"
                                            |                        |
                              printing_options/payment      ScanAdapter.handle_scan()
                              (existing pipeline, untouched)         |
                                                            SessionManager.create_session(source="scan")
                                                                      |
                                                              screens/scan_result (QR + OTP)
                                                                      |
                                                     user's own phone -> GET/POST /redeem
                                                                      |
                                                     verify_otp_for_source_with_id("scan", otp)
                                                                      |
                                                        /redeem/download   /redeem/email
```

## What this session built

### 1. Hardware abstraction — `SSP/managers/scanner.py`, `scanner_manager.py`, `scanner_thread.py`

The objectives doc specifies sane-airscan (eSCL/AirScan, driverless) against the
HP Smart Tank 580, but there's no maintained python-sane binding worth adding as
a dependency — `scanimage` is the same CLI sane-airscan itself wraps. This
mirrors `printer_thread.py`'s existing choice to shell out to `lp`/`lpstat`
rather than binding directly to CUPS, so `SaneAirscanScanner.scan_page(dpi)`
shells to `scanimage -d <device> --format=png --mode=Color --resolution <dpi>`,
capturing stdout to a file (scanimage streams PNG bytes to stdout, it doesn't
write to a path itself). `FileNotFoundError`/`TimeoutExpired`/`CalledProcessError`/
zero-byte output all map to one `ScannerError`, with any partial file cleaned up.
No ADF/geometry flags — flatbed only, full-bed default, one page per call, per
the hardware constraint stated in the objectives doc. The device string itself
is operator-obtained (`scanimage -L` on the kiosk once sane-airscan is
installed) and set via `.env`, not auto-discovered — eSCL device indices aren't
stable across reboots, so auto-discovery would be actively worse than a fixed
string.

`SimScanner` seeds a small fixed number of canned page PNGs (built with `fitz`,
already a dependency — no new package needed) into a sim directory on first
use, the same seed-once idea as `USBFileManager`'s `SIM_USB_DIR`. Each
`scan_page()` call copies the next canned file round-robin to a *fresh* temp
path, so repeated scans and rescans behave like real hardware producing a new
file every time rather than handing back the same path repeatedly.

`ScannerManager` (pure Python, no PyQt import — directly unit-testable the same
way `PaymentAlgorithmManager` is) owns page accumulation, `rescan_last()`
(deletes the last page file and scans a replacement in its place, keeping the
same page number), `cancel()`, and `finish()`, which combines the accumulated
page images into a single PDF via `fitz.open(image).convert_to_pdf()` →
`insert_pdf`, deleting the source images afterward. `ScannerThread(QThread)` is
a *generic* wrapper that runs any bound `ScannerManager` method and emits
`operation_succeeded(dict)`/`operation_failed(str)`, rather than one thread
subclass per operation — `start_session()`/`cancel()` are cheap file-IO and
called directly on the main thread; only `scan_page`/`rescan_last`/`finish` go
through the thread since real hardware can block for tens of seconds.

### 2. Capture UI and photocopy routing — `screens/scanner/*` rewrite, `screens/scan_destination/*`

The old view had one "Start Scan" button. It's replaced with a page-counter
label, a thumbnail preview of the last captured page, and four actions: Scan
Page / Scan Next Page, Rescan Last Page (disabled until ≥1 page), Done
(disabled until ≥1 page), and Cancel Scan. The controller tracks a
`_scan_completed` flag specifically so `on_leave()` knows *not* to call
`model.cancel()` (which deletes the working files) when the reason for leaving
is a successful `scan_finished` navigation to `scan_destination` — `on_leave()`
firing after every navigation is existing `show_screen()` behavior, so without
this flag a successful scan would delete its own output on the way to the next
screen. The "DEV BYPASS" block that faked scans into `test_pdfs/` is removed
entirely; there is no longer a UI-only mode for this screen.

`screens/scan_destination` presents the actual product decision from the
objectives doc — print vs. send — as two cards. "Print Now" is the simpler of
the two: it builds `pdf_data = {'path': ..., 'filename': 'Scan_<timestamp>.pdf'}`
and `selected_pages = list(range(1, page_count + 1))`, then calls
`main_app.printing_options_screen.set_pdf_data(pdf_data, selected_pages,
"scanner")` — the exact 3-arg controller call `file_browser` already uses for
USB-sourced files — and hands off to the existing `printing_options` → `payment`
→ `printer_manager` pipeline completely unchanged. Confirmed by reading
`print_options/controller.py:135` and `model.py`'s `trigger_analysis()` before
relying on it: the pipeline only ever needs a path/filename and a page list, and
re-derives page count and per-page color analysis from the file itself, so a
scanner-composed PDF requires zero changes downstream. This alone satisfies the
roadmap's stated Phase 6 deliverable of a working scan-to-print flow.

### 3. Scan-to-email and scan-to-Wi-Fi-download, unified — `scan_adapter.py`, `screens/scan_result`, `webapp/routers/redeem.py`

The design question discussed with the user before writing any code: how should
the kiosk collect a destination email address for scan-to-email, given there's
no on-kiosk virtual keyboard anywhere in this codebase — every `QLineEdit` up to
this point has been a numeric OTP field. Building one from scratch for a
rarely-typed field was rejected in favor of the option the user picked: reuse
the OTP/QR session flow already proven for *intake*, but run it in reverse for
*output*. "Send via Wi-Fi" on `scan_destination` composes the PDF, calls the new
`ScanAdapter.handle_scan(pdf_path)` (validates the `%PDF` header, copies into
`SCAN_UPLOAD_DIR` under a fresh UUID name — copy, not move, since the scanner's
own session directory cleans up independently — then
`session_manager.create_session(source="scan", files=[...])`, mirroring
`wifi_adapter.py`'s division of labor exactly), and `screens/scan_result` shows
a QR + OTP pointing at a *new* "redeem" portal URL. The user opens that URL on
their own phone, types the OTP into a normal browser form, and from there can
either download the PDF or type an email address to have it sent — both are new
server-side capabilities in `webapp/`, not new kiosk UI. This one decision
collapses two of the three destinations in the objectives doc into a single
kiosk-side path.

`GET/POST /redeem` (`webapp/routers/redeem.py`) verifies the OTP via a new
`SessionManager.verify_otp_for_source_with_id("scan", otp)` and renders
`redeem_actions.html` with the file list plus hidden `session_id`/`otp` fields.
The new method exists only because the initial `/redeem` POST has an OTP in
hand but not a session_id, and the two follow-up actions need to resubmit both
as hidden form fields — added additively, without touching
`verify_otp_for_source`'s existing signature or callers. `POST /redeem/download`
and `POST /redeem/email` both re-verify via the *existing*
`SessionManager.verify_otp(session_id, otp)`, which already had an
"already-verified" short-circuit (`row['status'] == 'verified'`, checked before
the hash check) built for retry-safety on the intake side — that short-circuit
is exactly what lets the redeem-actions page call `verify_otp` a second and
third time with the same OTP rather than needing a separate token system.
`/redeem/email` builds the `EmailMessage`+PDF-attachment the same way
`email_adapter.py:130-141` already does and sends it via the existing
`SmtpClient`, surfacing a 502 on SMTP failure. `webapp/dependencies.py` gained
`get_session_manager()`/`get_smtp_client()` following the same per-request
provider pattern as `get_wifi_adapter()`, and `webapp_thread.py`'s
`wifi_portal_url()` was factored into a shared `_portal_url(path, host, tls)`
helper so the new `scan_redeem_portal_url()` doesn't duplicate the LAN-IP/TLS
logic.

### Bugs fixed along the way (not new work, but worth recording)

- Boot/navigation smoke-testing surfaced `RuntimeError: ... table sessions has
  no column named files` — the local dev `SSP/database/ssp_database.db`
  (gitignored, never in git history) predated the `files`-column migration for
  multi-file sessions, and `CREATE TABLE IF NOT EXISTS` never migrates an
  existing table. Not a code bug — it would have broken wifi/email session
  creation identically, not just scanning — fixed by deleting the local `.db`
  file so `init_db()` regenerates it. Recorded in memory as a recurring gotcha
  for whoever hits it next on a laptop with an older local DB.
- The first smoke-test script instantiated `PrintingSystemApp()` directly
  without calling `database.models.init_db()` first (which in the real app only
  runs inside `main_app.py`'s `if __name__ == '__main__':` guard) — a
  test-script omission, not a product issue; fixed by calling `init_db()` before
  constructing the app.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/managers/scanner.py` | new (163 lines) | `ScannerInterface`/`SaneAirscanScanner`/`SimScanner` hardware abstraction |
| `SSP/managers/scanner_manager.py` | new (102 lines) | multi-page session orchestration, PDF composition |
| `SSP/managers/scanner_thread.py` | new (31 lines) | generic `QThread` wrapper for any bound `ScannerManager` method |
| `SSP/managers/adapters/scan_adapter.py` | new (48 lines) | validates + persists the scanned PDF, creates a `source="scan"` session |
| `SSP/screens/scanner/model.py` | rewritten (+79/-existing) | real multi-page capture via `ScannerThread`, new signals |
| `SSP/screens/scanner/view.py` | rewritten (+96/-existing) | page counter, thumbnail, Scan/Rescan/Done/Cancel controls |
| `SSP/screens/scanner/controller.py` | rewritten (+91/-existing) | wiring, `_scan_completed` guard on `on_leave()`, dev-bypass removed |
| `SSP/screens/scan_destination/` | new (3 files) | Print Now / Send via Wi-Fi choice screen |
| `SSP/screens/scan_result/` | new (3 files) | QR + OTP display for the redeem portal |
| `SSP/webapp/routers/redeem.py` | new (121 lines) | `GET/POST /redeem`, `/redeem/download`, `/redeem/email` |
| `SSP/webapp/templates/redeem.html` | new (151 lines) | OTP entry form, phone-side |
| `SSP/webapp/templates/redeem_actions.html` | new (172 lines) | download/email actions page |
| `SSP/webapp/dependencies.py` | modified (+22) | `get_session_manager()`, `get_smtp_client()` |
| `SSP/webapp/main.py` | modified (+3/-1) | registers the `redeem` router |
| `SSP/managers/webapp_thread.py` | modified (+17/-3) | shared `_portal_url()` helper, `scan_redeem_portal_url()` |
| `SSP/managers/session_manager.py` | modified (+14) | `verify_otp_for_source_with_id()` (additive) |
| `SSP/main_app.py` | modified (+11/-1) | `scan_destination`/`scan_result` wiring into `SCREEN_MAP` + stacked widget |
| `SSP/config.py` | modified (+50) | `SCANNER_*`/`SIM_SCANNER_*`/`SCAN_UPLOAD_DIR` properties |
| `.env.example` | modified (+12) | documents the new scanner config block |
| `SSP/.gitignore` | modified (+4/-2... via 4 lines) | ignores `scan_uploads/`, `sim_scanner_pages/` |
| `tests/test_scanner_manager.py` | new (166 lines) | `SimScanner`, `ScannerManager`, `SaneAirscanScanner` error mapping |
| `tests/test_scan_adapter.py` | new (78 lines) | mirrors `test_wifi_adapter.py` |
| `tests/test_redeem_route.py` | new (190 lines) | `TestClient`-based route tests, including the download-then-email re-auth path |
| `tests/test_session_manager.py` | modified (+24) | `verify_otp_for_source_with_id` success/failure cases |

## Testing guide

```bash
make test    # 115 passed (81 existing + 34 new)
make lint    # no new violations (new/touched files clean; pre-existing noise
             # in config.py/main_app.py/usb/utils left untouched)
```

Also verified live this session (SIM_MODE, offscreen Qt, scripted navigation
through the real `PrintingSystemApp`, not just unit tests):
- Full boot; navigate `idle` → `scanner`, scan 2 pages via `SimScanner`, rescan
  the last page, `Done` → lands on `scan_destination` with the correct
  `pdf_path`/`page_count`.
- "Print Now" → `printing_options` receives the composed PDF and page list,
  cost analysis renders correctly (`₱6.00` for 2 B&W pages), matching the
  existing pipeline's own logic with no scanner-specific branching.
- Backed out to `scanner`, scanned a second PDF, "Send via Wi-Fi" → session
  creation initially failed on the stale local DB (see Bugs Fixed above); after
  regenerating the DB, session creation and navigation to `scan_result`
  succeeded end to end.

Manual, end-to-end (needs the real thing running, not yet done this session):
1. `make run-sim`; scan → Send via Wi-Fi → note the QR/OTP on `scan_result`;
   from a phone (or `curl`) hit the printed redeem URL, submit the OTP, confirm
   the actions page renders; exercise `/redeem/download` and `/redeem/email`
   with the same session against a local dev SMTP (e.g. the existing greenmail
   setup used for email intake testing).
2. **Final hardware validation (explicitly out of scope this session, per
   `CLAUDE.md`'s workflow rule and the team's limited kiosk access):** run
   `scanimage -L` against the HP Smart Tank 580 to get the real
   `SCANNER_DEVICE` string, set it in `.env`, and validate one full
   scan→print and one full scan→Wi-Fi→phone cycle on actual hardware before
   merging to `main`.

## Future considerations

1. **Physical hardware validation is still outstanding.** `SaneAirscanScanner`
   has only been exercised via monkeypatched `subprocess.run` — the real
   `scanimage -d <device>` invocation against the HP Smart Tank 580 has never
   run. Carried forward explicitly; needs kiosk access per
   `[[user-context]]`'s team constraint.
2. **`CLAUDE.md` is now stale for a second reason.** It already didn't describe
   Phases 2-5 (per `WIFI_EMAIL_END_TO_END_SESSION_SUMMARY.md`'s future
   considerations); it also doesn't mention `scan_destination`/`scan_result` in
   its screen-navigation list or the scanner hardware row in its hardware table.
   Same doc, growing same gap — worth a single pass to bring it current with
   Phases 2-6 together rather than patching it phase by phase.
3. **The QR-scanner-hardware-selection question
   (`QR_SCANNER_HARDWARE_SELECTION_SESSION_SUMMARY.md`) is unrelated to this
   session's scanner but easily confused with it.** That doc concerns a
   USB-CDC serial (`/dev/ttyACM0`) 2D scan engine for reading a QR code *off a
   user's phone* back into the kiosk (the wifi/email intake pickup flow); this
   session's `managers/scanner.py` is the flatbed *document* scanner
   (sane-airscan/HP Smart Tank 580). Neither `project_objectives.txt` nor
   `roadmap-planning.txt` reflects that the two are separate concerns yet.
4. **Self-signed-cert browser warning applies to the redeem portal too**,
   carried from `docs/adr/0001` — the phone hitting `/redeem` over HTTPS will
   see the same warning as `/upload` already does.
5. **`ScanAdapter`'s uploaded copies and `ScannerManager`'s own session
   directory are two independent sets of temp files for the same logical
   scan** (by design — the adapter copies rather than moves, so cancelling the
   kiosk-side session after a successful Wi-Fi send can't delete the file the
   session/redeem flow still needs). Neither has a cleanup scheduler yet;
   `cleanup_expired_sessions()` already lacked one (carried from
   `SESSION_MANAGER_SESSION_SUMMARY.md` item 5), and the scan-upload copies
   inherit the same gap.
