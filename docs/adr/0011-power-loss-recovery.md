# Power loss mid-payment: record what's owed, an operator releases it

_Status: accepted; implemented in issue #156, not yet tried on kiosk hardware. Builds on ADR 0003 (Vouchers) and ADR 0012 (abandoned payments)._

A payment exists only in memory until `PaymentModel.settle_transaction()` logs it as `paid`,
which happens after change is dispensed. If power is cut before that, the cash inserted, any
Voucher value already taken off by `_commit_vouchers()`, and the change still owed are all
lost without a trace: no transaction row, no Voucher, no change to `cash_inventory`. After
settlement, a cut leaves the row `paid` for good, with no print and no refund.

We decided the kiosk keeps a **journal of the payment in progress** in the database, and on
startup turns anything it finds there into an **Interrupted Payment**: a record of what the
customer is owed. Recovery does **not** issue a Voucher by itself. An operator issues one, or
refunds in cash, once they're satisfied the person asking is the customer who paid.

## Decisions

- **Journal.** One `pending_payments` row per payment, keyed by its own `journal_id` (the
  payment has no `payment_ref` until it's committed), holding the cash received, the job's
  transaction columns, its Source, `total_cost`, the `payment_ref` once there is one, and the
  ₱1/₱5 coins counted out (`managers/payment_journal.py`). Written:
  - on every coin or bill credited;
  - at commit, with the `payment_ref`, just before the Applied Vouchers are taken off (a
    payment by Voucher alone gets its row here);
  - after each coin the hopper sensor sees, from the dispense thread.

  Each write opens its own short-lived connection with `synchronous=FULL`, so it's on disk
  before the call returns and is safe from any thread (a queued `db_threader` write could be
  lost in the very cut this is for). The main connection uses `synchronous=FULL` too, since WAL
  with the default `NORMAL` can roll back the last commits after a power cut.

  It's deleted once the outcome is recorded (`managers/print_refund.py`, whichever of success,
  refund or Digital Copy failure ends the row's `paid` status), with the cancelled transaction
  when Carried Credit becomes a Voucher, and when the customer leaves with nothing in. Carried
  Credit keeps its row.

- **No stage column: recovery reads what happened from the database.** Writing a stage at each
  step would need it saved in the same transaction as the step, and would still have to be
  trusted. Instead recovery checks evidence that holds wherever the last run stopped:
  - the payment has a transactions row that isn't `paid`: the outcome was recorded and only the
    journal row was left. Nothing is owed.
  - it has a `paid` row: it was settled and the print was cut off. Settlement now writes the
    `paid` row and the `cash_inventory` change in one transaction, so a `paid` row means the
    cash and change are already counted.
  - it has no row: the cut came while paying or dispensing. The Voucher value Applied is read
    from `voucher_applications` by the journal's `payment_ref`, so taking it off the Vouchers
    needs no write to the journal at the same time.

- **A coin counts only once the sensor has seen it.** A cut mid-coin may let out one coin that
  wasn't counted, so the customer may receive up to ₱5 more than recorded. The kiosk absorbs
  that loss rather than the customer.

- **What's owed.** Before settlement nothing has printed, so the customer is owed everything
  they put in, less the coins that came out: `cash received + Voucher value applied − coins
  dispensed`. After settlement, any CUPS jobs left over are cancelled first (CUPS keeps spooled
  jobs across a reboot and would print them later), then the cost of the files not marked
  `printed` is owed (the whole `total_cost` for a row without file rows), as with
  `partly_printed` (ADR 0010). CUPS may already have printed a job before the app starts and
  cancels it; the operator's check covers that.

- **Recovery is one transaction and converges.** `recover_interrupted_payments()`
  (`managers/payment_recovery.py`) runs in `main()` after `init_db()`, after stopping the hopper
  motors, and before the window opens. For each journal row, in a single SQLite transaction it
  inserts the `interrupted_payments` row (`status='owed'`), logs the transaction (`interrupted`;
  not revenue), adjusts `cash_inventory` (cash in, coins out), and deletes the `pending_payments`
  row. A cut during recovery leaves either all of that or none of it, so the next start finishes
  the job or finds nothing. Any `pending_payments` row found at startup is stale by definition:
  the single-instance lock means no running copy can own it. `interrupted_payments.payment_ref`
  is `UNIQUE` as a second guard. The SMS and the unresolved `error_log` row
  (`Power Loss Recovery`, with the ref, amount and time, never a code) are sent after the commit;
  `alerted_at` is set once the SMS has gone, so a cut between the two sends at most one
  duplicate.

- **Nothing about money appears on screen at startup.** After a run that didn't exit cleanly
  (a `kiosk_clean_exit` setting `cleanup()` sets last and startup clears), idle shows "The kiosk
  restarted unexpectedly. If you were paying when it went off, please contact the attendant" for
  15 minutes, the same whether or not anything is owed. Whoever is standing at the kiosk when it
  comes back may not be the customer who paid.

- **An operator releases it.** In Kiosk Admin (behind `ADMIN_PIN`), a pending Interrupted
  Payment is offered (an "Owed payments" button, shown only while one is owed) with its amount,
  time and breakdown. The operator checks the customer's account against
  it (roughly what they paid, and when), then either:
  - **Issue Voucher:** issues it with the Interrupted Payment's `payment_ref` and shows it on
    the voucher screen (reason `INTERRUPTED`), so the code is shown once, to the customer, as
    ADR 0003 requires; or
  - **Refunded in cash:** records that the attendant paid it back by hand.

  Either one sets `status='settled'` in the same transaction, only from `'owed'`, so a double
  tap can't issue two Vouchers, and writes an `admin_actions` row (`interrupted_payment`). The
  Voucher's value is added to the transaction's `voucher_issued`. The Admin Dashboard lists
  Interrupted Payments on `/kiosk` (with **Refunded in cash** for `admin`:
  `POST /kiosk/owed/{id}/refunded-in-cash`, 409 once settled) but can't issue the
  Voucher, since a code shown on a remote screen would have to be passed on to the customer.

## Considered options

- **Show the Voucher on screen at startup:** the customer gets their money back without waiting
  for anyone, but if they've left, the next person at the kiosk gets it instead, and the kiosk
  can't tell them apart.
- **Tie the refund to the customer's pickup code or QR:** only a customer who printed a Session
  has one. USB and scanner customers have none, and a Wi-Fi customer who closed the page has
  lost theirs, so most interrupted payments couldn't be claimed.
- **Show a payment reference on the payment screen for the customer to note down:** nobody
  writes down a code before they know something will go wrong.
- **Keep doing nothing:** the customer loses the money, and the cash shows up only as an
  unexplained difference at Collect cash.

## Consequences

- A customer at an unattended kiosk waits for an operator to get their money back. This is the
  accepted cost of not handing credit to whoever is present at startup.
- What's owed but not yet settled shows on `/accounting` and the Reports screen as "Owed on
  interrupted payments", next to the Voucher liability. An `interrupted` transaction is not
  revenue; its change and Applied Vouchers count like `print_failed`'s.
- A Voucher issued for a Shortfall just before the cut was never shown (the voucher screen comes
  after settlement), so nobody holds its code; it only adds to the liability figure until it
  expires.
- With Vouchers turned off (`vouchers_enabled = 0`), only **Refunded in cash** is offered.
- A coin let out but not counted makes `cash_inventory` read one coin high until the next
  Collect cash.
- `settle_transaction()`'s once-per-`payment_ref` guard is still in memory only. That's fine,
  because whether a payment was settled is now decided by its `paid` row, which is stored in
  the database.
- A clean shutdown with cash in (an operator stopping the app mid-payment) also leaves a journal
  row, so that cash becomes an Interrupted Payment too, instead of being lost as before.
- A UPS on the Pi is still worth having. It makes this path rarer and protects the SD card,
  which a cut mid-write can corrupt whatever the app does.
