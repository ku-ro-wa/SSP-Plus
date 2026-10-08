"""
End-to-end SIM_MODE tests for change dispensing, Shortfalls and Vouchers:
a real PrintOptionsModel prices a real PDF, a real PaymentModel takes the
payment, auto-completes, dispenses change on the real DispenseThread
(simulated ChangeDispenser), shows the real VoucherController (offscreen),
and logs the transaction to a temp SQLite DB.

Only the edges are faked: the coin/bill acceptor (a per-test stand-in for the
persistent_gpio singleton, which would otherwise outlive each PaymentModel),
main_app (screen navigation, paper check, the global countdown label), the
per-coin hopper call (ChangeDispenser._dispense_coin) when a test needs a
hopper to fail, QR image rendering, and the operator SMS send.
"""
import locale
import os
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import managers.hopper_manager as hm  # noqa: E402
import managers.voucher_manager as vm  # noqa: E402
import screens.payment.model as payment_module  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.voucher_manager import VoucherManager  # noqa: E402
from screens.payment.model import PaymentModel, ShortfallCause  # noqa: E402
from screens.print_options.model import PrintOptionsModel  # noqa: E402
from screens.voucher.controller import VoucherController  # noqa: E402

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


class FakeMainApp:
    def __init__(self):
        self.admin_screen = FakeAdminScreen()
        self.db_threader = None
        self.screens = []
        self.countdown = None
        self.payment_screen = SimpleNamespace(model=None)
        self.voucher_screen = VoucherController(self)

    def show_screen(self, name):
        # Like PrintingSystemApp.show_screen: leave, start the 60s countdown, enter.
        if self.screens and self.screens[-1] == 'voucher':
            self.voucher_screen.on_leave()
        self.screens.append(name)
        self.countdown = 60
        if name == 'voucher':
            self.voucher_screen.on_enter()

    def start_global_countdown(self, seconds=60):
        self.countdown = seconds

    def stop_global_countdown(self):
        self.countdown = None


@pytest.fixture(scope='module')
def qapp():
    # Constructing a Q(Core)Application calls setlocale(LC_ALL, ""), which would
    # localise strftime output (e.g. %B) for every test that runs after this one.
    saved = locale.setlocale(locale.LC_ALL)
    app = QApplication.instance() or QApplication([])
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
    monkeypatch.setattr(payment_module, 'send_operator_alert', sent.append)
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
    main_app.payment_screen.model = model
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


def wait_for(condition, what):
    deadline = time.time() + 10
    while not condition():
        assert time.time() < deadline, f"timed out waiting for {what}"
        QApplication.processEvents()
        time.sleep(0.01)


def pay(main_app, model, change):
    """print_options -> payment -> auto-complete -> dispense, as on the kiosk.
    Returns once the voucher or thank-you screen is showing."""
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    payment_data = options.get_payment_data()
    payment_data['source'] = 'usb'  # what PrintOptionsController adds

    model.set_payment_data(payment_data)
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(int(payment_data['total_cost'] + change))
    wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")
    return payment_data


def displayed(main_app):
    """What the voucher screen is showing right now (None if it isn't)."""
    if main_app.screens[-1] != 'voucher':
        return None
    view = main_app.voucher_screen.view
    return SimpleNamespace(
        title=view.title_label.text(),
        code=view.code_label.text(),
        code_visible=not view.code_row.isHidden(),
        qr=main_app.voucher_screen.model.qr_bytes,
    )


def finish(main_app, model):
    """Customer taps "I've saved it" if the voucher screen is up; the print succeeds."""
    if main_app.screens[-1] == 'voucher':
        main_app.voucher_screen.view.continue_button.click()
    assert main_app.screens[-1] == 'thank_you'
    model.log_transaction_after_print_success()  # main_app does this once the print succeeds


