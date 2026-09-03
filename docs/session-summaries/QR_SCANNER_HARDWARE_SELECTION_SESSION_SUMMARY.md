# Session Summary — QR Scanner Hardware Selection (OTP Pickup Path)

**Date:** 2026-09-03 (no commit — this session produced no code changes)
**Scope:** A hardware-selection decision for the kiosk-side QR scanner that reads
a customer's pickup code off their phone at collection time, plus a compatibility
check of the chosen approach against the existing `SSP/managers/session_manager.py`
payload format. Refines the scanner assumption baked into
`docs/project_objectives.txt` #7 ("QR scanning via LogicOwl OJ-HS-23 USB HID
scanner"), `docs/roadmap-planning.txt` line 197 ("read USB HID events and
validate OTP"), and closes analysis owed against
`SESSION_MANAGER_SESSION_SUMMARY.md` Future consideration #4 (the kiosk pickup
screen + scanner). No `*_SESSION_SUMMARY.md` or objectives-doc text has been
edited yet — that's follow-up work (see Future considerations).

> **Not** the flatbed document scanner. `docs/project_objectives.txt` #8 /
> roadmap Phase 6's "Scanner Module" is the sane-airscan path against the HP
> Smart Tank 580 (`SSP/screens/scanner/`). This session is only about the small
> 2D imager that reads the OTP/QR the customer presents on their phone to pick
> up an already-uploaded job — a Phase 7 (Session Manager) concern.

```
 Customer phone screen                  Kiosk
 ┌───────────────────┐
 │  QR: "sid:otp"    │  present at      ┌──────────────────────────────┐
 │  (session_manager │  fixed mount     │ 2D scan engine (own aimer +  │
 │   _generate_qr_   │ ───────────────▶ │ active illumination)         │
 │   bytes)          │                  │        │ USB-CDC serial       │
 └───────────────────┘                  │        ▼ /dev/ttyACM0         │
                                        │ new managers/ serial reader  │
                                        │  .decode().strip()           │
                                        │        ▼                     │
                                        │ SessionManager               │
                                        │  .verify_qr_payload("sid:otp")│
                                        └──────────────────────────────┘
```

## What this session decided

The kiosk's compute is a Raspberry Pi 4 (fixed in the BOM for other reasons), the
unit is unattended, the scanner is fixed-mount, and the code being scanned is
always on an **emissive phone screen**, not paper. One prototype exists now; the
final fleet must tolerate varying ambient light without per-site retuning. Those
constraints, not price alone, drove the choice.

### 1. Constraints that ruled options in or out

