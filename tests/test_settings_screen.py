"""Kiosk Admin's settings screen (issue #106): real model + view on a temp DB."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.settings_catalog import CATALOG  # noqa: E402
from screens.settings import SettingsController  # noqa: E402


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / 'settings_screen.db')
    init_db(path)
    d = DatabaseManager(db_path=path)
    yield d
    d.close()


@pytest.fixture
def screen(app, db):
    main_app = MagicMock()
    main_app.admin_screen.db_manager = db
    s = SettingsController(main_app)
    s.main_app = main_app
    s.on_enter()
    return s


def _type(screen, key, text):
    screen.view.fields[key].setText(text)


def test_lists_every_catalog_key_with_current_values(screen, db):
    assert set(screen.view.fields) == {s.key for s in CATALOG}
    assert screen.view.fields['max_change_limit'].text() == '50'
    assert screen.view.fields['session_expiry_minutes'].text() == '720'
    assert screen.view.fields['voucher_expiry_days'].text() == '30'  # seeded by init_db


def test_save_writes_and_applies_immediately(screen, db):
    _type(screen, 'max_change_limit', '80')
    screen.view.save_button.click()
    assert db.get_setting('max_change_limit') == 80
    assert 'Saved' in screen.view.status_label.text()


def test_invalid_value_saves_nothing_and_says_why(screen, db):
    _type(screen, 'voucher_expiry_days', '7')
    _type(screen, 'max_change_limit', '99999')
    screen.view.save_button.click()
    assert db.get_setting('voucher_expiry_days') == 30
    assert db.get_setting('max_change_limit') is None
    text = screen.view.status_label.text()
    assert 'Nothing saved' in text and 'Maximum change' in text


def test_non_numeric_rejected(screen, db):
    _type(screen, 'min_coin_threshold_1', 'abc')
    screen.view.save_button.click()
    assert 'whole number' in screen.view.status_label.text()
    assert db.get_setting('min_coin_threshold_1') is None


def test_vouchers_enabled_is_not_offered(screen):
    assert 'vouchers_enabled' not in screen.view.fields


def test_back_returns_to_admin(screen):
    screen.view.back_button.click()
    screen.main_app.show_screen.assert_called_with('admin')


def test_keypad_types_into_the_focused_field(screen):
    screen.view.show()
    field = screen.view.fields['max_change_limit']
    field.setFocus()
    field.clear()
    screen.view.keypad.key_buttons['7'].click()
    screen.view.keypad.key_buttons['5'].click()
    assert field.text() == '75'
