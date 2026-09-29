# Vouchers: bearer credit for change the kiosk couldn't dispense

The hoppers only dispense ₱1 and ₱5 coins, and the acceptors can't refuse a bill, so a customer
can always pay more than the kiosk can give back in change. Today that difference is silently
lost: `ChangeDispenser` (`managers/hopper_manager.py`) stops at the first failed coin, dispenses
what it can, and still reports `success: True`, and `transactions.change_given` records the
change *owed*, not what came out. We decided the kiosk issues a **Voucher** (see `CONTEXT.md`)
for every **Shortfall** instead, so a sale is never blocked or short-changed for lack of coins.

## Decisions

- **Value is the Shortfall only.** The kiosk dispenses every coin it can first; the Voucher
  covers the remainder. This covers both the predicted case (the kiosk knew it was low) and a
  hopper jamming or running dry mid-dispense. The trigger is the measured shortfall
  (`expected_change - actual_change`), not the prediction.

- **Bearer credit, unrecoverable by design.** A Voucher code is 8 Crockford-base32 characters
  (shown `XXXX-XXXX`), persisted only as a salted hash like the Session OTP, and shown exactly
  once. Nobody — not Kiosk Admin, not the Admin Dashboard — can look up or reissue a lost code.
  This is deliberate: storing codes recoverably would turn the DB into a list of spendable money.
  Wrong-code attempts (at payment *and* at balance check) share one lockout counter, so the 30-day
  lifetime can't be used to brute-force codes at the touchscreen.

- **Partial use keeps the same code; expiry is fixed at issue.** Applying a Voucher decrements
  its remaining value rather than consuming it and reissuing a new code, so the customer's one
  photo stays valid. The history lives in a Voucher↔transaction link (needed anyway, since one
  payment can Apply several Vouchers alongside cash). When several are Applied, they are used in
  the order entered, so at most the last one is partly used. Expiry is 30 days from issue
  (`settings`-configurable) and is never extended by partial use — otherwise tiny periodic
  Applies would keep the outstanding liability alive forever.

- **Persist, then show.** The Voucher row is committed before its code is displayed. If the
  write fails, no code is shown; the customer is told the Shortfall amount and to contact the
  attendant, and the failure goes to `error_log` plus an operator alert.

- **QR payload is type-tagged.** The Voucher QR encodes `V1:<code>` so the (future) kiosk
  scanner can tell it apart from a Session payload (`session_id:otp`); only the payment screen
  accepts it.

- **Accounting separates cash from credit.** Each transaction records cash received, change
  actually dispensed, Voucher value issued, and Voucher value Applied as distinct amounts;
  revenue stays the job price. The Admin Dashboard shows outstanding Voucher liability
  (unexpired remaining value). Expired value drops out of the liability.

## Considered options

- **Consume-and-reissue on partial use** (Voucher is immutable; leftover becomes a new code):
  simpler invariant, but forces the customer to photograph a new code every time and loses
  their money if they don't. The link table gives the same audit trail, so we took partial use.
- **Voucher the whole change amount, dispense nothing:** rejected — it maximises the liability
  and gives the customer credit where real coins were available.
- **6-digit numeric code like the OTP:** fine for an hours-long Session, too guessable for a
  30-day bearer credit.
