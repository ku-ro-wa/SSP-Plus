# Session Summary — Payment Hardware Working on the Kiosk

**Date:** 2026-10-13 → 2026-10-15 (PRs #68, #70 merged; main at `81a0225`; #64 open)
**Scope:** First runs of real coins and real change on the kiosk Pi. Coins were
accepted but never credited, then credited but the hoppers overpaid change by
several times. This covers finding the right GPIO pins, filtering noise on the
coin and hopper-sensor lines, and making payouts fail safe. Builds on the Voucher
Shortfall path (`VOUCHER_SYSTEM_COMPLETION_SESSION_SUMMARY.md`), which is now
what a stopped hopper falls back to. Written from the commits and PR descriptions.

```
 COIN IN                                         CHANGE OUT
 acceptor COIN wire  GPIO 12 (.env COIN_PIN)     hopper A ₱1: sensor GPIO 9,  motor enable 24
   |  pigpio glitch filter 5 ms                  hopper B ₱5: sensor GPIO 26, motor enable 25
   |  count low pulses 10-150 ms wide              |  enable pin written OFF before it becomes an output
   v                                               |  motor on, wait <= 1.5 s for ONE low pulse 20-300 ms
 pulse count -> coin                               |    (5 ms glitch filter; edge ticks, not current tick)
   ₱1 3-4 · ₱5 5-6 · ₱10 8-9 · ₱20 11-12           |  seen  -> next coin
   other -> "Coin ignored: N pulses" (logged)      |  unseen -> stop this hopper, rest becomes a Voucher
   v                                               v
 PaymentModel  (signals connected ONCE)          payment screen locked: Back ignored, buttons grey,
   credited coin/bill restarts the 60 s timeout    timeout deferred until change is out
                                                 app exit / startup: stop_all_hopper_motors()
```

## What this session built

### 1. Coin acceptor on the right pin, with noise filtering — `SSP/managers/persistent_gpio.py` (#68)

`PersistentGPIO` listened on a hardcoded GPIO 17, but this kiosk's acceptor COIN wire is
on GPIO 12. `.env` already had `COIN_PIN=12`, but only the unused `PaymentHandler` read
it. The inhibit pin (22) was right, which is why the acceptor opened and closed on cue
while no value ever reached the payment. Pins now come from config, with defaults
matching `.env.example`.

Fixing the pin alone wasn't enough. An earlier raw test on GPIO 12 showed ~85
sub-millisecond spikes per second with no coin present; falling-edge counting with a
0.1 s debounce would keep the pulse count climbing so a coin never finished. With
`COIN_PULSE_FILTER` on (default), pigpio's glitch filter (5 ms) is set on the pin and
only low pulses 10–150 ms wide are counted, timed from the edges' own ticks. Turning
the filter off restores the old counting, which is kept deliberately as a way to check
the wiring on its own. A count that matches no coin is now logged instead of dropped
silently, and `enable_payment()` clears any half-counted coin.

The first kiosk log showed a ₱1 is 3 pulses, which the old table (₱1 = 1) ignored; the
old table would also have credited a ₱20 as ₱10. The table now matches the one in
`payment_handler.py`: ₱1 3–4, ₱5 5–6, ₱10 8–9, ₱20 11–12. On the kiosk the measured
counts were 3/5/8/11, all pulses ~66–74 ms wide, and every coin credited correctly.

### 2. Acceptor signals connected once — `SSP/screens/payment/model.py` (#68; also #64)

`setup_gpio()` runs on every payment `on_enter()` and connected the acceptor signals
each time without disconnecting. Both objects live for the whole app run (the app
doesn't restart between customers), so after N visits each coin was credited N times,
including when a customer taps Back and returns. This had been fixed on 2026-10-08 in
#64, which was never merged; it only became visible once coins started crediting, and
was fixed again in #68. #64 is now redundant.

### 3. Hopper sensors found by scanning — `SSP/managers/hopper_manager.py` (#70)

During #68's tests the hoppers paid ₱11 for ₱4 owed and ₱75 for ₱14 owed. The code
listened for coin-out pulses on GPIO 10/11, where nothing arrives, so each coin ran the
motor 5 × 10 s waiting for a pulse that never came. Rather than trust the wiring notes
(this is the second time coded pins didn't match the kiosk), every GPIO was scanned
with a motor-off baseline while each hopper ran: hopper A's sensor is GPIO 9 (5 coins
out, 5 low pulses of 43–48 ms) and B's is GPIO 26 (4 coins, 59–183 ms). Pins now come
from `.env` (`HOPPER_A/B_SIGNAL/ENABLE_PIN`), with defaults matching this kiosk.

Without filtering, both sensor lines see thousands of noise edges a second while a
motor runs, so they get the same treatment as the coin line: a 5 ms glitch filter and
one low pulse 20–300 ms wide per coin, timed from edge ticks.

### 4. Payouts that fail safe — `hopper_manager.py`, `payment/{model,controller}.py`, `main_app.py` (#70)

The bigger design change is what happens when a coin isn't seen. Before, an empty,
jammed or miswired hopper could run 50 s per coin. Now each coin gets one 1.5 s attempt
(the hoppers pay about 5 coins/s) and no retry; a coin the sensor doesn't see stops
that hopper and the rest of the change becomes a Voucher, the same as any other hopper
failure. This trades a possible small shortfall for never paying out an unbounded
amount, and the Voucher system already exists to absorb the shortfall.

Four related holes were closed on the way:
- **Motor off first.** The enable pin is written off before it's set as an output;
  setting the mode first could pulse the motor at every payment (likely the stray ₱5
  seen in one test).
- **Payout can't be interrupted from the screen.** From auto-complete until the change
  is out, Back is ignored, Back and Vouchers are greyed out, and the timeout is deferred
  (`PaymentModel.is_busy()`). Before, Back mid-payout stopped the hoppers and logged the
  paid job as **cancelled**.
- **Motors stopped on exit and at startup.** pigpiod keeps a pin's level after the app
  exits, so Ctrl+C mid-payout left hopper A running empty until the next start — 31
  coins came out. `stop_all_hopper_motors()` switches both motors off over its own
  pigpio connection; `main_app` calls it at startup and first in `cleanup()`, after
  ending any payout so it can't restart a motor.
- **Money restarts the timeout.** A credited coin or bill now restarts the 60 s payment
  timeout; only taps did, so the screen could time out while a bill was going in.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/managers/persistent_gpio.py` | modified (+59/-16) | coin pins from config, glitch filter, pulse-width counting, coin table |
| `SSP/managers/hopper_manager.py` | modified (+85/-65) | sensor pins from config, filter, 1.5 s cap, motor-off-first, `stop_all_hopper_motors` |
| `SSP/screens/payment/model.py` | modified (+30/-5) | signals connected once, `is_busy()` |
| `SSP/screens/payment/controller.py` | modified (+7) | Back/timeout guarded during payout, money restarts timeout |
| `SSP/main_app.py` | modified (+22) | stop motors at startup and in `cleanup()` |
| `SSP/config.py`, `.env.example` | modified (+100/-4) | acceptor, filter and hopper pin settings |
| `CLAUDE.md` | modified (+11/-7) | pins come from `.env`, hopper behaviour |
| `tests/test_persistent_gpio_coin_filter.py` | added (+131/-3) | synthetic pigpio edges: noise, wide pulses, tick wrap, unmatched counts, filter off |
| `tests/test_hopper_controller.py` | added (+134) | fake pigpio: pins, motor-off order, filter, measured widths, unseen coin stops |
| `tests/test_payment_change_flow.py` | modified (+61) | signals once, Back during payout, timeout restart |

## Testing guide

```bash
make test    # 573 passed on main 81a0225 (556 at #68 + 17 from #70); re-run 2026-10-16
make lint    # clean
```

Also verified on the kiosk Pi (2026-10-15, PR checklists ticked):
- Coins: ₱1/₱5/₱10/₱20 credit correctly; rejected outside payment; each coin credited
  once across repeated transactions.
- Change: exact payment runs no hopper; ₱10 for a ₱6 job pays exactly ₱4; ₱20 pays
  exactly ₱14 (2 × ₱5 + 4 × ₱1), with matching `SENSOR` log lines.
- Back greyed out and ignored during payout; job not logged as cancelled.
- Ctrl+C during payout stops the motor; a coin at ~50 s keeps the screen another 60 s.
- Empty hopper A: motor runs ~1.5 s, a Voucher covers the rest.

Manual, end-to-end (still to do):
1. **Bills.** No bill was accepted on 2026-10-15, but the bills on hand were worn.
   Retest with good bills of each denomination. The bill path is unchanged
   (falling-edge, 0.1 s debounce).

## Future considerations

1. **Bill acceptor not proven on the kiosk** — retest with good bills; if it fails,
   apply the coin line's pulse-width filtering to the bill line.
2. **Close #64** — its fix shipped in #68.
3. **Hardcoded inhibit pins remain** — `main_app` startup and the idle/payment
   controllers' manual-disable backups still use 22/23 directly, and
   `managers/payment_handler.py` is dead code. Both would bite on a second kiosk wired
   differently (multi-kiosk is a possibility).
4. **Overrun after the motor stops** — a coin may still leave a hopper after the motor
   is cut. Not seen in testing; the PR asks testers to report extras.
5. **Re-verify on the rebuilt card** — these tests ran 2026-10-15 on the new card
   before printer, QR reader and autostart were set up; repeat a full transaction
   including a real print once those are in place.
