"""
Tests for Kiosk Admin's SIM_MODE-only "Empty All (SIM)" coin button: it zeroes
both hoppers' counts so a sim payment with change hits a Shortfall and shows
the Voucher screen, and it is never built outside SIM_MODE.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from screens.admin.view import AdminScreenView  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


@pytest.fixture
def model(db_path):
    from screens.admin import model as admin_model

    with patch.object(admin_model, "DatabaseManager", lambda: DatabaseManager(db_path=db_path)), \
            patch.object(admin_model, "get_sms_manager", lambda: MagicMock()):
        m = admin_model.AdminModel()
    return m


def _coin_counts(db_path):
    rows = DatabaseManager(db_path=db_path).get_cash_inventory()
    return {r['denomination']: r['count'] for r in rows if r['type'] == 'coin'}


def _button_texts(view):
    return [b.text() for b in view.findChildren(QPushButton)]


def test_empty_sets_both_coin_counts_to_zero(model, db_path):
    model.reset_coin_counts()
    shown = []
    model.coin_count_changed.connect(lambda one, five: shown.append((one, five)))

    model.empty_coin_counts()

    counts = _coin_counts(db_path)
    assert (counts[1], counts[5]) == (0, 0)
    assert shown[-1] == (0, 0)


def test_button_exists_only_in_sim_mode(qapp):
    assert "Empty All (SIM)" in _button_texts(AdminScreenView(sim_mode=True))
    assert "Empty All (SIM)" not in _button_texts(AdminScreenView(sim_mode=False))


def test_button_emits_empty_signal(qapp):
    view = AdminScreenView(sim_mode=True)
    fired = []
    view.empty_coins_clicked.connect(lambda: fired.append(True))

    next(b for b in view.findChildren(QPushButton) if b.text() == "Empty All (SIM)").click()

    assert fired == [True]
