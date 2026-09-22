"""
Tests for database/models.py:init_db(), in particular the idempotent
migration mechanism that adds transactions.source (issue #12). Each test
points init_db() at its own temp SQLite file (db_path param) rather than the
real ssp_database.db, so nothing here touches the kiosk's actual database.
"""
import sqlite3

from database.models import init_db, _column_exists


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cursor.fetchall()]
    finally:
        conn.close()


class TestFreshDatabase:
    def test_transactions_table_has_source_column(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        init_db(db_path)

        assert "source" in _columns(db_path, "transactions")

    def test_source_column_accepts_known_source_values(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            for source in ("usb", "wifi", "email", "scanner"):
                cursor.execute(
                    "INSERT INTO transactions "
                    "(timestamp, file_name, pages, copies, color_mode, total_cost, "
                    " amount_paid, change_given, status, source) "
                    "VALUES (?, 'f.pdf', 1, 1, 'Color', 1.0, 1.0, 0.0, 'success', ?)",
                    ("2026-09-22T00:00:00", source),
                )
            conn.commit()
            cursor.execute("SELECT source FROM transactions ORDER BY id")
            assert [row[0] for row in cursor.fetchall()] == ["usb", "wifi", "email", "scanner"]
        finally:
            conn.close()


class TestMigrationOfExistingDatabase:
    def _make_pre_migration_db(self, db_path):
        """A transactions table shaped like it was before this ticket —
        no source column — with one existing row, mirroring a real
        already-initialized database that predates the migration."""
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    file_name TEXT NOT NULL,
                    pages INTEGER NOT NULL,
                    copies INTEGER NOT NULL,
                    color_mode TEXT NOT NULL,
                    total_cost REAL NOT NULL,
                    amount_paid REAL NOT NULL,
                    change_given REAL NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            ''')
            cursor.execute(
                "INSERT INTO transactions "
                "(timestamp, file_name, pages, copies, color_mode, total_cost, "
                " amount_paid, change_given, status) "
                "VALUES ('2026-01-01T00:00:00', 'old.pdf', 2, 1, 'Color', 5.0, 5.0, 0.0, 'success')"
            )
            conn.commit()
        finally:
            conn.close()

    def test_adds_column_without_error(self, tmp_path):
        db_path = str(tmp_path / "existing.db")
        self._make_pre_migration_db(db_path)

        init_db(db_path)

        assert "source" in _columns(db_path, "transactions")

    def test_existing_rows_are_preserved(self, tmp_path):
        db_path = str(tmp_path / "existing.db")
        self._make_pre_migration_db(db_path)

        init_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT file_name, source FROM transactions")
            rows = cursor.fetchall()
        finally:
            conn.close()

        assert rows == [("old.pdf", None)]

    def test_running_init_db_twice_is_a_noop(self, tmp_path):
        db_path = str(tmp_path / "existing.db")
        self._make_pre_migration_db(db_path)

        init_db(db_path)
        init_db(db_path)  # must not raise a duplicate-column error

        assert "source" in _columns(db_path, "transactions")


class TestColumnExistsHelper:
    def test_true_for_present_column(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            assert _column_exists(conn.cursor(), "transactions", "source") is True
        finally:
            conn.close()

    def test_false_for_absent_column(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        try:
            assert _column_exists(conn.cursor(), "transactions", "not_a_real_column") is False
        finally:
            conn.close()
