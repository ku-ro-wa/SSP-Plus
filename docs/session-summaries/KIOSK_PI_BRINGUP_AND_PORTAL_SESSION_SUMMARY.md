# Session Summary — Kiosk Pi Bring-up and Portal Access

**Date:** 2026-10-09 → 2026-10-15 (PRs #50, #51, #52, #65, #67, #69 merged; #63, #66 open)
**Scope:** Running the app on the real kiosk Pi for the first time surfaced a
string of problems that SIM_MODE on a laptop never showed: portal pages hanging,
Ctrl+C not quitting, the UI at two-thirds size, `make run` failing over SSH, and
pigpio missing without anyone noticing. This covers those fixes, the proposed
captive-portal approach (ADR 0008), and the setup guide written when the kiosk's
SD card died on 2026-10-14. Follows on from the hotspot work in #47/#49 (issue #29).
Written from the commits and PR descriptions for the week.

```
 phone joins kiosk Hotspot
   |  OS "am I online?" probe (http://captive.apple.com, connectivitycheck..., msftconnecttest)
   v
 dnsmasq  address=/#/<pi>          every name -> the Pi (dns.msftncsi.com keeps its real address)
   v
 nft prerouting  :80 -> :8080      HTTPS :443 reset at once
   v
 webapp/captive.py probe responder  (only when WIFI_HOTSPOT_ENABLED)
   |  device not yet released  -> 302 /upload   => OS opens sign-in window on the upload page
   |  device released (1 h)    -> exact "online" reply per OS
   v
 Portal :8000 /upload  -- any request here releases the device (middleware in webapp/main.py)
   |  page loads with inline SVG icons, nothing fetched from the internet
   |  anything else the phone tries to reach outside: TCP reset / ICMP prohibited (#50)
```
*(Captive-probe part is PR #63, still open pending on-device tests.)*

## What this session built

### 1. Portal pages that don't wait for the internet — `SSP/webapp/templates/`, `scripts/setup_hotspot.py` (#50)

On the first iPhone test on the Pi, the upload page took over 10 s to appear and its
icons never loaded. Every portal page pulled Font Awesome from cdnjs in `<head>`, and
the browser holds rendering until that stylesheet loads. The hotspot has no internet
and the firewall's forward chain silently *dropped* the request, so the page waited for
a timeout (16,852 dropped packets during the test).

Two fixes, each sufficient on its own for the icons but both kept: the ten icons in use
are now inline SVG partials (Font Awesome Free 6.5.0, CC BY 4.0, credit kept in each
file), and the forward chain now *rejects* (TCP reset / ICMP admin-prohibited) instead
of dropping, so anything else a phone tries to fetch fails immediately. The input chain
is unchanged, so SSH and the dashboard stay silently dropped on `wlan0`. A test fails if
any portal template references an outside URL, and the container check asserts the
refusal arrives in under a second; it fails against the old drop rule.

### 2. Clean shutdown on Ctrl+C and SIGTERM — `SSP/main_app.py` (#51)

Found while testing #50: Ctrl+C didn't stop `make run-sim`, so the old instance and its
portal on port 8000 kept running. Qt's event loop runs in C++ and Python only handles
signals while running Python code. SIGINT/SIGTERM now close the window, which runs
`cleanup()`; a 200 ms no-op `QTimer` gives Python a chance to run the handler, and a
second signal calls `os._exit(1)` in case cleanup hangs. This matters more than it
looks: it's also how `systemctl stop` will end the app once autostart is set up.

### 3. Pi install fixes — `requirements.txt`, `docs/SETUP.md` (#52)

`opencv-python` bundles Qt plugins that break PyQt5 on Linux, so the app aborted on the
Pi. The app only uses cv2 for ink analysis, so `opencv-python-headless` replaces it.
`SETUP.md` gains the first "Verified on the kiosk Pi" record and kernel/interface names.

### 4. UI scaled to the screen height — `SSP/ui/scaling.py` (#65)

Every screen is laid out in fixed pixels for a window about 720–800 px tall, so on the
1920×1080 panel the UI came out at about two-thirds size. Rather than re-lay out 16
screens, `main()` sets Qt's `QT_SCALE_FACTOR` before creating the `QApplication`, from a
new `UI_SCALE` setting: blank/`auto` = screen height ÷ 800 (never below 1; 1.35 on a
1080 panel), a number forces it, and an existing `QT_SCALE_FACTOR` wins. 800 is the
tallest screen's need at 1× (scan_destination ~790), so auto can't overflow; all 16
screens were rendered offscreen at 1920×1080 × 1.35 and fit. Verified on the kiosk,
including touch targets lining up and the screen probe working under Wayland.

### 5. `make run` over SSH — `Makefile` (#67)

With no `DISPLAY`, `make run` now uses the kiosk's X session (`DISPLAY=:0`) if
`/tmp/.X11-unix/X0` exists, and otherwise runs headless (`QT_QPA_PLATFORM=offscreen`).
This is what made the week's hardware testing from a laptop over SSH practical.

### 6. Refuse to start without pigpio — `SSP/managers/gpio_check.py` (#66, open)

The payment screen decided whether to show its *simulated* coin/bill buttons from
whether `import pigpio` worked, not from `SIM_MODE`. On the Pi, pigpio wasn't importable
from the venv and `pigpiod` wasn't running, so with `SIM_MODE=false` the acceptors did
nothing and customers would have been offered buttons that add free credit. With
`SIM_MODE` off, `main()` now checks that pigpio imports and `pigpiod` answers, logs a
`GPIO` error naming the fix, and exits before opening the window. The sim buttons only
appear when `SIM_MODE=true`. `SETUP.md` documents building pigpio on trixie, a `pigpiod`
unit bound to localhost (`-l`; by default it listens on the whole network on port 8888),
and the Python 3.13 venv/egg problem. **Not merged yet**; its on-Pi checks are unticked.

### 7. Captive-portal detection without a splash page — `SSP/webapp/captive.py`, ADR 0008 (#63, open)

No domain is being bought (a cost to the operator), and laptops can't scan the kiosk's
QR image, so something has to bring devices to the Portal by itself. The supervisor
suggested openNDS with a "Continue" splash page. ADR 0008 keeps the useful part —
the OS's own sign-in window — without openNDS and without the extra tap: the Hotspot
answers the OSes' "am I online?" checks itself (see diagram). Until a device makes any
Portal request, its probes are redirected to `/upload`, so the sign-in window opens on
the upload page; after that it's released for an hour (the DHCP lease) and gets each
OS's exact "online" reply, so it stops treating the Wi-Fi as captive. Verified off the
Pi (container test with real nft + dnsmasq; live run with real Uvicorn servers). Open
question recorded in the ADR: HTTPS on the Hotspot, since without a domain the
certificate is self-signed and the iOS/macOS sign-in window may refuse it.

### 8. Kiosk Pi setup guide — `docs/KIOSK_PI_SETUP.md` (#69)

The kiosk's SD card died on 2026-10-14. The rebuild was written up as a 17-step guide
from a blank card (flashing, packages, `.env`, hotspot, first run, coin inventory,
systemd autostart, Tailscale, backup/restore of the card image), with a status table
marking what has actually been done on the new card. `SETUP.md`'s QR reader section
gains the five settings `KIOSK_CONFIG` sends that the barcode list lacked, and what the
app can and can't re-send on each port open. `SETUP.html` was re-rendered, as it had
fallen behind.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/webapp/templates/icons/*.svg` (10) | added | inline icons, no CDN |
| `SSP/webapp/templates/{index,redeem,redeem_actions,success}.html` | modified (+11/-17) | use inline icons |
| `scripts/setup_hotspot.py` | modified (+5/-1) | forward chain rejects instead of drops |
| `SSP/main_app.py` | modified (+23) | signal handling, UI scale at startup |
| `SSP/ui/scaling.py` | added (+57) | `UI_SCALE` resolution |
| `SSP/config.py`, `.env.example`, `CLAUDE.md` | modified | `UI_SCALE` |
| `requirements.txt` | modified (+3/-2) | headless OpenCV |
| `Makefile` | modified (+12) | `make run` over SSH |
| `docs/KIOSK_PI_SETUP.md` | added (+344) | rebuild guide |
| `docs/SETUP.md`, `docs/SETUP.html` | modified | Pi verification, QR settings, re-render |
| `tests/test_ui_scaling.py`, `test_webapp.py`, `test_setup_hotspot.py`, `hotspot_container/check.sh` | added/modified | see Testing guide |
| *Open:* `SSP/webapp/captive.py`, ADR 0008, `webapp_thread.py`, `setup_hotspot.py`, `tests/test_captive.py` | #63 | captive-probe responder |
| *Open:* `SSP/managers/gpio_check.py`, `payment/view.py`, `tests/test_gpio_required.py`, `SETUP.md` | #66 | pigpio startup check |

## Testing guide

```bash
make test           # 573 passed on main (2026-10-15); #63 reports 552 and #66 541 on their branches
make lint           # clean
make test-hotspot   # Docker; 22/22 at #50, all pass on #63
```

Also verified on the kiosk Pi:
- #50, #51, #52: merged after kiosk verification (PR checklists).
- #65: startup logs `UI scale 1.35`; Wayland probe works; nothing clipped on scan
  destination, scanner, Kiosk Admin, payment with keypad; taps land where drawn.
- #69: steps 1–7 and 9–12 of the guide done on the new card.

Manual, end-to-end (still to do):
1. #63's device matrix: iPhone, Android (data on/off), Windows and Mac laptops — sign-in
   window opens on `/upload`, a PDF uploads, the device stays on kiosk Wi-Fi.
2. #66's checks: `pigpiod` survives reboot; app exits with the GPIO error when it's
   stopped; `ss -ltnp | grep 8888` shows localhost only.
3. #67 over SSH with and without the kiosk screen (no boxes ticked on the PR).

## Future considerations

1. **Finish the new card** — printer (step 8), QR reader (13), systemd autostart (14) and
   Tailscale (15) are not done. Tailscale also blocks remote access (#41, #45, #46),
   next on the roadmap after the admin dashboard.
2. **Merge #66 (pigpio required)** — until it lands, a kiosk with `SIM_MODE=false` and no
   pigpio still shows free-credit sim buttons on main. Highest-risk open item.
3. **Decide HTTPS on the Hotspot (ADR 0008 open question)** and run #63's device matrix
   before merging. Carries over the self-signed-certificate concern from
   `WIFI_EMAIL_END_TO_END_SESSION_SUMMARY.md` item 2.
4. **Back up the new card's image** once it's complete, per the guide's last step, so
   another card failure is a restore rather than a rebuild.
5. **`SETUP.html` re-render is on a local-only commit** (`cec012e` on
   `feature/coin-acceptor-pin-filter`, not pushed), which also recorded
   `.claude/worktrees/*` entries that shouldn't be committed. Redo it on a clean branch.