def pay_with_change(main_app, model, change):
    payment_data = pay(main_app, model, change)
    shown = displayed(main_app)
    finish(main_app, model)
    return payment_data, shown


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
        assert model.outcome.cause is None
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
        assert model.outcome.cause is ShortfallCause.HOPPER_FAILURE

    def test_low_inventory_is_a_predicted_shortfall(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)

        pay_with_change(main_app, model, 10)

        row = logged_row(db)
        assert (row['change_given'], row['change_dispensed']) == (10, 3)
        assert model.outcome.cause is ShortfallCause.PREDICTED

    def test_revenue_is_still_the_job_price(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        payment_data, _ = pay_with_change(main_app, model, 10)

        summary = {r['source']: r for r in db.get_accounting_summary()}
        assert summary['usb']['revenue'] == payment_data['total_cost']


def voucher_rows(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM vouchers")]
    finally:
        conn.close()


class TestVoucherForShortfall:
    def test_short_hoppers_issue_a_voucher_for_exactly_the_shortfall(self, kiosk, db, sms):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)

        _, shown = pay_with_change(main_app, model, 10)

        assert main_app.screens == ['voucher', 'thank_you']
        assert shown.code_visible
        [voucher] = voucher_rows(db.db_path)
        assert (voucher['initial_value'], voucher['remaining_value']) == (7, 7)
        issued_at = datetime.fromisoformat(voucher['created_at'])
        assert datetime.fromisoformat(voucher['expires_at']) == issued_at + timedelta(days=30)
        row = logged_row(db)
        assert (row['change_dispensed'], row['voucher_issued']) == (3, 7)
        assert voucher['payment_ref'] == row['payment_ref']

        balance = VoucherManager(db).balance(shown.code)
        assert (balance.success, balance.remaining) == (True, 7)
        assert sms == []  # predicted Shortfall: no operator alert

    def test_qr_payload_is_the_tagged_code_without_a_hyphen(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        _, shown = pay_with_change(main_app, model, 4)

        assert shown.qr == ("V1:" + shown.code.replace("-", "")).encode()
        assert len(shown.code.replace("-", "")) == 8

    def test_voucher_value_is_the_shortfall_not_the_change(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 5, 1)  # one ₱5, then the ₱5 hopper jams
        statuses = []
        model.payment_status_updated.connect(statuses.append)

        pay_with_change(main_app, model, 11)  # ₱5 + six ₱1 top-up => all ₱11 comes out

        assert voucher_rows(db.db_path) == []
        assert logged_row(db)['change_dispensed'] == 11
        assert not any(s.startswith("Change dispensing failed") for s in statuses)  # all change came out

    def test_hopper_failure_shortfall_alerts_the_operator(self, kiosk, db, sms, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 1, 1)

        _, shown = pay_with_change(main_app, model, 8)

        assert voucher_rows(db.db_path)[0]['initial_value'] == 2
        assert len(sms) == 1
        assert "hopper" in sms[0].lower() and "P2" in sms[0]
        assert shown.code.replace("-", "") not in sms[0]

    def test_full_change_sends_no_alert_and_shows_no_voucher(self, kiosk, db, sms):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)

        pay_with_change(main_app, model, 13)

        assert sms == []
        assert main_app.screens == ['thank_you']


class TestVoucherSaveFailure:
    def test_shows_no_code_logs_and_alerts(self, kiosk, db, sms, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)
        monkeypatch.setattr(db, 'create_voucher', lambda **kwargs: False)

        _, shown = pay_with_change(main_app, model, 10)

        assert not shown.code_visible and shown.code == ""
        assert shown.qr is None
        assert "couldn't issue" in shown.title.lower()
        assert voucher_rows(db.db_path) == []
        assert [e['error_type'] for e in db.get_error_log()] == ["Voucher Issue Failed"]
        assert len(sms) == 1 and "P7" in sms[0]
        assert logged_row(db)['voucher_issued'] == 0


class TestVoucherScreenTiming:
    def test_shows_a_three_minute_countdown(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        pay(main_app, model, 4)

        screen = main_app.voucher_screen
        assert main_app.countdown == 180
        assert screen.timeout_timer.isActive()
        assert screen.timeout_timer.interval() == 180_000
        finish(main_app, model)

    def test_timeout_continues_to_thank_you_and_keeps_the_voucher(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)
        pay(main_app, model, 4)
        code = main_app.voucher_screen.view.code_label.text()

        main_app.voucher_screen.timeout_timer.start(1)  # fast-forward the 3 minutes
        wait_for(lambda: main_app.screens[-1] == 'thank_you', "the voucher screen to time out")

        assert main_app.voucher_screen.view.code_label.text() == ""  # code wiped on leave
        assert VoucherManager(db).balance(code).remaining == 4


# ---- Applying Vouchers at payment ------------------------------------------

def job(source='usb'):
    """payment_data for a 1-page B&W job, as PrintOptionsController builds it."""
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    payment_data = options.get_payment_data()
    payment_data['source'] = source
    return payment_data


def job_cost():
    return int(job()['total_cost'])


def start_payment(model, source='usb'):
    model.set_payment_data(job(source))
    model.on_enter()


def issue_voucher(main_app, model, db, value):
    """A real Voucher worth `value`, issued by overpaying with empty hoppers.
    Leaves the kiosk ready for the next customer; returns the shown code."""
    stock_hoppers(db, ones=0, fives=0)
    _, shown = pay_with_change(main_app, model, value)
    assert shown.code_visible
    main_app.screens.clear()
    return shown.code


def finish_with_cash(main_app, model, amount):
    if amount:
        main_app.acceptors.bill_inserted.emit(amount)
    wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")
    finish(main_app, model)


def row_for(db, payment_ref):
    [row] = [r for r in db.get_transaction_history() if r['payment_ref'] == payment_ref]
    return row


def applications(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM voucher_applications ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture
def messages(kiosk):
    _, model = kiosk
    seen = []
    model.voucher_message.connect(lambda message, is_error: seen.append((message, is_error)))
    return seen


class TestApplyVoucherAtPayment:
    @pytest.mark.parametrize('source', ['usb', 'wifi', 'email', 'scanner'])
    def test_issued_voucher_plus_cash_end_to_end(self, kiosk, db, source):
        main_app, model = kiosk
        cost = job_cost()
        assert cost > 2
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model, source)
        assert model.apply_voucher(code)
        assert model.amount_owed == cost - 2
        stock_hoppers(db, ones=20, fives=20)
        finish_with_cash(main_app, model, cost - 2)

        assert main_app.screens == ['thank_you']  # exact payment: no change, no new voucher
        ref = model.payment_ref
        row = row_for(db, ref)
        assert (row['voucher_applied'], row['amount_paid'], row['change_given']) == (2, cost - 2, 0)
        assert row['source'] == source
        [link] = applications(db.db_path)
        assert (link['amount'], link['payment_ref']) == (2, ref)
        assert voucher_rows(db.db_path)[0]['remaining_value'] == 0
        assert VoucherManager(db).balance(code).status == vm.LookupStatus.USED

    def test_vouchers_covering_the_cost_need_no_cash(self, kiosk, db):
        main_app, model = kiosk
        cost = job_cost()
        code = issue_voucher(main_app, model, db, cost + 2)

        start_payment(model)
        assert model.apply_voucher("V1:" + code.replace("-", ""))  # the QR payload form
        assert [(v.amount, v.remaining) for v in model.applied_vouchers] == [(cost, 2)]
        finish_with_cash(main_app, model, 0)

        row = row_for(db, model.payment_ref)
        assert (row['voucher_applied'], row['amount_paid'], row['change_given']) == (cost, 0, 0)
        assert VoucherManager(db).balance(code).remaining == 2

    def test_several_vouchers_are_used_in_order_and_only_the_last_is_partial(self, kiosk, db):
        main_app, model = kiosk
        cost = job_cost()
        first = issue_voucher(main_app, model, db, cost - 1)
        second = issue_voucher(main_app, model, db, 5)

        start_payment(model)
        assert model.apply_voucher(first)
        assert model.apply_voucher(second)
        assert [(v.amount, v.remaining) for v in model.applied_vouchers] == [(cost - 1, 0), (1, 4)]
        finish_with_cash(main_app, model, 0)

        assert [a['amount'] for a in applications(db.db_path)] == [cost - 1, 1]
        assert row_for(db, model.payment_ref)['voucher_applied'] == cost
        assert VoucherManager(db).balance(first).status == vm.LookupStatus.USED
        assert VoucherManager(db).balance(second).remaining == 4

    def test_overpaying_with_voucher_and_cash_gives_change_and_vouchers_the_shortfall(self, kiosk, db):
        main_app, model = kiosk
        cost = job_cost()
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model)
        model.apply_voucher(code)
        stock_hoppers(db, ones=2, fives=0)  # can give ₱2 of the ₱7 change
        main_app.acceptors.bill_inserted.emit(cost - 2 + 7)
        wait_for(lambda: 'voucher' in main_app.screens, "the new voucher")
        new_code = displayed(main_app).code
        finish(main_app, model)

        row = row_for(db, model.payment_ref)
        assert (row['voucher_applied'], row['change_given'], row['change_dispensed'], row['voucher_issued']) \
            == (2, 7, 2, 5)
        assert VoucherManager(db).balance(new_code).remaining == 5

    def test_cancelling_leaves_the_voucher_untouched(self, kiosk, db):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model)
        model.apply_voucher(code)
        model.go_back()

        assert model.applied_vouchers == []
        assert applications(db.db_path) == []
        assert VoucherManager(db).balance(code).remaining == 2

    def test_same_voucher_twice_is_applied_once(self, kiosk, db, messages):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model)
        assert model.apply_voucher(code)
        assert not model.apply_voucher(code.lower())
        assert model.voucher_total == 2
        assert "already applied" in messages[-1][0]

    def test_failed_apply_takes_nothing_and_lets_the_customer_pay_cash(self, kiosk, db, messages, monkeypatch):
        main_app, model = kiosk
        cost = job_cost()
        code = issue_voucher(main_app, model, db, 2)
        stock_hoppers(db, ones=20, fives=20)

        start_payment(model)
        model.apply_voucher(code)
        monkeypatch.setattr(db, 'apply_vouchers', lambda *a: False)
        main_app.acceptors.bill_inserted.emit(cost - 2)
        wait_for(lambda: messages[-1][1], "the apply failure")

        assert main_app.screens == []
        assert model.payment_ready and model.applied_vouchers == []
        assert "pay the rest in cash" in messages[-1][0]
        assert VoucherManager(db).balance(code).remaining == 2
        finish_with_cash(main_app, model, 2)
        row = row_for(db, model.payment_ref)
        assert (row['voucher_applied'], row['amount_paid']) == (0, cost)


