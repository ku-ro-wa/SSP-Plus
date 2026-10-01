# Session Summary — QR Reader Kiosk Integration (Session Payloads) + Lint Cleanup

**Date:** 2026-09-30 (commits `a865fd1` … `1cfe334`, branch `feature/admin-dashboard-auth`)
**Scope:** Builds the kiosk side of the QR reader chosen in
`QR_SCANNER_HARDWARE_SELECTION_SESSION_SUMMARY.md`: issues #31–#36, all children of
parent #30 ("QR reader: read Session payloads at the kiosk"). Closes Future
considerations #2 (serial reader manager) and #3 (the pickup path) of that summary.
A sidenote covers the `make lint` cleanup commit (`e73d9bb`) made between #35 and #36.

```
 Customer phone                     Kiosk
 ┌──────────────────┐   CR-terminated line
 │ QR "sid16:otp6"  │ ───────────────────▶ QrReaderManager (QThread, pyserial)
 │ (portal / email) │                        │ classify_payload()  → session | voucher | malformed
 └──────────────────┘                        ▼
   brightness reminder                decide_redemption(read, screen, SessionManager)
   + wake lock (#33)                         │  exact-pair verify_otp, source check first
                                             ▼
                          go-to-wifi / go-to-email / show-message / ignore
                                             │
                      main_app._on_qr_read → open_session_files()  (same path as a typed OTP)
```

## What this session built

The QR image printed on every upload success page and reply email used to be
decorative: the kiosk had no way to read it. This session makes the reader a first-class
input that lands a customer in exactly the place a correct typed code would, and makes
sure a hostile or broken reader can never stop sales. The design decisions are recorded
in ADR 0004 and the **QR reader** entry in `CONTEXT.md`.

### 1. Source rename: `scan` → `scanner` (#31) — `scan_adapter.py`, `routers/redeem.py`

Flatbed-flow Sessions were stored with Source `scan` while transactions and the Admin
Dashboard already said `scanner`. Because the reader only accepts `wifi`/`email`
Sessions, the Source check became load-bearing, and two names for one thing would have
been a latent bug. Renamed in the adapter, the redeem route's lookup and the tests. No
data migration: Sessions expire in minutes. Done first so later tickets build on one name.

### 2. Tracer bullet: read a Session QR on idle/homepage (#32) — `SSP/managers/qr_reader.py`

A background thread in the style of the other persistent managers: opens the configured
serial port, frames on CR (stray LF stripped), and emits one signal per read. The pure
pieces are separated so they're testable without hardware or Qt:

- **`classify_payload`** — every line is exactly one of *Session* (`16 lowercase hex:6 digits`),
  *Voucher* (`V1:` prefix) or *Malformed*. Anything a reconfigured reader might emit is
  malformed, by construction.
- **`decide_redemption`** — takes a classified read, the screen name and the Session
  Manager and returns an outcome. The returned flow follows the **Session's own Source**,
  not the current screen, so someone who emailed but is on the Wi-Fi screen isn't stuck.
- **Checked as an exact pair.** A read goes through `verify_otp(session_id, otp)`, so a wrong
  OTP counts toward the same lockout as typing — the reader is not a faster way to guess.
  Malformed reads never count. The Source is checked *before* verifying, which needed a small
  read-only `SessionManager.get_session_source`.

`main_app._on_qr_read` acts on the outcome via a new shared `open_session_files()`,
extracted from what the Wi-Fi/Email controllers did after a correct OTP and now used by
all three. A blank `QR_READER_PORT` turns the reader off; in `SIM_MODE`, Ctrl+Shift+Q
opens a box that injects a payload through the identical path.

*Rejected:* keyboard (HID) mode, the usual POS choice. It loses reads on screens without an
input field, can mangle `:` under a non-US layout, and can't be told apart from a person
typing. *Also rejected:* wiring the reader to the Pi's UART — no advantage over USB serial,
and RS232/5 V TTL levels would damage the 3.3 V GPIO.

### 3. Brightness reminder and wake lock (#33) — `webapp/templates/success.html`, `email_adapter.py`

Bench testing showed the reader fails at minimum phone brightness. The success page and
the reply email now say to turn brightness up, and the page requests a screen wake lock
while visible (re-requesting when it becomes visible again; unsupported browsers skip it).
Brightness can't be forced from a web page or email, and a timed "can't scan?" pop-up was
rejected because the reader sends nothing on a failed read, so the kiosk can't know
someone is trying.

### 4. Kiosk setup docs (#34) — `docs/SETUP.md`

