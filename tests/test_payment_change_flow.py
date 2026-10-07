"""
End-to-end SIM_MODE tests for change dispensing, Shortfalls and Vouchers:
a real PrintOptionsModel prices a real PDF, a real PaymentModel takes the
payment, auto-completes, dispenses change on the real DispenseThread
(simulated ChangeDispenser), and logs the transaction to a temp SQLite DB.

Only the edges are faked: the coin/bill acceptor (a per-test stand-in for the
persistent_gpio singleton, which would otherwise outlive each PaymentModel),
main_app (screen navigation, paper check, the voucher screen widget, which here
wraps the real VoucherModel), the per-coin hopper call
(ChangeDispenser._dispense_coin) when a test needs a hopper to fail, and the
operator SMS send.
"""
import locale
import os
import time

import pytest
from PyQt5.QtCore import QCoreApplication, QObject, pyqtSignal

import managers.hopper_manager as hm
import managers.voucher_manager as vm
import screens.payment.model as payment_module
from database.db_manager import DatabaseManager
from database.models import init_db
from screens.payment.model import PaymentModel
from screens.print_options.model import PrintOptionsModel
from screens.voucher.model import VoucherModel

PDF = os.path.join(os.path.dirname(__file__), '..', 'test_pdfs', 'Rootlocus-Plotting-1.pdf')


class FakeAcceptors(QObject):
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)

    def enable_payment(self):
        pass

    def disable_payment(self):
        pass

    def process_coin_timeout(self):
        pass


class FakeAdminScreen:
    def check_paper_availability(self, pages):
        return True


class FakeVoucherScreen:
    """Stands in for VoucherController (a QWidget); keeps the real VoucherModel."""

    def __init__(self):
        self.model = VoucherModel()
        self.shown = None

    def show_issued(self, voucher):
        self.shown = 'issued'
        self.model.set_voucher(voucher)

    def show_failure(self, amount):
        self.shown = 'failed'
        self.model.set_failure(amount)


class FakeMainApp:
    def __init__(self):
        self.admin_screen = FakeAdminScreen()
        self.voucher_screen = FakeVoucherScreen()
        self.db_threader = None
        self.screens = []

    def show_screen(self, name):
        self.screens.append(name)


@pytest.fixture(scope='module')
def qapp():
    # Constructing a QCoreApplication calls setlocale(LC_ALL, ""), which would
    # localise strftime output (e.g. %B) for every test that runs after this one.
    saved = locale.setlocale(locale.LC_ALL)
    app = QCoreApplication.instance() or QCoreApplication([])
    locale.setlocale(locale.LC_ALL, saved)
    return app


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    manager = DatabaseManager(db_path=path)
    yield manager
    manager.close()


@pytest.fixture
def sms(monkeypatch):
    sent = []
    monkeypatch.setattr(payment_module, 'send_operator_alert', sent.append, raising=False)
    return sent


@pytest.fixture
def kiosk(qapp, db, sms, monkeypatch):
    monkeypatch.setenv('SIM_MODE', 'true')
    monkeypatch.setattr(payment_module, 'DatabaseManager', lambda *a, **k: db)
    monkeypatch.setattr(payment_module, 'log_error', db.log_error)
    acceptors = FakeAcceptors()
    monkeypatch.setattr(payment_module, 'get_persistent_gpio', lambda: acceptors)
    monkeypatch.setattr(hm, 'SIM_COIN_SECONDS', 0)
    monkeypatch.setattr(vm, '_generate_qr_bytes', lambda payload: payload.encode())
    main_app = FakeMainApp()
    main_app.acceptors = acceptors
    model = PaymentModel(main_app)
    model.change_dispenser.simulated = True
    yield main_app, model
    model.on_leave()


def stock_hoppers(db, ones, fives):
    db.update_cash_inventory(denomination=1, count=ones, type='coin')
    db.update_cash_inventory(denomination=5, count=fives, type='coin')


def fail_hopper_after(model, monkeypatch, denomination, n):
    dispenser = model.change_dispenser
    real = dispenser._dispense_coin
    count = {'n': 0}

    def coin(denom):
        if denom == denomination:
            count['n'] += 1
            if count['n'] > n:
                return False
        return real(denom)
    monkeypatch.setattr(dispenser, '_dispense_coin', coin)


def pay_with_change(main_app, model, change):
    """print_options -> payment -> auto-complete -> dispense, as on the kiosk."""
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    payment_data = options.get_payment_data()
    payment_data['source'] = 'usb'  # what PrintOptionsController adds

    model.set_payment_data(payment_data)
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(int(payment_data['total_cost'] + change))

    deadline = time.time() + 10
    while not ({'voucher', 'thank_you'} & set(main_app.screens)):
        assert time.time() < deadline, "payment never finished"
        QCoreApplication.processEvents()
        time.sleep(0.01)
    if 'voucher' in main_app.screens:
        model.continue_to_thank_you()  # the customer taps "I've saved it"
    model.log_transaction_after_print_success()  # main_app does this once the print succeeds
    return payment_data


def logged_row(db):
    rows = db.get_transaction_history()
    assert len(rows) == 1
    return rows[0]


class TestChangeActuallyDispensed:
    def test_full_change_is_recorded_with_no_shortfall(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)

        pay_with_change(main_app, model, 13)

        row = logged_row(db)
        assert (row['change_given'], row['change_dispensed'], row['voucher_issued']) == (13, 13, 0)
        assert model.shortfall_cause is None
        assert main_app.screens == ['thank_you']

    def test_hopper_failure_after_n_coins_records_what_came_out(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 1, 1)

        pay_with_change(main_app, model, 8)  # one ₱5 + one ₱1 come out, the second ₱1 jams

        row = logged_row(db)
        assert row['change_given'] == 8
        assert row['change_dispensed'] == 6
        assert row['change_given'] - row['change_dispensed'] == 2
        assert model.shortfall_cause == 'hopper_failure'

    def test_low_inventory_is_a_predicted_shortfall(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)

        pay_with_change(main_app, model, 10)

        row = logged_row(db)
        assert (row['change_given'], row['change_dispensed']) == (10, 3)
        assert model.shortfall_cause == 'predicted'

    def test_revenue_is_still_the_job_price(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        payment_data = pay_with_change(main_app, model, 10)

        summary = {r['source']: r for r in db.get_accounting_summary()}
        assert summary['usb']['revenue'] == payment_data['total_cost']