class TestVoucherEntryMessages:
    def test_expired_used_and_unknown_codes_get_distinct_messages(self, kiosk, db, messages):
        import sqlite3
        main_app, model = kiosk
        expired = issue_voucher(main_app, model, db, 2)
        conn = sqlite3.connect(db.db_path)
        conn.execute("UPDATE vouchers SET expires_at = ?", (datetime.now() - timedelta(days=1),))
        conn.commit()
        conn.close()
        used = issue_voucher(main_app, model, db, job_cost())
        start_payment(model)
        model.apply_voucher(used)
        finish_with_cash(main_app, model, 0)
        main_app.screens.clear()

        start_payment(model)
        messages.clear()
        for code in (expired, used, "ZZZZ-ZZZZ"):
            assert not model.apply_voucher(code)
        texts = [m for m, _ in messages]
        assert all(is_error for _, is_error in messages)
        assert "expired" in texts[0]
        assert "fully used" in texts[1]
        assert texts[2] == vm.MSG_UNKNOWN
        assert len(set(texts)) == 3
        assert not any("redeem" in t.lower() for t in texts)

    def test_wrong_codes_lock_entry_and_show_the_cooldown(self, kiosk, db, messages):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        start_payment(model)

        for _ in range(vm.MAX_FAILED_ATTEMPTS):
            model.apply_voucher("ZZZZ-ZZZZ")
        assert "locked for 5 more minute" in messages[-1][0]
        assert not model.apply_voucher(code)  # even the right code, until the cooldown ends
        assert "locked" in messages[-1][0]
        assert model.applied_vouchers == []

    def test_malformed_entry_does_not_count_toward_the_lockout(self, kiosk, db, messages):
        main_app, model = kiosk
        start_payment(model)
        for _ in range(vm.MAX_FAILED_ATTEMPTS + 1):
            model.apply_voucher("hello")
        assert all("locked" not in m for m, _ in messages)


