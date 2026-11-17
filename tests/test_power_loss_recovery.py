# flake8: noqa: F811

"""
Power loss mid-payment (ADR 0011, issue #156): the payment journal, recovery at
startup, and an operator settling what's owed.

A "power cut" is the model simply stopping at some point: nothing after it runs
(no on_leave, no cleanup), and recovery then reads the same temp SQLite file the
payment wrote to, as the next start would. The payment runs for real in
SIM_MODE (real PaymentModel, DispenseThread and simulated hoppers), as in
test_payment_change_flow.py.
"""
import os
import sqlite3

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from fastapi.testclient import TestClient  # noqa: E402

from SSP.admin_dashboard.main import app  # noqa: E402
from admin_dashboard.cli import create_account  # noqa: E402
from admin_dashboard.dependencies import get_db  # noqa: E402
from managers import payment_recovery as recovery  # noqa: E402
from managers.accounting_report import voucher_figures  # noqa: E402
from managers.inventory_edits import TOUCHSCREEN  # noqa: E402
from managers.payment_journal import PaymentJournal, read_entries  # noqa: E402
from managers.print_refund import record_print_success  # noqa: E402
from managers.voucher_manager import VoucherManager  # noqa: E402
from screens.voucher.model import VoucherModel  # noqa: E402
from tests.test_payment_change_flow import (  # noqa: E402,F401
    db, fail_hopper_after, finish, issue_voucher, job, job_cost, kiosk, pay, qapp, sms,
    start_payment, stock_hoppers, wait_for,
)


def journal(db):
    return read_entries(db.conn)


def inventory(db):
    return {(int(i['denomination']), i['type']): i['count'] for i in db.get_cash_inventory()}


def tx_rows(db):
    return db.get_transaction_history()


def owed(db):
    return recovery.owed_payments(db)


def recover(db, **kwargs):
    return recovery.recover_interrupted_payments(db, **kwargs)


def cut_power_after_dispensing(model, monkeypatch):
    """The power goes as the last coin comes out: nothing after the payout runs."""
    model.payout_results = []
    monkeypatch.setattr(model, '_on_dispensing_finished', model.payout_results.append)


def wait_for_payout(model):
    # Until the (cut) handler has had the result, so no queued signal outlives the test
    wait_for(lambda: model.payout_results, "the payout to end")
    model.dispense_thread.wait(5000)


# ---- the journal while paying -------------------------------------------------

