# Abandoned payments: Carried Credit, then a Voucher

Cash put in for a payment the customer didn't complete used to be kept by the kiosk:
Back logged a `cancelled_partial_payment` and reset the amount to ₱0, and a payment-screen
timeout didn't even record it. We decided that Back keeps the cash as **Carried Credit**
while the customer is on print options (it counts again when payment reopens, and completes
the payment at once if it already covers the new price), and that leaving for any other
screen, or timing out, abandons the payment and issues a **Voucher** for all of it. This
widens ADR 0003: a Voucher's value is a Shortfall *or* an abandoned payment's Carried Credit.
The same bearer, shown-once, persist-then-show rules apply.

## Considered options

- **Refund in coins, Voucher the rest:** the hoppers only hold ₱1/₱5 and can't return a
  bill, and refunds drain the coins needed for change, so most refunds would be Vouchers
  anyway, after a long wait at the hopper.
- **Block Back once cash is in:** stops the loss on Back, but a customer who only wants
  fewer pages is stuck, and a timeout still loses the money.
- **Keep the money, just record it:** the old behaviour, fixed so a timeout is logged. The
  customer still loses the money.

## Consequences

- Carried Credit lives in memory only, so an app restart while a customer is on print
  options loses it, as before this change.
- An abandoned payment is a `cancelled_partial_payment` transaction with `voucher_issued`
  set; it isn't revenue, but its Voucher counts in the Admin Dashboard's Voucher-issued total
  and in the outstanding liability.
- With vouchers turned off (`vouchers_enabled = 0`), an abandoned payment's cash is only
  recorded, as before.