udev rule matching the reader's vendor/product ID that marks it ignored as an input
device and provides a stable `/dev/serial/by-id/...` path; the `.env` value; and the
configuration sequence using the manual's own labels (Restore Defaults, USB COM,
Auto-Sensing, 2D-ON, 1D-OFF, End Mark CR, Duplicate Detection-ON at 3000 ms, etc.). A
follow-up commit states that the duplicate-detection time unit is **ms**. The reason for
the udev rule: the module has no way to stop reading settings barcodes (1D-OFF was tested
and doesn't block them), so anyone can flip it to keyboard mode; the OS must ignore it.

### 5. Code screens, messages and kiosk text (#35) — `qr_reader.py`, idle/homepage/wifi/email screens

The Wi-Fi and Email code screens accept reads too. Malformed, Voucher, wrong-Source, expired,
used and locked-out reads show a message via each screen's `show_qr_message()` and never
count a failed attempt; all other screens ignore reads silently so a stray read can't
interrupt a job in progress. A **used** Session is rejected like a typed code rather than
reopening files. Voucher reads say "Vouchers can only be used at payment" until the voucher
tickets land. A `DuplicateReadFilter` drops an identical read within 3 s, layered on the
reader's own duplicate detection. Idle, homepage and both code screens show "Hold your QR
code up to the reader, or type your code."

### 6. Handling a lost reader (#36) — `qr_reader.py`, `main_app.py`, `screens/admin/`

`QrReaderManager` takes a port factory, tracks connected/unavailable, retries every 5 s and
reports each availability *change* once (so a dead port doesn't spam `error_log`). `main_app`
writes one `error_log` row (`QR Reader`) per loss and per recovery, and Kiosk Admin shows the
status (blank port = "Not configured"). The kiosk keeps working with typed codes throughout.
No operator SMS — deliberately deferred until the legacy GSM channel is replaced.

### Sidenote: lint cleanup (`e73d9bb`) — `.flake8`, ~60 files

`make lint` went from **1,359 findings to 2**. Mostly autopep8 whitespace/blank-line fixes,
unused imports/variables, pointless f-string prefixes, and bare `except:` narrowed to
`except Exception:`. One real fix: `screens/payment/model.py`'s `setup_gpio` referenced an
undefined `pigpio`; it now has a guarded import. `.flake8` sets `max-line-length = 160`
(long lines are print/SQL strings; the longest was 150) and exempts `main_app.py` from E402
(it edits `sys.path` before importing). Makefile and CLAUDE.md updated to match.

*Deliberately not fixed:* the two remaining F811s — `complete_payment` and
`_on_dispensing_finished` are each defined twice in `screens/payment/model.py`, and the
shadowed copies **differ in behavior** (transaction_data, paper check, cash inventory).
Deleting either is a payment-behavior decision, not a lint fix, so it needs an owner's call.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/managers/qr_reader.py` | new (+242) | reader thread, classification, redemption decision, duplicate filter, status/retry |
| `SSP/main_app.py` | modified | reader wiring, `open_session_files()`, `error_log` on loss/recovery, SIM injection |
| `SSP/managers/session_manager.py` | modified (+11) | `get_session_source`, used-session handling |
| `SSP/screens/{idle,homepage,wifi,email}/` | modified | hint text, `show_qr_message()` |
| `SSP/screens/admin/` | modified | reader status row in Kiosk Admin |
| `SSP/webapp/templates/success.html`, `email_adapter.py` | modified | brightness line, wake lock |
| `SSP/managers/adapters/scan_adapter.py`, `webapp/routers/redeem.py` | modified | `scan` → `scanner` |
| `SSP/config.py`, `.env.example` | modified | `QR_READER_PORT` |
| `tests/test_qr_reader.py`, `tests/test_qr_redemption.py` | new (+258/+199) | reader seam (`loop://`) and redemption seam tests |
| `tests/test_upload_route.py` + rename tests | modified | brightness/wake-lock, `scanner` |
| `docs/SETUP.md`, `docs/adr/0004-…md`, `CONTEXT.md`, `CLAUDE.md` | modified/new | setup, ADR, glossary |
| `.flake8`, `Makefile` + ~60 source files | modified | lint cleanup (sidenote) |

Whole-range diff: 76 files, +2,636/−1,538 — inflated by whitespace lint fixes and by
`.env.example`/`CLAUDE.md` showing whole-file diffs because `.gitattributes` normalizes
their old CRLF blobs to LF.

## Testing guide

```bash
make test    # 275 passed
make lint    # 2 findings: F811 complete_payment / _on_dispensing_finished (payment/model.py)
```

Both run at the end of this session. Reader tests use pyserial's in-memory `loop://` port,
so no hardware, `pigpio`, CUPS or Qt event loop is needed.

Not verified this session: anything on real hardware. Bench results (phone reads,
CR line ending, settings surviving replug) were recorded in #30 from earlier work on a Mac.

Manual, end-to-end (tracked as #38):
1. Install the udev rule on the kiosk Pi; confirm a stable `/dev/serial/by-id/...` path across reboot.
2. Switch the reader to HID-KBW; confirm it types nothing into the kiosk; switch back to USB COM.
3. Read a real Wi-Fi and a real email Session QR from a phone; confirm the right flow opens.
4. Unplug/replug; confirm Kiosk Admin status changes and reads resume without restart.

## Future considerations

1. **Verify the reader on the kiosk Pi (#38, `ready-for-human`)** — needs the demo Pi and reader;
   blocked on the Pi being set up. Related to #29 (RaspAP), not blocked by it.
2. **Read Voucher payloads at payment and balance check (#37)** — replaces the "payment only"
   message; blocked by #26 (Apply Vouchers) and #27 (balance check), both under the voucher
   epic #21. Carries over the voucher spec in memory/`CONTEXT.md`.
3. **Parent #30 stays open** until #37 and #38 land.
4. **Resolve the duplicate `complete_payment` / `_on_dispensing_finished`** in
   `screens/payment/model.py` — clears the last 2 lint findings so `make lint` can gate CI.
5. **Operator alerting for reader loss** — currently `error_log` + Kiosk Admin only; carries over
   the "replace the GSM SMS channel" item.
6. **`QR_SCANNER_HARDWARE_SELECTION` leftovers** — objectives/roadmap docs still name the HID
   LogicOwl scanner (its Future consideration #1), and the final-fleet engine choice is open.
