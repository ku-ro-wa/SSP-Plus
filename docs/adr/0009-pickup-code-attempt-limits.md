# Pickup codes: attempt limits on both surfaces that accept them

A **Pickup code** (the Session OTP) is 6 digits — 10^6 possibilities. The only limit was on the
QR path: a QR payload carries the session id, so a miss could be charged to that one Session
(`MAX_FAILED_ATTEMPTS` = 5, then the Session is `locked`). A *typed* code matched no candidate
when it was wrong, so `SessionManager.verify_otp_for_source()` returned "Incorrect or expired
code" and nothing was counted. A code could be guessed at the Wi-Fi or Email keypad, and at the
Portal's `/redeem` page (Digital Copy pickup, unauthenticated, reachable from any phone on the
Hotspot), with no limit and no delay.

Every other guessable secret in the kiosk already locks out: the touchscreen admin PIN
(#98, `managers/pin_lockout.py`), Voucher codes (ADR 0003), the Admin Dashboard login
(ADR 0002). Pickup codes were the gap.

## Decisions

- **The two surfaces get different limits, because their clients differ.** The kiosk has a
  screen to disable and one customer in front of it; the Portal has neither, only a source
  address.

- **Kiosk: one counter, shared by the Wi-Fi and Email screens, stored in `settings`.**
  `managers/pickup_code_lockout.py` (a subclass of the shared `AttemptLockout` that #98's
  `PinLockout` now also uses) counts consecutive wrong typed codes in
  `pickup_code_failed_attempts` and writes the deadline to `pickup_code_locked_until`. Five
  misses (or `pickup_code_max_attempts`) lock **typed** entry for five minutes (or
  `pickup_code_lockout_minutes`), whichever screen the customer is on. A correct code resets
  the counter. The deadline is a wall-clock timestamp, so leaving the screen, opening the other
  screen or restarting the app doesn't clear it. While locked, the keypad, entry field and Send
  are disabled and the status banner counts down — even the right code is refused.

- **Only guesses count, on either surface.** `SessionManager.verify_typed_otp()` returns an
  `OtpLookup` whose `matched` says whether the code hashed to a Session at all, of that Source or
  another. A real code that can't be redeemed here is `matched`, so it never counts: its Session
  expired or is already locked out, or — the likely one — it was typed on the wrong upload
  screen, since the Wi-Fi and Email tiles look alike and a customer holding a working Email code
  can pick Wi-Fi. The QR path already declined to count a wrong-Source attempt, and the typed
  limits keep that promise. Input that isn't six digits never reaches the lookup, so mashing
  keys can't lock entry for the next customer, and a malformed string at `/redeem` is refused
  before the limiter.

- **Portal: a per-client sliding window in the process, not the kiosk's counter.**
  `webapp/rate_limit.py` (`ClientAttemptLimiter`) keeps each request address's wrong-code times;
  5 inside 15 minutes refuse that client with `429` + `Retry-After` until its oldest counted
  failure ages out, and a correct code clears the client. State is in-memory on purpose: the
  kiosk runs one uvicorn server with no workers (`managers/webapp_thread.py`), a restart
  forgiving a guesser costs nothing (Session codes live 12 hours, and a Digital Copy code is
  useless once redeemed), and the low-trust Portal gets no table of its own to write. The two
  limits are deliberately separate in both directions: a phone guessing must not lock the
  keypad in front of a paying customer, and a customer's typos must not refuse a phone.

- **One `error_log` row per lockout**, in both surfaces (`Pickup Code`, with `Redeem Portal` as
  the context there). Refused attempts during a lockout don't log again. No operator SMS: the
  PIN lockout texts the operator because the touchscreen is being attacked by someone standing
  at it, while a customer's typos would page for nothing.

- **QR reads are untouched.** They keep locking the individual Session after 5 misses and never
  consult either counter. There is no need to lock the keypad for a payload that identifies
  itself.

## Considered options

- **One shared `settings` counter for both surfaces** (the Portal writing the kiosk's rows):
  simplest code, rejected — it lets any phone on the Hotspot lock the kiosk keypad for five
  minutes at a time, a denial of service against the customer in front of it, and it makes a
  customer's typos refuse a phone.
- **Per-Source delays at the kiosk** instead of a lockout: a fixed pause per wrong code is
  friendlier than a lock and works at the Portal too, but 10^6 codes at ~2 s each is still
  only weeks, and a delay can't be shown or enforced on a screen the customer walks away from.
  The kiosk needs a state the UI can display; a wall-clock deadline is that state.
- **Per-IP counters in the kiosk DB for the Portal**: survives restarts, but the Portal is the
  unauthenticated surface (ADR 0006) and a lockout that the attacker can create is a row an
  attacker can write. It also needs pruning and a schema for what is a 15-minute concern.
- **Locking the Portal out for a whole Source** after a burst: one phone could then halt Digital
  Copy pickup for everyone on the Hotspot.
- **Counting expired/locked Session matches, or wrong-Source codes, as misses:** simpler (`matched`
  and the cross-Source scan would not be needed), but retyping a real code that has just expired
  five times would lock the keypad, which is exactly the customer who needs help, not the
  attacker. The scan costs one hash comparison per pending Session of the other three Sources,
  on failures only.

## Consequences

- The kiosk's typed code space is now bounded to ~5 guesses per 5 minutes per kiosk — the
  customer can still mistype a code, but not walk the space. A customer who does lock it is
  told how long is left, and a QR read of the same code still works (printed or emailed code
  on a phone screen).
- The Portal's window is per request address. On the Hotspot that is each phone's own address
  (the kiosk's dnsmasq hands out a private range), so one guesser is bounded to ~5 guesses per
  15 minutes; a NAT in front of many phones would share one budget.
- Both limits live in the running process or in `settings`; the Admin Dashboard (a separate
  process) can read `pickup_code_locked_until` but never enforces it.
- `tests/test_pickup_code_lockout.py` (kiosk counter and both screens, fake clock),
  `tests/test_redeem_route.py::TestRedeemWrongCodeLimit` (Portal, fake clock) and
  `tests/test_session_manager.py::TestVerifyTypedOtp` (`matched`) cover it without a Qt event
  loop; `tests/test_onscreen_keypads.py` covers the disabled keypad and countdown banner.
