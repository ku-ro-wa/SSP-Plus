"""Settings catalog (issue #106): validation, defaults and write path."""
import sqlite3

import pytest

from managers import payment_algorithm_manager, session_manager, voucher_manager
from managers.settings_catalog import (
    CATALOG, DASHBOARD, KIOSK, SettingError, get_setting_def, get_value,
    save_value, settings_for,
)

KEYS = {
    'voucher_expiry_days', 'voucher_lockout_minutes', 'session_expiry_minutes',
    'max_change_limit', 'min_coin_threshold_1', 'min_coin_threshold_5',
    'low_change_warning_threshold',
}


class FakeDB:
    """Mimics DatabaseManager's get_setting/update_setting on a temp SQLite."""
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)')

    def get_setting(self, key, default=None):
        row = self.conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if not row:
            return default
        try:
            return int(row['value'])
        except (ValueError, TypeError):
            return row['value']

    def update_setting(self, key, value):
        self.conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                          (key, str(value)))
        self.conn.commit()


def test_catalog_lists_the_seven_keys_only():
    assert {s.key for s in CATALOG} == KEYS
    assert 'vouchers_enabled' not in KEYS


def test_every_entry_is_complete_and_default_in_range():
    for s in CATALOG:
        assert s.label and s.minimum <= s.default <= s.maximum
        assert s.surfaces and set(s.surfaces) <= {KIOSK, DASHBOARD}


def test_defaults_match_the_managers():
    assert get_setting_def('voucher_expiry_days').default == voucher_manager.DEFAULT_EXPIRY_DAYS
    assert get_setting_def('voucher_lockout_minutes').default == voucher_manager.DEFAULT_LOCKOUT_MINUTES
    assert get_setting_def('session_expiry_minutes').default == session_manager.DEFAULT_EXPIRY_MINUTES
    assert (get_setting_def('low_change_warning_threshold').default
            == payment_algorithm_manager.DEFAULT_LOW_CHANGE_THRESHOLD)
    assert get_setting_def('max_change_limit').default == 50
    assert get_setting_def('min_coin_threshold_1').default == 0
    assert get_setting_def('min_coin_threshold_5').default == 0


@pytest.mark.parametrize('raw', ['abc', '', '  ', '5.5', None, 5.0, True, '1e3'])
def test_non_numeric_rejected(raw):
    with pytest.raises(SettingError):
        get_setting_def('voucher_expiry_days').validate(raw)


def test_out_of_range_rejected_not_clamped():
    s = get_setting_def('voucher_expiry_days')
    for bad in (s.minimum - 1, s.maximum + 1, '-3'):
        with pytest.raises(SettingError, match='between'):
            s.validate(bad)
    assert s.validate(s.minimum) == s.minimum
    assert s.validate(f' {s.maximum} ') == s.maximum


def test_save_writes_and_reads_back():
    db = FakeDB()
    assert get_value(db, 'max_change_limit') == 50
    assert save_value(db, 'max_change_limit', '80', surface=KIOSK) == 80
    assert get_value(db, 'max_change_limit') == 80
    assert db.get_setting('max_change_limit') == 80


def test_rejected_save_writes_nothing():
    db = FakeDB()
    with pytest.raises(SettingError):
        save_value(db, 'max_change_limit', '99999')
    assert db.get_setting('max_change_limit') is None


def test_unknown_and_database_only_keys_rejected():
    db = FakeDB()
    for key in ('vouchers_enabled', 'nope'):
        with pytest.raises(SettingError):
            save_value(db, key, 1)
    assert db.get_setting('vouchers_enabled') is None


def test_bad_stored_value_falls_back_to_default():
    db = FakeDB()
    db.update_setting('voucher_expiry_days', 'garbage')
    assert get_value(db, 'voucher_expiry_days') == 30
    db.update_setting('voucher_expiry_days', 9999)
    assert get_value(db, 'voucher_expiry_days') == 30


def test_settings_for_each_surface():
    assert {s.key for s in settings_for(KIOSK)} == KEYS
    assert {s.key for s in settings_for(DASHBOARD)} == KEYS


def test_save_many_is_all_or_nothing():
    from managers.settings_catalog import save_many
    db = FakeDB()
    saved, errors = save_many(db, {'voucher_expiry_days': '7', 'max_change_limit': 'x'}, surface=KIOSK)
    assert saved == {} and list(errors) == ['max_change_limit']
    assert db.get_setting('voucher_expiry_days') is None
    saved, errors = save_many(db, {'voucher_expiry_days': '7', 'max_change_limit': ' 60 '}, surface=KIOSK)
    assert errors == {} and saved == {'voucher_expiry_days': 7, 'max_change_limit': 60}
    assert db.get_setting('max_change_limit') == 60
    _, errors = save_many(db, {'vouchers_enabled': 0})
    assert 'vouchers_enabled' in errors and db.get_setting('vouchers_enabled') is None
