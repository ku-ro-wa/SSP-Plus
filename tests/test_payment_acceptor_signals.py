"""
PaymentModel is created once and reused for every customer, while the coin/bill
acceptor (persistent_gpio) is a process-wide singleton. Entering the payment
screen again must not connect the acceptor's signals again, or each coin is
credited once per earlier visit.
"""
import locale

import pytest
from PyQt5.QtCore import QCoreApplication, QObject, pyqtSignal

import screens.payment.model as payment_module
from database.db_manager import DatabaseManager
from database.models import init_db
from screens.payment.model import PaymentModel


class FakeAcceptors(QObject):
    """Stands in for the persistent_gpio singleton (hardware edge)."""
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)

    def enable_payment(self):
        pass

    def disable_payment(self):
        pass

    def process_coin_timeout(self):
        pass


@pytest.fixture(scope='module')
def qapp():
    # QCoreApplication() calls setlocale(LC_ALL, ""); keep later tests' strftime unaffected.
    saved = locale.setlocale(locale.LC_ALL)
    app = QCoreApplication.instance() or QCoreApplication([])
    locale.setlocale(locale.LC_ALL, saved)
    return app


@pytest.fixture
def acceptors(qapp, tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    init_db(path)
    db = DatabaseManager(db_path=path)
    acceptors = FakeAcceptors()
    monkeypatch.setattr(payment_module, 'DatabaseManager', lambda *a, **k: db)
    monkeypatch.setattr(payment_module, 'get_persistent_gpio', lambda: acceptors)
    yield acceptors
    db.close()


@pytest.fixture
def model(acceptors, monkeypatch):
    model = PaymentModel(main_app=None)
    monkeypatch.setattr(model, '_auto_complete_payment', lambda: None)
    return model


def start_payment(model, total_cost=100):
    model.total_cost = total_cost
    model.on_enter()


class TestRepeatVisits:
    def test_each_customer_is_credited_each_coin_once(self, model, acceptors):
        for customer in range(3):
            start_payment(model)
            acceptors.coin_inserted.emit(5)
            acceptors.bill_inserted.emit(20)
            assert model.amount_received == 25, f"customer {customer + 1}"
            model.on_leave()

    def test_going_back_and_returning_does_not_double_count(self, model, acceptors):
        start_payment(model)
        model.on_leave()  # customer taps Back
        start_payment(model)
        acceptors.coin_inserted.emit(5)
        assert model.amount_received == 5

    def test_acceptor_status_is_relayed_once(self, model, acceptors):
        statuses = []
        model.payment_status_updated.connect(statuses.append)
        for _ in range(3):
            start_payment(model)
            model.on_leave()
        statuses.clear()
        acceptors.payment_status.emit("Bill jammed")
        assert statuses == ["Bill jammed"]

    def test_coins_while_off_the_payment_screen_are_ignored(self, model, acceptors):
        start_payment(model)
        model.on_leave()
        model.disable_payment_mode()
        acceptors.coin_inserted.emit(5)
        assert model.amount_received == 0
