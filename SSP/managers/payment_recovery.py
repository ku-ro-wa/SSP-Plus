"""
Recovering payments a power cut (or crash) interrupted, and settling them
(ADR 0011, issue #156).

At startup `recover_interrupted_payments()` turns each payment journal row
(managers/payment_journal.py) into an **Interrupted Payment**: a record of what
the customer is owed. It never issues a Voucher by itself, because whoever is
at the kiosk when it comes back may not be the customer who paid. An operator
settles it in Kiosk Admin, with the customer present (`settle_with_voucher`),
or records a cash refund (`settle_in_cash`, either side).

Recovery works out what happened from what's in the database, not from what
the last run meant to do, so it is safe however often it runs and wherever the
last run stopped:

- the payment has a transactions row that isn't `paid`: its outcome was
  recorded; only the journal row was left. Nothing is owed.
- it has a `paid` row: it was settled (cash counted, change out) and the print
  was cut off. Owed: the cost of the files not marked printed (the whole cost
  if it has no file rows). The row becomes `interrupted`.
- it has no row: the cut came while paying or dispensing. Owed: the cash put in
  plus the Voucher value Applied under its payment_ref, less the change coins
  counted out. An `interrupted` row is logged and the cash inventory adjusted.

Each journal row is handled in one SQLite transaction (the Interrupted Payment,
the transaction row, the inventory and the journal row's deletion), so a cut
during recovery leaves all of it or none of it. The operator alert (error_log
row and SMS) goes after the commit, marked by alerted_at; a cut between the two
sends it twice at most.
"""
import subprocess
import uuid
from datetime import datetime

from managers.admin_actions import record_action
from managers.payment_journal import delete_entry, read_entries

INTERRUPTED = 'interrupted'        # transactions.status
STAGE_PAYMENT = 'payment'          # cut while paying or dispensing change
STAGE_PRINTING = 'printing'        # cut after settlement, before the print outcome
OWED = 'owed'
SETTLED = 'settled'
HOW_VOUCHER = 'voucher'
HOW_CASH = 'cash'
ACTION_INTERRUPTED = 'interrupted_payment'

ERROR_TYPE = "Power Loss Recovery"


def _default_summary():
    return {'file_name': "unknown.pdf", 'pages': 0, 'copies': 1, 'color_mode': 'Color', 'file_count': 1}


def _voucher_value_applied(conn, payment_ref):
    if not payment_ref:
        return 0
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM voucher_applications WHERE payment_ref = ?",
                   (payment_ref,))
    row = cursor.fetchone()
    return int((row['total'] if isinstance(row, dict) else row[0]) or 0)


def _has_paid_row(db, entry):
    row = db.get_transaction_by_ref(entry['payment_ref']) if entry['payment_ref'] else None
    return bool(row and row['status'] == 'paid')


