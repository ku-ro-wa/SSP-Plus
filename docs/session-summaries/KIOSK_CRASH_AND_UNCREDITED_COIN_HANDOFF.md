# Handoff — kiosk crashes, uncredited coins, and the field-check session

**Date:** 2026-11-10 (evening, on the kiosk)
**Kiosk:** the newer unit (the one deployed 2026-11-05 → 2026-11-07). Shell user `group-c`,
repo at `/home/group-c/SSP-Plus`, DB `/home/group-c/SSP-Plus/SSP/database/ssp_database.db`.
Journald is **volatile on this image** (`journalctl`: "No journal files were found"), so
nothing before the current boot is recoverable from logs — only `SSP/logs/crash.log` and the
kernel ring buffer are left.
**Branch on the kiosk when this was written:** `feature/ignored-pulse-logging` (e6cf4f1,
pushed). It ran on `feature/crash-diagnostics` (0d6b8e9) earlier the same evening.
**Laptop side:** `~/thesis-data/ssp_database-before-trip.db`, `~/thesis-data/crash.log`
(copy taken 17:43–18:31), `~/thesis-data/shots/`.

Two separate problems plus one already-solved one. Read sections 1–3 before touching the
kiosk; the thesis data collection (section 6) is secondary.

---

## 1. Coins that are accepted but never credited — root cause found, fix pushed

A few coins of the correct denomination were swallowed with **no log line at all**: not
`Coin processed`, not `Coin ignored`. The app's pulse decoding is
`persistent_gpio.py:275` `_get_coin_value()` — 3–4 pulses ₱1, 5–6 ₱5, 8–9 ₱10, 11–12 ₱20 —
and every pulse must be 10–150 ms wide (`COIN_PULSE_MIN_MS`/`MAX_MS`) after pigpio's 5 ms
glitch filter. A pulse failing the width check returned **before counting and before
printing**, so a coin whose pulses all landed outside the window left no trace; one with a
partly-dropped train left only the misleading "N pulses match no coin".

Fixed on `feature/ignored-pulse-logging` (e6cf4f1): width-rejected pulses are counted and
reported once per coin window as
`WARNING: Coin ignored: 2 pulse(s) outside 10-150ms, nothing credited` (same for bills).
Four new tests in `tests/test_persistent_gpio_coin_filter.py`, one in
`tests/test_persistent_gpio_bill_filter.py`, full suite 975 passed, flake8 clean.
`CLAUDE.md`'s coin/bill-filter paragraph updated.

**Not yet verified on the kiosk** — the verification run is what section 2's crash prevented.
The kiosk was left on this branch; the kiosk's deployed code is `0d6b8e9` (see section 4).

---

## 2. The app dies after entering the payment screen — unresolved, this is the real bug

Timeline of the evening: a payment screen worked at ~19:10 (₱3 of ₱5 credited, three ₱1
coins; screenshot proves it), then later runs died on/after `show_screen` into payment.

What a dead run looks like:
- `~/trip-2026-11-10.log` and `~/trip-2026-11-10-patched.log` both **end at**
  `DEBUG: show_screen - new_widget.on_enter() completed` for the payment screen (or at
  `SUCCESS: Payment mode enabled via persistent GPIO`), with **no** `SIGINT received` and no
  `=== Application cleanup completed ===`.
- The `grep` of that log was byte-identical while the app ran and after it closed, so the
  file was not merely buffered behind.
- `pgrep -f main_app.py` printed nothing: no process left.
- Coins inserted afterwards produced no lines at all, while `pigs r 22` read **1** (coin
  acceptor enabled) — and pigpiod keeps that pin level after the client dies, so coins keep
  being swallowed into the cash box with no credit. Old-design coins are refused by the mech
  itself, which is expected and produces no output either.

**`SSP/logs/crash.log` on the kiosk (30,737 bytes, mtime 19:54) has 10 fatal dumps:**

| line | kind | note |
|---|---|---|
| 1, 7 | `Segmentation fault` | Nov 6, from the earlier copy (1,245 bytes), one with the pigpio callback thread live in `pigpio.py:1196 run` |
| 18, 84, 145, 211, 273, 347, 423 | `Aborted` | tonight; threads vary (pigpio callback thread, QR reader blocked in `serialposix.read`) |

`Aborted` = SIGABRT = **Qt `qFatal` → `abort()`**, and the terminal from a later launch shows
exactly that message:

```
qt.qpa.xcb: could not connect to display
qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in "" even though it was found.
This application failed to start because no Qt platform plugin could be initialized.
```

