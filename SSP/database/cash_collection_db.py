# database/cash_collection_db.py
#
# Cash collection persistence for DatabaseManager (issue #110), a mixin like
# voucher_db.py. A collection is the operator physically emptying the kiosk and
# recording what they counted: one `cash_collections` row, one
# `cash_collection_items` row per denomination, and every `cash_inventory`
# count zeroed, all in one SQLite transaction.
#
# The coin figures are the operator's physical count, not a tally of coins
# received: received coins are added to the hopper count, so the ₱1/₱5 counts
# mix takings with stock. Bills are pure accumulation and reconcile exactly.
import sqlite3
from datetime import datetime

# Denominations always listed, even before cash_inventory has a row for them.
STOCKED_COINS = (1, 5)


class CashCollectionDBMixin:
    def get_collection_preview(self):
        """What a collection would record right now: every denomination with its
        count (₱1 and ₱5 always present, zero-filled), and the total in pesos."""
        counts = {}
        for item in self.get_cash_inventory() or []:
            counts[(float(item['denomination']), item['type'])] = int(item['count'])
        for denom in STOCKED_COINS:
            counts.setdefault((float(denom), 'coin'), 0)
        items = [
            {'denomination': denom, 'type': kind, 'count': count}
            for (denom, kind), count in sorted(counts.items())
        ]
        total = sum(i['denomination'] * i['count'] for i in items)
        return {'items': items, 'total': total}

    def record_cash_collection(self, note=None, collected_at=None):
        """Record the current counts as a collection and zero every inventory
        count, atomically. Returns the collection id, or None if nothing was
        written (no connection, or a database error, which rolls back)."""
        if not self.conn:
            return None
        when = collected_at or datetime.now()
        try:
            cursor = self.conn.cursor()
            if self.conn.in_transaction:
                self.conn.commit()
            # Take the write lock before reading the counts, so a payment settling
            # on another connection can't change them between the read and the zeroing.
            cursor.execute("BEGIN IMMEDIATE")
            preview = self.get_collection_preview()
            cursor.execute(
                "INSERT INTO cash_collections (collected_at, total, note) VALUES (?, ?, ?)",
                (when, preview['total'], note),
            )
            collection_id = cursor.lastrowid
            cursor.executemany(
                "INSERT INTO cash_collection_items (collection_id, denomination, type, count) "
                "VALUES (?, ?, ?, ?)",
                [(collection_id, i['denomination'], i['type'], i['count']) for i in preview['items']],
            )
            cursor.execute("UPDATE cash_inventory SET count = 0, last_updated = ?", (when,))
            self.conn.commit()
            return collection_id
        except sqlite3.Error as e:
            print(f"Error recording cash collection: {e}")
            try:
                self.conn.rollback()
            except sqlite3.Error:
                pass
            return None

    def get_cash_collections(self, limit=50):
        """Collections newest first, each with its per-denomination `items`."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM cash_collections ORDER BY collected_at DESC, id DESC LIMIT ?",
                (int(limit),),
            )
            collections = cursor.fetchall()
            for collection in collections:
                cursor.execute(
                    "SELECT denomination, type, count FROM cash_collection_items "
                    "WHERE collection_id = ? ORDER BY denomination",
                    (collection['id'],),
                )
                collection['items'] = cursor.fetchall()
            return collections
        except sqlite3.Error as e:
            print(f"Error getting cash collections: {e}")
            return []

    def get_last_collection_time(self):
        """collected_at of the newest collection, or None if there has been none."""
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT MAX(collected_at) AS last FROM cash_collections")
            row = cursor.fetchone()
            return row['last'] if row else None
        except sqlite3.Error as e:
            print(f"Error getting last collection time: {e}")
            return None
