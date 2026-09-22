"""
Tests that DatabaseManager.log_transaction actually persists the `source`
column (issue #12 added the column; this closes the gap where nothing in
the real write path ever populated it, which meant get_accounting_summary's
`WHERE source IS NOT NULL` filter silently excluded every real transaction).
"""
from database.db_manager import DatabaseManager
from database.models import init_db


def _base_transaction(**overrides):
    data = {
        'file_name': 'doc.pdf',
        'pages': 2,
        'copies': 1,
        'color_mode': 'Color',
        'total_cost': 5.0,
        'amount_paid': 5.0,
        'change_given': 0.0,
        'status': 'completed',
    }
    data.update(overrides)
    return data


class TestLogTransactionPersistsSource:
    def _manager(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        return DatabaseManager(db_path=db_path)

    def test_source_is_written_for_each_known_value(self, tmp_path):
        db = self._manager(tmp_path)
        for source in ("usb", "wifi", "email", "scanner"):
            db.log_transaction(_base_transaction(source=source))

        rows = db.get_transaction_history()
        assert [row['source'] for row in rows] == ["scanner", "email", "wifi", "usb"]

    def test_missing_source_key_does_not_raise(self, tmp_path):
        db = self._manager(tmp_path)
        db.log_transaction(_base_transaction())

        rows = db.get_transaction_history()
        assert rows[0]['source'] is None

    def test_logged_transaction_is_counted_in_accounting_summary(self, tmp_path):
        db = self._manager(tmp_path)
        db.log_transaction(_base_transaction(source="scanner", total_cost=3.0))

        summary = {row['source']: row for row in db.get_accounting_summary()}
        assert summary['scanner']['revenue'] == 3.0
        assert summary['scanner']['transaction_count'] == 1