class TestVoucherEntryOnScreen:
    def test_typed_code_is_applied_and_listed_with_what_is_left(self, kiosk, db):
        from screens.payment.controller import PaymentController
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        screen.set_payment_data(job())
        screen.on_enter()
        view = screen.view
        try:
            assert view.voucher_input.isHidden()
            view.use_voucher_btn.click()
            assert not view.voucher_input.isHidden()
            view.voucher_input.setText(code.lower())
            view.apply_voucher_btn.click()

            assert view.voucher_input.text() == ""  # the code isn't left on screen
            assert view.vouchers_label.text() == f"Voucher ••••-{code[-4:]}: P2 applied, P0 left"
            assert code not in view.vouchers_label.text()
            assert screen.model.amount_owed == job_cost() - 2
            assert "Use a voucher" == view.use_voucher_btn.text()
        finally:
            screen.on_leave()

    def test_code_typed_on_the_keypad_is_applied(self, kiosk, db):
        from screens.payment.controller import PaymentController
        from ui.widgets import BACKSPACE_KEY
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        screen.set_payment_data(job())
        screen.on_enter()
        view = screen.view
        try:
            assert view.voucher_keypad.isHidden()
            view.use_voucher_btn.click()
            assert not view.voucher_keypad.isHidden()
            # Every code character has a key; a slip is fixed with backspace.
            assert set(view.voucher_keypad.key_buttons) == set(vm.CODE_ALPHABET) | {BACKSPACE_KEY}
            keys = view.voucher_keypad.key_buttons
            chars = code.replace("-", "")  # no hyphen key: it's optional when typing
            keys[chars[0]].click()
            keys["Z" if chars[1] != "Z" else "Y"].click()
            keys[BACKSPACE_KEY].click()
            for ch in chars[1:]:
                keys[ch].click()
            assert view.voucher_input.text() == chars
            view.apply_voucher_btn.click()

            assert view.vouchers_label.text() == f"Voucher ••••-{code[-4:]}: P2 applied, P0 left"
            assert screen.model.amount_owed == job_cost() - 2
        finally:
            screen.on_leave()