So at least some of the aborts are **headless launches over SSH**: `main_app.main()` sets
`DISPLAY=:0` when the shell has none ("No display in this shell: showing the app on the kiosk
screen"), and when the labwc/Xwayland session is gone Qt aborts. Those dumps pollute the file
and do not prove an app crash.

The last dump (line 423) has the **main thread inside `app.exec_()`**
(`main_app.py:1094`) with no Python frames below it, and every other thread idle — QR reader
blocking on `read`, email poller, two uvicorn threads, ink-analysis and DB workers, and the
pigpio callback thread in `pigpio.py:1196 run`. ~~That shape means the fault is inside Qt's
C++.~~ **Wrong — reproduced on the laptop (2026-11-10, 20:41):** the same shape (`Aborted`,
main thread in `app.exec_()`, no Python frames) comes from a *Python* exception escaping a Qt
slot, which PyQt5 turns into `qFatal` → `abort()`. The trigger: Ctrl+C on
`make run 2>&1 | tee log` sends SIGINT to `tee` too; `tee` exits; the SIGINT handler's
`print("🛑 SIGINT received…")` raises `BrokenPipeError`; abort before `cleanup()`, so the coin
acceptor stays enabled (pin 22 = 1) and the trip log ends mid-run with no `SIGINT received`.
That is exactly the "dead run" signature above. The same happens on any `print` once the
SSH session/tee behind stdout is gone (a closed tab or dropped SSH was SIGHUP, which killed the
app outright, also with no cleanup), while a run whose terminal died but which hadn't printed
yet kept running on the panel with nothing attached — the "phantom" that needed Alt+F4.

**Fixed (this branch):** `utils/run_log.py` sends all output to `SSP/logs/app.log`
(timestamped) and only mirrors it to the terminal while that works; a dead terminal is dropped
with one note. SIGHUP now shuts down cleanly like SIGINT/SIGTERM. Re-run of the exact repro:
no abort, full cleanup logged. The pigpio callback-thread segfaults of Nov 6 are not explained
by this.

**State left behind:** the graphical session is gone. `pgrep -a labwc` / `Xwayland` and
`ls /tmp/.X11-unix/` need checking; `systemctl --user status ssp-kiosk` reports
**"Unit ssp-kiosk.service could not be found"**: this kiosk does not use the `--user`
service from `docs/KIOSK_PI_SETUP.md` §14. Checked afterwards: nothing starts the app at boot
(no `~/.config/labwc/autostart`, no XDG autostart entry, no crontab, no unit besides
`ssp-hotspot-*`), so it is started by hand from a terminal on the desktop (the first idle
screenshot shows `group-c@aio-spark-kiosk:~/SSP-Plus` plus the on-screen keyboard). Nothing
restarts it after a crash (no `Restart=always`), its output went only to that terminal, and
`systemctl --user stop ssp-kiosk` does nothing — which is why two instances coexisted tonight:
the one from the desktop terminal on the panel, and a second `make run` tee'd over SSH. Two copies fight over the acceptor/hopper GPIO, the QR serial port, port 8000 and
the DB (a second copy's startup disables the acceptors under the first one's payment screen),
so every run tonight that overlapped another is suspect evidence.

**Fixed (this branch):** `main()` now takes an flock single-instance lock
(`managers/instance_lock.py`, `$TMPDIR/ssp-kiosk.lock`) before touching anything and refuses
a second copy with `The kiosk app is already running (pid N, started …, launched by make)`.
The kernel drops the lock however the holder dies, so it never goes stale; `cat
/tmp/ssp-kiosk.lock` shows which process (and what launched it) owns the panel.

**Kernel log:** `dmesg`'s newest entries are at uptime 1263–1265 s (~16:55, boot ≈ 16:34) and
show the USB touchscreen (`27c0:0859`, "TouchScreen") **disconnecting and re-enumerating**
twice. Nothing in the kernel log at 19:54, consistent with SIGABRT (not kernel-logged) rather
than SIGSEGV. Not yet established whether the touchscreen flap and the payment-screen deaths
are related — they are ~3 h apart.

### Next steps, in order

1. **Restore the session**: check `pgrep -a labwc; pgrep -a Xwayland; ls -l /tmp/.X11-unix/;
   loginctl list-sessions`, then `sudo reboot`. Confirm the desktop comes back (nothing starts
   the app; it's launched by hand). `pkill -f main_app.py` before any SSH `make run` (a second
   copy is now refused anyway), and read `SSP/logs/app.log` rather than relying on `tee`.
2. **Get exact times and signals** — this settles whether any abort overlaps a payment run:
   `coredumpctl list --since today` and `coredumpctl info --since today | head -60`
   (systemd-coredump, trixie default). Cross-check against `ls -l --time-style=full-iso` of
   the trip logs.
3. **Reproduce deliberately, one process only**: start the app *inside the graphical session*
   or from SSH while `pgrep labwc` shows a live session, in `tmux`, tee'd:
   `PYTHONUNBUFFERED=1 make run 2>&1 | tee ~/crash-repro-$(date +%H%M).log`. Walk
   homepage → scan/USB → payment. Note whether it dies every time, and at which line.
4. **Branch bisect**: the runs that died were on `feature/crash-diagnostics` (0d6b8e9), which
   changed SQLite (WAL + lock timeout) and added faulthandler. `git checkout 0d6b8e9` and
   repeat — if payment is stable there and dies on the newer branch, that is the regression;
   if it dies on both, it is pre-existing and affects the deployed unit.
5. Only then file the issue (draft it with the dump above + the `coredumpctl` rows + which
   branch reproduces). The uncredited-coin issue is separate and already fixed.

**Do not** trust `crash.log` order for timing (no timestamps in it), and do not read silence in
a trip log as "no coin pulses" until `pgrep -f main_app.py`, `ls -l /proc/<pid>/fd/1` and the
panel's own screen agree on which process is serving the kiosk screen.

---

## 3. Hardware facts confirmed tonight (cheap, keep them)

- `pigs r 22` = **0** off the payment screen (idle/homepage/timeout) and **1** on it: the
  app's inhibit handling is correct, so the inhibit path is innocent for the coin problem.
  Same for the bill acceptor, which credited normally throughout.
- `pigs r 22` uses a second pigpiod client and works while the app runs.
- `KIOSK_MODEL=new` on this unit: coin pulses GPIO 17, hopper A sensor 26 / enable 24,
  hopper B sensor 9 / enable 25 (matches the app's startup line).
- A ₱95 Voucher was issued at ~18:25 with `cash_inventory` claiming 36 ₱1 + 36 ₱5 — a real
  `ShortfallCause.HOPPER_FAILURE`: the hoppers owed ~19 ₱5 and stopped early. That is C2
  evidence, not a zeros artefact (the "0 inventory" attempt in Kiosk Admin was overwritten by
  the "Refill All" button, `admin/model.py:216`, which writes ₱1=100, ₱5=50 — see §5).

---

## 4. Branches and repo state

- `main` — untouched by tonight.
- `feature/crash-diagnostics` (0d6b8e9, only on the kiosk and origin) — faulthandler crash
  log + SQLite WAL/lock timeout. This is what the kiosk ran during the field deployment and
  what the runs that died were running. Not merged, not in the laptop clone.
- `feature/ignored-pulse-logging` (e6cf4f1, pushed to origin) — the fix in §1, plus this
  handoff.

---

## 5. Kiosk state that needs cleaning up before customers use it

- `cash_inventory` now says **₱1 100 / ₱5 50** because the multi-tapper "Refill All" button
  was pressed; physically it is ~36/36 minus what the hoppers paid out. Set it to the real
  counts in Kiosk Admin (trip sheet section E), or
  `sqlite3 … "update cash_inventory set count = …"` with the app stopped.
- Paper count 40 while the tray was topped up once during the November testing.
- Tonight's test attempts wrote new `transactions` rows (Nov 10), including a ₱95 Voucher.
  The "before-trip" copy is clean at Nov 7 and is what `aio-spark-thesis/scripts/ch4_tables.py`
  should be run against; that script windows to 2026-11-05…11-07, so Nov 10 rows fall outside
  it regardless.
- **Make journald persistent** (`sudo mkdir -p /var/log/journal`) before the next session;
  the absence of a journal is what made tonight's crashes un-timestampable.

---

## 6. Thesis data collection status (context, not a bug)

`aio-spark-thesis/AIO-SPARK-Thesis/Chapter4/kiosk-trip.md` has sections A (DB copy, commit,
A3 numbers) filled in. `ch4_tables.py` was re-run against the copy and regenerated
`Chapter4/data/*.tex` + `summary.md` (untracked; `chapter4.tex` does not `\input` them yet).
Windowed totals: 54 transactions — 51 completed ₱445, 2 print_failed ₱72 (refunded), 1 `paid`
never finished (#27, Nov 5 16:04, wifi, ₱5); by source Wi-Fi 39 / Email 6 / Scanner 5 / USB 1.
`error_log` in-window: 470 `QR Reader` rows, of which 225 "lost the port" + 225 "recovered"
between 10:54 and 12:24 on Nov 7 — a USB-serial flap worth its own paragraph in Chapter 4.

Captured screens (`~/thesis-data/shots/` on the laptop): `fig-homepage.png`,
`fig-admin-kiosk-admin.png` (also documents the A3 numbers), `fig-voucher-issued.png`
(₱95 `WDEF-QB6F`, expires December 10 2026), `fig-payment-credited.png` (₱3 of ₱5,
Digital Copy). `redo-idle-desktop-not-a-screen.png` is the desktop, not a kiosk screen. Still
missing: C1 acceptor accuracy (blocked by §2). C2 hopper payout, C3 price-display times and
D1–D6 were already tested in earlier sessions; B's photos and labels were done on 2026-11-10
(trip sheet in the thesis repo).
