# database/voucher_db.py
#
# Voucher persistence for DatabaseManager. Kept as a mixin so db_manager.py
# only needs `class DatabaseManager(VoucherDBMixin):` plus the import; every
# method follows that file's conventions (self.conn, print-and-return on
# sqlite3.Error, dict-like rows). Schema lives in models.py (init_db).
#
# A voucher is "active" when remaining_value > 0 and expires_at is in the
# future; there is no status column, so there is no state to drift out of sync
# (an expired voucher simply stops matching). Expired rows are kept for audit.
import sqlite3


class VoucherDBMixin:
    def create_voucher(self, voucher_id, code_hash, value, created_at, expires_at, payment_ref=None):
        """Insert a new voucher worth `value` whole pesos. Returns True on success."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO vouchers
                    (voucher_id, code_hash, initial_value, remaining_value,
                     created_at, expires_at, payment_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (voucher_id, code_hash, value, value, created_at, expires_at, payment_ref))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error creating voucher: {e}")
            return False

    def get_active_vouchers(self, now):
        """Vouchers with value left that haven't expired, for hash-compare lookup."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM vouchers WHERE remaining_value > 0 AND expires_at > ? "
                "ORDER BY created_at", (now,)
            )
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting active vouchers: {e}")
            return []

    def get_inactive_vouchers(self, now):
        """Vouchers that are fully used or expired. Only consulted after a code
        misses every active voucher, to tell the customer which it was."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM vouchers WHERE remaining_value <= 0 OR expires_at <= ? "
                "ORDER BY created_at", (now,)
            )
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting inactive vouchers: {e}")
            return []

    def apply_vouchers(self, plan, payment_ref, applied_at):
        """
        Decrement each voucher in `plan` ([(voucher_id, amount), ...]) and
        record a voucher_applications row for each, all in ONE transaction:
        if any voucher no longer has `amount` left (or has expired), nothing
        is applied. The conditional UPDATE is what guarantees a voucher can
        never go negative. Returns True only if every line was applied.
        """
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            for voucher_id, amount in plan:
                cursor.execute("""
                    UPDATE vouchers SET remaining_value = remaining_value - ?
                    WHERE voucher_id = ? AND remaining_value >= ? AND expires_at > ?
                """, (amount, voucher_id, amount, applied_at))
                if cursor.rowcount != 1:
                    self.conn.rollback()
                    return False
                cursor.execute("""
                    INSERT INTO voucher_applications (voucher_id, amount, payment_ref, applied_at)
                    VALUES (?, ?, ?, ?)
                """, (voucher_id, amount, payment_ref, applied_at))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error applying vouchers: {e}")
            try:
                self.conn.rollback()
            except sqlite3.Error:
                pass
            return False

    def get_voucher_accounting(self, now, since=None):
        """Admin Dashboard figures (issue #28), in pesos:
        - change_dispensed: change that physically came out, over completed
          transactions (rows logged before #23 have NULL and count as 0);
        - issued / applied: Voucher value issued and Applied, read from the
          vouchers / voucher_applications ledger rather than transactions,
          since a transaction row is only logged once the print succeeds;
        - liability: remaining value of every unexpired Voucher right now.
        The first three are scoped to timestamp >= `since` when given;
        liability is a point-in-time figure and ignores it."""
        empty = {"change_dispensed": 0, "issued": 0, "applied": 0, "liability": 0}
        if not self.conn:
            return empty
        # (key, column summed, table, row filter, timestamp column)
        windowed = (
            ("change_dispensed", "change_dispensed", "transactions", "status = 'completed'", "timestamp"),
            ("issued", "initial_value", "vouchers", "1 = 1", "created_at"),
            ("applied", "amount", "voucher_applications", "1 = 1", "applied_at"),
        )
        try:
            cursor = self.conn.cursor()
            totals = {}
            for key, column, table, where, stamp in windowed:
                query = f"SELECT COALESCE(SUM({column}), 0) AS total FROM {table} WHERE {where}"
                params = ()
                if since is not None:
                    query += f" AND {stamp} >= ?"
                    params = (since,)
                totals[key] = cursor.execute(query, params).fetchone()["total"]
            totals["liability"] = cursor.execute(
                "SELECT COALESCE(SUM(remaining_value), 0) AS total FROM vouchers WHERE expires_at > ?",
                (now,)).fetchone()["total"]
            return totals
        except sqlite3.Error as e:
            print(f"Error getting voucher accounting: {e}")
            return empty