- **Emissive display, not print.** A backlit screen with glare, auto-dimming, and
  the occasional cracked panel is the hard case. This removes 1D laser scanners
  entirely (no 2D, can't read screens) and disfavors cheap CCD imagers with
  glossy front glass, which bounce their own glare back into the sensor.
- **Unattended.** No human to re-aim, wake, or retry. The read has to succeed
  first time, every time, with the phone held roughly — not precisely — in place.
- **Adaptable to lighting** was treated as the deciding criterion, and it cuts
  against intuition (see §2): a bare camera makes ambient light *the
  integrator's* problem forever; a scan engine with its own illumination makes it
  the engine's problem, solved once at the factory.
- **Pi already present.** The marginal cost of adding a scan module that talks to
  the Pi is just the module — there's no separate compute to justify.
- **Fixed-mount + unattended** is precisely the duty cycle embedded scan engines
  in kiosks and self-checkout lanes are built for (presentation/auto-sense mode,
  continuous trigger).

### 2. Options weighed, and why the others lost

| Option | Verdict | Reasoning |
|---|---|---|
| 1D laser scanner | Rejected outright | Cannot decode 2D symbologies; cannot read emissive displays. Non-starter. |
| **Raspberry Pi camera + `zbar`/OpenCV** | **Rejected as primary; kept as documented plan B** | Technically fine to decode `sid:otp` off a screen (Pi Camera Module 3 autofocus + `pyzbar`, or OpenCV `QRCodeDetector`). But it puts an exposure/gain/focus CV pipeline **and** an OS image on the maintenance ledger, and — critically — every change of deployment environment (brighter room, window glare, dimmer corner) becomes a re-tuning task. That directly contradicts the "adaptable to lighting" goal. Only worth it if the camera earns its keep elsewhere (OCR, image capture), which it doesn't here. |
| Consumer 2D imager, HID keyboard-wedge (Zebra DS2208 / Honeywell Voyager 1450g class; the objectives doc's LogicOwl OJ-HS-23 is in this bucket) | Viable but not chosen | Reads screens well and needs zero decode software. But it's a bulky external gun to mount and shroud on a fixed kiosk face, and HID keyboard-wedge input is awkward for an unattended app: it depends on window focus and, in practice, an X server / input layer to receive keystrokes. Fine as a fallback; not the clean path. |
| **Embedded 2D decoded scan engine → Pi over USB-CDC serial** | **Chosen** | Same decode silicon as the consumer guns, in a module built to sit behind a kiosk window. Brings its own aimer and active illumination LED — this is what actually delivers "works the same in a dim room or under a bright window." Talks to the Pi as a virtual serial device: newline-delimited payloads read straight from `/dev/ttyACM0`, no keyboard focus, no X dependency. |

### 3. Recommended parts — two tiers, one interface

Both tiers expose the same USB-CDC serial interface, so the prototype can run the
cheap part and the fleet can swap up with near-zero integration rework.

- **Prototype / budget:** DYScan DE2120, Waveshare Barcode Scanner Module, or a
  GM65-class module — roughly $25–45. Enough to validate mounting geometry,
  the serial reader, and the end-to-end pickup flow.
- **Final unit:** a decoded engine built on a Zebra SE4710 or Honeywell N3680 —
  roughly $50–70. Meaningfully better on dim / glary / marginal screen reads,
  which is what matters when there's no attendant to trigger a retry.

### 4. Integration decisions

- **USB-CDC virtual serial, not HID keyboard emulation.** This is a deliberate
  departure from `docs/project_objectives.txt` #7 and `roadmap-planning.txt`
  line 197, both of which assume "USB HID" / "read USB HID events". For an
  unattended Qt app, reading lines from `/dev/ttyACM0` on a dedicated thread is
  simpler and more robust than depending on keystroke delivery and focus.
- **New `managers/` module for the serial reader**, following the existing
  `SSP/managers/sms_manager.py` pattern: `try: import serial` with a
  `SERIAL_AVAILABLE` flag, a `QObject` with a `pyqtSignal` carrying the decoded
  payload, and a hard `SIM_MODE` short-circuit that skips the real port — mirrors
  how `sms_manager` and the GPIO code already degrade. In `SIM_MODE` the screen
  should accept typed input as the mock, same as the roadmap already intends.
- **Engine configuration** (set once by scanning the manual's setup barcodes):
  prefix **off**, suffix **LF only**, presentation / auto-sense mode, continuous
  trigger, illumination always on, same-symbol re-read delay ~1 s, beep on
  decode.
- **Optics / mounting:** fix the phone standoff inside the engine's decode range
  (~5–25 cm for this class); give the customer a moulded rest or a printed target
  outline so the phone lands in the sweet spot; angle the scan window ~10–15° off
  the phone's plane so the illuminator's specular reflection doesn't return
  straight into the sensor (the usual cause of screen no-reads); add a short
  hood/shroud around the window. The shroud plus active illumination is most of
  the "adaptable to different lighting" answer.

### 5. Compatibility check against `SSP/managers/session_manager.py`

The chosen approach is compatible. The payload is close to the friendliest thing
you can hand a 2D imager, with exactly one integration gotcha.

**What lines up cleanly:**

- The QR payload (`session_manager.py:95`) is `f"{session_id}:{otp}"` — 16
  lowercase hex chars + `:` + 6 digits = 23 ASCII bytes, byte mode.
  `qrcode.make()`'s defaults put that at QR **version 1** (21×21 modules), ECC
  level **M**: a large, low-density symbol, which is the best case for reading off
  a backlit screen even with a budget engine.
- `:` (0x3A) is keyboard-layout-safe, so even the HID-wedge fallback wouldn't
  mangle it.
- The payload contains no control characters, so a line-delimited read yields
  exactly one scan per line.
- **Repeat scans are already idempotent.** `verify_otp` (`session_manager.py:146`)
  returns `(True, "Session already verified", files)` on re-scan of a verified
  session, so the ~1 s same-symbol re-read delay is UX polish, not a correctness
  requirement.

**The one gotcha:** `verify_qr_payload` (`session_manager.py:104`) does
`payload.split(":", 1)` with **no trimming**. Scan engines append a configurable
terminator and can prepend a prefix. If either leaks through:

- a trailing `\r` → `otp = "123456\r"` → `_hash_otp` mismatch → "Incorrect OTP"
  **and it burns a failed attempt**; five such scans hit `MAX_FAILED_ATTEMPTS`
  and lock the session.
- a stray prefix → wrong `session_id` → "Session not found".

**Resolution:**

1. Configure the engine: prefix off, suffix = LF only (already in §4).
2. In the reader glue, `line.decode("ascii").strip()` before calling
   `verify_qr_payload()`.
3. Optionally harden `verify_qr_payload` itself to
   `payload.strip().split(":", 1)` as defense in depth — cheap, and it also
   protects the manual-entry path.

## Files touched

None. This session is a decision record; no code, config, or objectives-doc text
was changed. The follow-ups that *would* touch files are in Future considerations.

## Validating the recommendation

No automated tests apply (nothing was built). `make test` / `make lint` remain at
their last-commit state.

With the prototype unit, before committing to the fleet part:

1. Wire the budget engine (DE2120 / GM65-class) to the Pi over USB, confirm it
   enumerates as `/dev/ttyACM0` (or `ttyACM1`), and `cat` the port while scanning
   a `session_manager`-generated QR off a phone — verify the line is exactly
   `sid:otp` with no visible prefix and a single known terminator.
2. Reproduce the `\r` failure deliberately (leave the suffix at CRLF) and confirm
   it manifests as "Incorrect OTP" + a failed-attempt increment, so the fix is
   validated against real behavior, not assumed.
3. Test read reliability across: screen at min brightness, screen at max
   brightness, a raking overhead light, and a bright window behind the customer.
   This is the data that decides whether the budget engine is enough or the
   SE4710/N3680-class part is warranted.
4. Confirm decode latency and the same-symbol re-read delay feel right when a
   customer holds the phone in the mount for a few seconds (no double-fire, no
   missed first read).

## Future considerations

1. **Reconcile the objectives / roadmap docs.** `docs/project_objectives.txt` #7
   and line 34's BOM, plus `docs/roadmap-planning.txt` line 197, still name the
   "LogicOwl OJ-HS-23 USB HID scanner". If the embedded-engine + CDC-serial
   direction is accepted, those lines need updating so a future dev doesn't build
   the HID keystroke reader the roadmap currently describes.
2. **Build the serial reader manager.** New `SSP/managers/` module on the
   `sms_manager.py` template (see §4). Emits decoded payloads on a `pyqtSignal`;
   `SIM_MODE` accepts typed input instead.
3. **Build the kiosk pickup screen.** Still the open item from
   `SESSION_MANAGER_SESSION_SUMMARY.md` Future consideration #4: a screen that
   takes either a scan (via the manager above) or a manually keyed 6-digit OTP
   (mirroring `screens/dialogs/pin_dialog/`) and calls
   `session_manager.verify_qr_payload()` / `verify_otp_for_source()` to release
   the files to the print/email/download route.
4. **Harden `verify_qr_payload`** with `.strip()` regardless of which scanner
   ships — it's a one-line robustness fix that also covers manual entry.
5. **Finalize the mount.** The 10–15° window angle, standoff distance, phone
   rest, and shroud are design parameters to fix on the prototype enclosure
   before replicating.
6. **`cleanup_expired_sessions()` still has no scheduler** — unrelated to this
   session, but carried forward from `SESSION_MANAGER_SESSION_SUMMARY.md` Future
   consideration #5 and relevant once the pickup flow is live and generating
   real session churn.