def _recover_one(db, entry, now):
    """One journal row, inside the caller's transaction. Returns the Interrupted
    Payment's fields, or None if nothing is owed."""
    conn = db.conn
    ref = entry['payment_ref']
    row = db.get_transaction_by_ref(ref) if ref else None

    if row and row['status'] != 'paid':
        delete_entry(conn, journal_id=entry['journal_id'])
        return None

    if row:
        stage = STAGE_PRINTING
        files = db.get_transaction_files(ref)
        for f in files:
            if f['status'] == 'pending':
                db.set_transaction_file_status(ref, f['position'], 'not_printed', commit=False)
        if files:
            owed = int(round(sum(f['cost'] for f in files if f['status'] != 'printed')))
        else:
            owed = int(round(row['total_cost'] or 0))
        cash = float(row['amount_paid'] or 0)
        applied = float(row['voucher_applied'] or 0)
        dispensed = float(row['change_dispensed'] or 0)
        db.update_transaction_outcome(ref, INTERRUPTED, from_status='paid',
                                      error_message="Interrupted while printing (power loss or crash)",
                                      commit=False)
    else:
        stage = STAGE_PAYMENT
        ref = ref or uuid.uuid4().hex
        cash_by_denom = entry['cash_received']
        cash = sum(d * n for d, n in cash_by_denom.items())
        applied = _voucher_value_applied(conn, entry['payment_ref'])
        coins_out = {1: int(entry['coins_1_out'] or 0), 5: int(entry['coins_5_out'] or 0)}
        dispensed = coins_out[1] + 5 * coins_out[5]
        if not cash and not applied and not dispensed:
            delete_entry(conn, journal_id=entry['journal_id'])
            return None
        owed = max(0, int(round(cash + applied - dispensed)))
        logged = db.log_transaction({
            **(entry['summary'] or _default_summary()),
            'total_cost': float(entry['total_cost'] or 0),
            'amount_paid': float(cash),
            'change_given': dispensed,
            'status': INTERRUPTED,
            'error_message': "Interrupted during payment (power loss or crash)",
            'source': entry['source'],
            'change_dispensed': dispensed,
            'voucher_issued': 0,
            'voucher_applied': applied,
            'payment_ref': ref,
        }, commit=False)
        if not logged:
            raise RuntimeError(f"could not log the interrupted transaction {ref}")
        for denom, count in cash_by_denom.items():
            if count:
                db.adjust_cash_inventory(denom, count, 'bill' if denom >= 20 else 'coin', commit=False)
        for denom, count in coins_out.items():
            if count:
                db.adjust_cash_inventory(denom, -count, 'coin', commit=False)

    delete_entry(conn, journal_id=entry['journal_id'])
    if owed <= 0:
        return None
    conn.execute(
        """INSERT OR IGNORE INTO interrupted_payments
               (payment_ref, interrupted_at, recovered_at, stage, cash_received, voucher_applied,
                change_dispensed, amount_owed, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ref, entry['updated_at'], now, stage, cash, applied, dispensed, owed, OWED))
    return {'payment_ref': ref, 'stage': stage, 'amount_owed': owed, 'interrupted_at': entry['updated_at']}


def recover_interrupted_payments(db, cancel_print_jobs=None, now_fn=datetime.now):
    """Turn every payment journal row into an Interrupted Payment (or nothing,
    when nothing is owed). `cancel_print_jobs` runs first if any payment was
    cut off while printing: CUPS keeps spooled jobs across a reboot and would
    print them later. Returns the Interrupted Payments created."""
    if not getattr(db, 'conn', None):
        return []
    try:
        entries = read_entries(db.conn)
    except Exception as e:
        print(f"❌ Could not read the payment journal: {e}")
        return []
    if not entries:
        return []

    if cancel_print_jobs and any(_has_paid_row(db, e) for e in entries):
        try:
            cancel_print_jobs()
        except Exception as e:
            print(f"⚠️ Could not cancel leftover print jobs: {e}")

    recovered = []
    for entry in entries:
        try:
            result = _recover_one(db, entry, now_fn())
            db.conn.commit()
        except Exception as e:
            db.conn.rollback()
            print(f"❌ Could not recover interrupted payment {entry['journal_id']}: {e}")
            _log_error(f"Could not recover an interrupted payment (journal {entry['journal_id']}, "
                       f"ref {(entry['payment_ref'] or '')[:8]}): {e}")
            continue
        if result:
            print(f"⚠️ Interrupted payment recovered: P{result['amount_owed']} owed, ref {result['payment_ref'][:8]}")
            recovered.append(result)
    return recovered


def _log_error(message):
    try:
        from utils.error_logger import log_error
        log_error(ERROR_TYPE, message, "payment_recovery")
    except Exception:
        pass


def alert_message(row):
    when = row['interrupted_at']
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when)
        except ValueError:
            when = None
    at = f" at {when.strftime('%H:%M %d %b')}" if isinstance(when, datetime) else ""
    during = "printing" if row['stage'] == STAGE_PRINTING else "a payment"
    return (f"Kiosk lost power during {during}{at}: P{row['amount_owed']} owed to the customer. "
            f"Settle it in Kiosk Admin. Ref {row['payment_ref'][:8]}")


def send_pending_alerts(db, log_error=None, send_sms=None, now_fn=datetime.now):
    """Alert the operator about every Interrupted Payment not alerted yet: one
    unresolved error_log row and one SMS each. Never includes a Voucher code
    (none exists yet). Returns how many were sent."""
    if log_error is None:
        from utils.error_logger import log_error
    if send_sms is None:
        from managers.sms_manager import send_operator_alert as send_sms
    sent = 0
    for row in _query(db, "SELECT * FROM interrupted_payments WHERE alerted_at IS NULL ORDER BY id"):
        message = alert_message(row)
        try:
            log_error(ERROR_TYPE, message, "payment_recovery")
        except Exception as e:
            print(f"⚠️ Could not log the interrupted payment: {e}")
        try:
            send_sms(message)
        except Exception as e:
            print(f"⚠️ Could not send the interrupted payment SMS: {e}")
        try:
            db.conn.execute("UPDATE interrupted_payments SET alerted_at = ? WHERE id = ?", (now_fn(), row['id']))
            db.conn.commit()
        except Exception as e:
            print(f"⚠️ Could not mark the interrupted payment alerted: {e}")
        sent += 1
    return sent


def cancel_all_print_jobs():
    """Cancel every queued CUPS job (the kiosk has one printer)."""
    subprocess.run(['cancel', '-a'], capture_output=True, text=True, timeout=10)


# ------------------------------------------------------------------ reading

def _query(db, sql, params=()):
    if not getattr(db, 'conn', None):
        return []
    try:
        cursor = db.conn.cursor()
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        print(f"⚠️ Could not read interrupted payments: {e}")
        return []


def owed_payments(db):
    """Interrupted Payments not settled yet, oldest first."""
    return _query(db, "SELECT * FROM interrupted_payments WHERE status = ? ORDER BY id", (OWED,))


def owed_total(db):
    return sum(int(r['amount_owed']) for r in owed_payments(db))


# ------------------------------------------------------------------ settling

def _describe(row):
    return f"P{row['amount_owed']} owed, ref {row['payment_ref'][:8]}"


def _owed_row(db, payment_id):
    rows = _query(db, "SELECT * FROM interrupted_payments WHERE id = ? AND status = ?", (payment_id, OWED))
    return rows[0] if rows else None


def settle_with_voucher(db, payment_id, who, voucher_manager=None, now_fn=datetime.now):
    """Issue the Voucher for an owed Interrupted Payment and mark it settled, in
    one transaction. Returns the IssuedVoucher (to show the customer once), or
    None if it isn't owed any more (already settled: a double tap issues one
    Voucher). Raises if the Voucher couldn't be saved; nothing is settled then."""
    row = _owed_row(db, payment_id)
    if row is None:
        return None
    if voucher_manager is None:
        from managers.voucher_manager import VoucherManager
        voucher_manager = VoucherManager(db)
    conn = db.conn
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE interrupted_payments SET status = ?, settled_at = ?, settled_how = ?, settled_by = ? "
            "WHERE id = ? AND status = ?",
            (SETTLED, now_fn(), HOW_VOUCHER, who['actor'], payment_id, OWED))
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        conn.execute("UPDATE transactions SET voucher_issued = COALESCE(voucher_issued, 0) + ? "
                     "WHERE payment_ref = ?", (int(row['amount_owed']), row['payment_ref']))
        # VoucherManager.issue() commits on this same connection, so the Voucher
        # and the two updates above are saved together, or (if it raises) not at all.
        voucher = voucher_manager.issue(row['amount_owed'], payment_ref=row['payment_ref'])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    record_action(db, ACTION_INTERRUPTED, _describe(row), "voucher issued", **who)
    return voucher