class TestJournal:
    def test_each_coin_and_bill_is_on_disk_as_it_is_credited(self, kiosk, db):
        _, model = kiosk
        start_payment(model)
        model.on_coin_inserted(1)
        model.on_coin_inserted(1)
        [entry] = journal(db)
        assert entry['cash_received'] == {1: 2} and entry['payment_ref'] is None
        assert entry['summary']['file_count'] == 1 and entry['source'] == 'usb'

    def test_a_completed_print_leaves_no_journal_row(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 7)
        finish(main_app, model)
        assert journal(db) == []

    def test_carried_credit_keeps_its_row_and_its_voucher_removes_it(self, kiosk, db):
        main_app, model = kiosk
        start_payment(model)
        model.on_coin_inserted(1)
        model.on_leave()                       # Back to print options: Carried Credit
        assert len(journal(db)) == 1
        start_payment(model)                   # payment reopens: the same row
        model.on_coin_inserted(1)
        [entry] = journal(db)
        assert entry['cash_received'] == {1: 2}
        model.on_leave()
        main_app.show_screen('homepage')       # abandoned: a Voucher for the cash
        assert main_app.screens[-1] == 'voucher'
        assert journal(db) == []
        assert [r['status'] for r in tx_rows(db)] == ['cancelled_partial_payment']

    def test_counted_change_coins(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        cut_power_after_dispensing(model, monkeypatch)
        pay_and_cut(main_app, model, 7)
        [entry] = journal(db)
        assert (entry['coins_5_out'], entry['coins_1_out']) == (1, 2)
        assert entry['payment_ref'] == model.payment_ref


def pay_and_cut(main_app, model, change):
    start_payment(model)
    main_app.acceptors.bill_inserted.emit(job_cost() + change)
    wait_for_payout(model)


# ---- recovery ---------------------------------------------------------------

class TestRecoveryWhilePaying:
    def test_cash_put_in_is_owed(self, kiosk, db):
        _, model = kiosk
        start_payment(model)
        model.on_coin_inserted(1)
        before = inventory(db)

        [result] = recover(db)

        assert result['amount_owed'] == 1 and result['stage'] == recovery.STAGE_PAYMENT
        [row] = tx_rows(db)
        assert (row['status'], row['amount_paid'], row['payment_ref']) == ('interrupted', 1, result['payment_ref'])
        assert inventory(db)[(1, 'coin')] == before.get((1, 'coin'), 0) + 1
        assert journal(db) == []
        assert [r['amount_owed'] for r in owed(db)] == [1]

    def test_cut_after_the_change_came_out_owes_all_but_the_coins(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        cut_power_after_dispensing(model, monkeypatch)
        pay_and_cut(main_app, model, 7)

        [result] = recover(db)

        assert result['amount_owed'] == job_cost()
        [row] = tx_rows(db)
        assert (row['status'], row['change_dispensed']) == ('interrupted', 7)
        assert inventory(db)[(1, 'coin')] == 18 and inventory(db)[(5, 'coin')] == 19

    def test_cut_mid_payout_counts_only_the_coins_seen(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 1, 1)   # one P1 out, then the payout stops
        cut_power_after_dispensing(model, monkeypatch)
        pay_and_cut(main_app, model, 7)

        [result] = recover(db)

        assert result['amount_owed'] == job_cost() + 1  # P5 + P1 of P7 came out

    def test_voucher_value_applied_is_owed_too(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        stock_hoppers(db, ones=20, fives=20)
        start_payment(model)
        assert model.apply_voucher(code)
        cut_power_after_dispensing(model, monkeypatch)
        main_app.acceptors.bill_inserted.emit(job_cost() - 2 + 5)
        wait_for_payout(model)

        [result] = recover(db)

        assert result['amount_owed'] == job_cost()   # (cost - 2 + 5) cash + 2 Voucher - 5 change

    def test_a_payment_with_nothing_put_in_owes_nothing(self, kiosk, db):
        PaymentJournal(db.db_path).record('j1', {}, 10, job())
        assert recover(db) == []
        assert journal(db) == [] and tx_rows(db) == []


class TestRecoveryWhilePrinting:
    def test_settled_print_cut_off_is_owed_and_print_jobs_are_cancelled(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 3)          # settled `paid`, the print never reports back
        before = inventory(db)
        cancelled = []

        [result] = recover(db, cancel_print_jobs=lambda: cancelled.append(True))

        assert cancelled == [True]
        assert (result['stage'], result['amount_owed']) == (recovery.STAGE_PRINTING, job_cost())
        [row] = tx_rows(db)
        assert row['status'] == 'interrupted'
        assert inventory(db) == before   # counted at settlement already
        assert [f['status'] for f in db.get_transaction_files(model.payment_ref)] == ['not_printed']

    def test_only_unprinted_files_are_owed(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 0)
        db.conn.execute("UPDATE transaction_files SET cost = 3 WHERE payment_ref = ?", (model.payment_ref,))
        db.conn.execute("INSERT INTO transaction_files (payment_ref, position, file_name, pages, copies, "
                        "color_mode, cost, status) VALUES (?, 2, 'b.pdf', 1, 1, 'Color', 5, 'printed')",
                        (model.payment_ref,))
        db.conn.commit()

        [result] = recover(db)

        assert result['amount_owed'] == 3

    def test_outcome_already_recorded_owes_nothing(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 0)
        # The outcome was saved, the cut came before the journal row was cleared
        db.update_transaction_outcome(model.payment_ref, 'completed', from_status='paid')
        cancelled = []

        assert recover(db, cancel_print_jobs=lambda: cancelled.append(True)) == []

        assert cancelled == [] and journal(db) == [] and owed(db) == []
        assert tx_rows(db)[0]['status'] == 'completed'


class TestRecoveryConverges:
    def test_running_it_again_changes_nothing(self, kiosk, db):
        _, model = kiosk
        start_payment(model)
        model.on_coin_inserted(1)
        recover(db)
        state = (inventory(db), [dict(r) for r in tx_rows(db)], owed(db))

        assert recover(db) == []
        assert (inventory(db), [dict(r) for r in tx_rows(db)], owed(db)) == state

    def test_a_recovery_cut_halfway_leaves_nothing_and_the_next_one_finishes(self, kiosk, db, monkeypatch):
        _, model = kiosk
        start_payment(model)
        model.on_coin_inserted(1)
        before = inventory(db)

        def power_cut(*args, **kwargs):
            raise sqlite3.OperationalError("power cut")
        monkeypatch.setattr(db, 'adjust_cash_inventory', power_cut)
        logged = []
        monkeypatch.setattr(recovery, '_log_error', logged.append)   # not the real kiosk DB
        assert recover(db) == []
        assert len(logged) == 1
        assert tx_rows(db) == [] and owed(db) == [] and inventory(db) == before
        assert len(journal(db)) == 1
        monkeypatch.undo()

        [result] = recover(db)
        assert result['amount_owed'] == 1 and len(tx_rows(db)) == 1
        assert inventory(db)[(1, 'coin')] == before.get((1, 'coin'), 0) + 1


# ---- alerts and the startup flag ------------------------------------------------

class TestAlertsAndStartup:
    def test_each_interrupted_payment_is_alerted_once_without_a_code(self, kiosk, db):
        _, model = kiosk
        start_payment(model)
        model.on_coin_inserted(1)
        recover(db)
        logged, texts = [], []

        sent = recovery.send_pending_alerts(db, log_error=lambda *a: logged.append(a), send_sms=texts.append)
        again = recovery.send_pending_alerts(db, log_error=lambda *a: logged.append(a), send_sms=texts.append)

        assert (sent, again) == (1, 0)
        assert len(logged) == 1 and logged[0][0] == recovery.ERROR_TYPE
        assert "P1 owed" in texts[0]

    def test_unclean_exit_is_reported_until_a_clean_one(self, db, monkeypatch):
        monkeypatch.setattr(recovery, 'send_pending_alerts', lambda db: 0)
        assert recovery.startup_recovery(db, sim_mode=True) is False   # first run ever
        assert recovery.startup_recovery(db, sim_mode=True) is True    # no clean exit since
        recovery.mark_clean_exit(db)
        assert recovery.startup_recovery(db, sim_mode=True) is False


# ---- settling ---------------------------------------------------------------------

@pytest.fixture
def one_owed(kiosk, db, monkeypatch):
    import managers.voucher_manager as vm
    monkeypatch.setattr(vm, '_generate_qr_bytes', lambda payload: payload.encode())
    _, model = kiosk
    start_payment(model)
    model.on_coin_inserted(1)
    model.on_coin_inserted(5)
    recover(db)
    [row] = owed(db)
    return row


def audit(db):
    rows, _ = db.get_admin_action_page(100)
    return [(r['action'], r['new_value']) for r in rows]


class TestSettling:
    def test_issue_voucher_once_even_if_tapped_twice(self, db, one_owed):
        voucher = recovery.settle_with_voucher(db, one_owed['id'], TOUCHSCREEN)

        assert voucher.value == 6
        assert recovery.settle_with_voucher(db, one_owed['id'], TOUCHSCREEN) is None
        assert recovery.settle_in_cash(db, one_owed['id'], TOUCHSCREEN) is False
        assert owed(db) == []
        assert VoucherManager(db).balance(voucher.code).remaining == 6
        assert tx_rows(db)[0]['voucher_issued'] == 6
        assert audit(db) == [(recovery.ACTION_INTERRUPTED, "voucher issued")]

    def test_a_voucher_that_cant_be_saved_leaves_it_owed(self, db, one_owed):
        class Broken:
            def issue(self, *args, **kwargs):
                raise RuntimeError("disk full")

        with pytest.raises(RuntimeError):
            recovery.settle_with_voucher(db, one_owed['id'], TOUCHSCREEN, voucher_manager=Broken())

        assert [r['id'] for r in owed(db)] == [one_owed['id']]
        assert tx_rows(db)[0]['voucher_issued'] == 0

    def test_refunded_in_cash(self, db, one_owed):
        assert recovery.settle_in_cash(db, one_owed['id'], TOUCHSCREEN) is True
        assert owed(db) == []
        assert audit(db) == [(recovery.ACTION_INTERRUPTED, "refunded in cash")]

    def test_owed_counts_in_the_accounting_figures_until_settled(self, db, one_owed):
        assert voucher_figures(db, None)['interrupted_owed'] == 6
        recovery.settle_in_cash(db, one_owed['id'], TOUCHSCREEN)
        assert voucher_figures(db, None)['interrupted_owed'] == 0

    def test_voucher_screen_wording(self, db, one_owed):
        model = VoucherModel()
        model.set_voucher(recovery.settle_with_voucher(db, one_owed['id'], TOUCHSCREEN),
                          reason=VoucherModel.INTERRUPTED)
        assert model.title() == "Here's your refund voucher"
        assert "restarted during your payment" in model.body() and "₱6" in model.body()


class TestDashboard:
    @pytest.fixture
    def client(self, db):
        app.dependency_overrides[get_db] = lambda: db
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_db, None)

    def login(self, client, db, role):
        client.cookies.clear()
        create_account(db, role, "s3cret!", role)
        client.post("/login", json={"username": role, "password": "s3cret!"})

    def test_kiosk_page_lists_it_and_only_admin_can_mark_it_refunded(self, client, db, one_owed):
        self.login(client, db, "operator")
        page = client.get("/kiosk").text
        assert "Owed on interrupted payments (1)" in page and "Refunded in cash" not in page
        url = f"/kiosk/owed/{one_owed['id']}/refunded-in-cash"
        assert client.post(url).status_code == 403

        self.login(client, db, "admin")
        assert client.post(url).status_code == 200
        assert client.post(url).status_code == 409
        assert owed(db) == []
        assert "Owed on interrupted payments" not in client.get("/kiosk").text
        assert client.get("/accounting/data?range=all").json()['vouchers']['interrupted_owed'] == 0
