"""
The journal of payments in progress (ADR 0011, issue #156).

A payment used to exist only in memory until it was settled, so a power cut
while a customer was paying lost their cash, any Voucher value already taken
and the change still owed, without a trace. Now each payment has a
`pending_payments` row from its first coin until its outcome is recorded:

- `record()` on every coin or bill credited, and at commit (when the payment
  gets its payment_ref, just before the Applied Vouchers are taken off);
- `coin_out()` after each change coin the hopper sensor sees, from the
  dispense thread;
- deleted when the print outcome is recorded (`finish()`, from print_refund),
  or with the cancelled transaction when Carried Credit becomes a Voucher
  (`delete_entry()` inside that transaction).

A row still there at startup belongs to a run that never finished the payment;
managers/payment_recovery.py turns it into an Interrupted Payment.

Each write here opens its own short-lived connection with synchronous=FULL, so
it is on disk before the call returns and is safe from any thread. A write that
fails is logged and never stops the payment: the customer is in front of the
kiosk, and the journal only matters if the power goes.
"""
import json
import sqlite3
from datetime import datetime


def _cash_json(cash):
    return json.dumps({str(int(d)): int(n) for d, n in (cash or {}).items() if n})


def _summary_json(payment_data):
    """The transaction columns recovery needs to log the payment, from its items."""
    items = (payment_data or {}).get('items') or []
    if not items:
        return None
    from managers.print_items import summary_columns
    try:
        return json.dumps(summary_columns(items))
    except Exception as e:
        print(f"WARNING: payment journal could not summarise the job: {e}")
        return None


class PaymentJournal:
    def __init__(self, db_path, now_fn=datetime.now):
        self.db_path = db_path
        self._now = now_fn

    def _write(self, sql, params):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                conn.execute("PRAGMA synchronous=FULL")
                with conn:
                    conn.execute(sql, params)
            finally:
                conn.close()
            return True
        except Exception as e:
            print(f"WARNING: payment journal write failed: {e}")
            return False

    def record(self, journal_id, cash, total_cost, payment_data, payment_ref=None):
        """Create or update the payment's row with what has been put in so far.
        Never touches the coins counted out, and never clears a payment_ref
        once set (a later coin is recorded without one)."""
        now = self._now()
        return self._write(
            """INSERT INTO pending_payments
                   (journal_id, payment_ref, cash_received, total_cost, source, summary, started_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(journal_id) DO UPDATE SET
                   payment_ref = COALESCE(excluded.payment_ref, payment_ref),
                   cash_received = excluded.cash_received,
                   total_cost = excluded.total_cost,
                   source = excluded.source,
                   summary = COALESCE(excluded.summary, summary),
                   updated_at = excluded.updated_at""",
            (journal_id, payment_ref, _cash_json(cash), float(total_cost or 0),
             (payment_data or {}).get('source'), _summary_json(payment_data), now, now))

    def coin_out(self, journal_id, denomination):
        """One change coin came out (the sensor saw it)."""
        column = {1: 'coins_1_out', 5: 'coins_5_out'}.get(int(denomination))
        if column is None or not journal_id:
            return False
        return self._write(
            f"UPDATE pending_payments SET {column} = {column} + 1, updated_at = ? WHERE journal_id = ?",
            (self._now(), journal_id))

    def delete(self, journal_id):
        """The payment ended with nothing owed and nothing recorded (no cash went in)."""
        if not journal_id:
            return False
        return self._write("DELETE FROM pending_payments WHERE journal_id = ?", (journal_id,))


def delete_entry(conn, journal_id=None, payment_ref=None):
    """Delete a journal row inside the caller's transaction (no commit)."""
    if journal_id:
        conn.execute("DELETE FROM pending_payments WHERE journal_id = ?", (journal_id,))
    elif payment_ref:
        conn.execute("DELETE FROM pending_payments WHERE payment_ref = ?", (payment_ref,))


def finish(db, payment_ref):
    """The payment's outcome is recorded: it no longer needs recovering. Safe to
    call more than once, and for a ref that was never journaled."""
    if not payment_ref or not getattr(db, 'conn', None):
        return False
    try:
        delete_entry(db.conn, payment_ref=payment_ref)
        db.conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"WARNING: could not clear the payment journal for {payment_ref}: {e}")
        return False


def read_entries(conn):
    """Every journal row, oldest first, as plain dicts with cash_received and
    summary decoded."""
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    cursor.execute("SELECT * FROM pending_payments ORDER BY started_at")
    entries = []
    for row in cursor.fetchall():
        entry = dict(row)
        try:
            entry['cash_received'] = {int(d): int(n) for d, n in json.loads(entry['cash_received'] or '{}').items()}
        except (ValueError, TypeError):
            entry['cash_received'] = {}
        try:
            entry['summary'] = json.loads(entry['summary']) if entry['summary'] else None
        except (ValueError, TypeError):
            entry['summary'] = None
        entries.append(entry)
    return entries