def settle_in_cash(db, payment_id, who, now_fn=datetime.now):
    """The attendant paid it back by hand. Returns True if it was owed and is
    now settled; False if it was already settled (nothing written)."""
    row = _owed_row(db, payment_id)
    if row is None:
        return False
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE interrupted_payments SET status = ?, settled_at = ?, settled_how = ?, settled_by = ? "
            "WHERE id = ? AND status = ?",
            (SETTLED, now_fn(), HOW_CASH, who['actor'], payment_id, OWED))
        changed = cursor.rowcount == 1
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise
    if changed:
        record_action(db, ACTION_INTERRUPTED, _describe(row), "refunded in cash", **who)
    return changed


# ------------------------------------------------------------------ startup

# '1' once a run's cleanup() finished; set to '0' while a run is going. A '0'
# at startup means the last run ended without it: a power cut or a crash.
SETTING_CLEAN_EXIT = 'kiosk_clean_exit'


def mark_clean_exit(db):
    try:
        db.update_setting(SETTING_CLEAN_EXIT, 1)
    except Exception as e:
        print(f"⚠️ Could not record the clean exit: {e}")


def startup_recovery(db, sim_mode=False):
    """Run once at startup, before the window opens: recover interrupted payments
    and alert the operator. Returns True if the last run didn't exit cleanly (the
    idle screen then shows the restart notice, whether or not anything is owed).
    Never raises: the kiosk starts regardless."""
    unclean = False
    try:
        unclean = str(db.get_setting(SETTING_CLEAN_EXIT, 1)) != '1'
        db.update_setting(SETTING_CLEAN_EXIT, 0)
        recover_interrupted_payments(db, cancel_print_jobs=None if sim_mode else cancel_all_print_jobs)
        send_pending_alerts(db)
    except Exception as e:
        print(f"❌ Startup payment recovery failed: {e}")
    return unclean
