# flake8: noqa: F811

"""
The print path on the `items` shape (#119 / #123): payment with several items,
Carried Credit, scans, the main_app outcome handlers (full vs partial refund),
and the thank-you screen's timer while the print thread runs.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import main_app as main_app_module  # noqa: E402
from main_app import PrintingSystemApp  # noqa: E402
from managers.print_items import PrintItem  # noqa: E402
from managers.print_refund import record_print_success  # noqa: E402
from screens.thank_you.model import ThankYouModel  # noqa: E402
from screens.voucher.model import VoucherModel  # noqa: E402
from tests.test_payment_change_flow import (  # noqa: E402,F401
    PDF, db, kiosk, qapp, sms, stock_hoppers, wait_for,
)


def two_items():
    return [PrintItem({'path': PDF, 'filename': 'one.pdf'}, [1, 2], copies=1, color_mode="Black and White", cost=4.0),
            PrintItem({'path': PDF, 'filename': 'two.pdf'}, [1], copies=3, color_mode="Color", cost=9.0)]


def two_item_job(source='usb'):
    items = two_items()
    items[1].analysis = {'pricing': {'black_pages_count': 0, 'color_pages_count': 1}}
    items[0].analysis = {'pricing': {'black_pages_count': 2, 'color_pages_count': 0}}
    return {'items': items, 'total_cost': 13.0, 'source': source}


class TestPaymentWithSeveralItems:
    def test_one_row_with_file_count_and_one_file_row_per_item(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        summaries = []
        model.payment_data_updated.connect(summaries.append)
        model.set_payment_data(two_item_job())
        model.on_enter()
        main_app.acceptors.bill_inserted.emit(20)
        wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")

        [row] = db.get_transaction_history()
        assert (row['file_name'], row['pages'], row['copies'], row['color_mode'], row['file_count']) == \
            ('one.pdf +1 more', 5, 1, 'Mixed', 2)
        assert row['status'] == 'paid'
        files = db.get_transaction_files(model.payment_ref)
        assert [(f['position'], f['file_name'], f['pages'], f['copies'], f['cost'], f['status']) for f in files] == [
            (1, 'one.pdf', 2, 1, 4.0, 'pending'), (2, 'two.pdf', 1, 3, 9.0, 'pending')]
        assert [i.file_name for i in main_app.current_print_job['items']] == ['one.pdf', 'two.pdf']
        assert main_app.current_print_job['payment_ref'] == model.payment_ref

        record_print_success(db, model.payment_ref)
        assert db.get_transaction_history()[0]['status'] == 'completed'
        assert {r['source']: r['revenue'] for r in db.get_accounting_summary()}['usb'] == 13.0

    def test_the_summary_says_how_many_files_and_where_they_differ(self, kiosk):
        _, model = kiosk
        summaries = []
        model.payment_data_updated.connect(summaries.append)

        model.set_payment_data(two_item_job())

        assert summaries[0]['document_name'] == "2 files"
        assert summaries[0]['copies'] == "Varies" and summaries[0]['color_mode'] == "Varies"
        assert (summaries[0]['black_pages'], summaries[0]['color_pages']) == (2, 1)

    def test_one_item_summary_is_that_items_values(self, kiosk):
        _, model = kiosk
        summaries = []
        model.payment_data_updated.connect(summaries.append)
        data = two_item_job()
        data['items'] = data['items'][:1]

        model.set_payment_data(data)

        assert (summaries[0]['document_name'], summaries[0]['copies'], summaries[0]['color_mode']) == \
            ("one.pdf", 1, "Black and White")

    def test_paper_check_uses_the_total_sheets(self, kiosk, db):
        main_app, model = kiosk
        seen = []
        main_app.admin_screen.check_paper_availability = lambda pages: seen.append(pages) or True
        model.set_payment_data(two_item_job())
        model.on_enter()
        main_app.acceptors.bill_inserted.emit(20)
        wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")

        assert seen == [2 + 3]


class TestCarriedCreditWithSeveralItems:
    def test_back_and_return_keeps_the_items_and_total(self, kiosk, db):
        main_app, model = kiosk
        data = two_item_job()
        model.set_payment_data(data)
        model.on_enter()
        main_app.acceptors.coin_inserted.emit(5)

        model.go_back()
        model.set_payment_data(data)
        model.on_enter()

        assert model.amount_received == 5
        assert model.payment_data['items'] is data['items'] and model.total_cost == 13.0

    def test_abandoning_it_logs_two_not_printed_file_rows(self, kiosk, db):
        main_app, model = kiosk
        data = two_item_job()
        data['total_cost'] = 50.0   # dearer than the cash put in
        model.set_payment_data(data)
        model.on_enter()
        main_app.acceptors.coin_inserted.emit(5)
        main_app.acceptors.bill_inserted.emit(20)
        model.go_back()

        main_app.show_screen('homepage')

        [row] = db.get_transaction_history()
        assert (row['status'], row['file_count'], row['file_name']) == \
            ('cancelled_partial_payment', 2, 'one.pdf +1 more')
        files = db.get_transaction_files(row['payment_ref'])
        assert [(f['position'], f['status']) for f in files] == [(1, 'not_printed'), (2, 'not_printed')]


class TestScans:
    def _scan_data(self, fee=0, print_job=True):
        item = PrintItem({'path': PDF, 'filename': 'Scan.pdf'}, [1], copies=1 if print_job else 0,
                         color_mode="Black and White" if print_job else 'N/A', cost=2.0 if print_job else 0)
        data = {'items': [item], 'total_cost': item.cost + fee, 'source': 'scanner'}
        if not print_job:
            data['print_job'] = False
        if fee:
            data['digital_copy'] = {'fee': fee}
        return data

    def test_print_plus_digital_keeps_the_fee_out_of_the_file_cost(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        import managers.adapters.scan_adapter as adapter
        monkeypatch.setattr(adapter.ScanAdapter, 'handle_scan',
                            lambda self, path, **k: (True, "ok", SimpleNamespace(otp="123456")))
        model.set_payment_data(self._scan_data(fee=5))
        model.on_enter()
        main_app.acceptors.bill_inserted.emit(20)
        wait_for(lambda: 'scan_result' in main_app.screens, "the OTP screen")

        [row] = db.get_transaction_history()
        assert row['total_cost'] == 7.0 and row['file_count'] == 1
        [f] = db.get_transaction_files(row['payment_ref'])
        assert f['cost'] == 2.0

    def test_digital_only_writes_no_file_rows(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        import managers.adapters.scan_adapter as adapter
        monkeypatch.setattr(adapter.ScanAdapter, 'handle_scan',
                            lambda self, path, **k: (True, "ok", SimpleNamespace(otp="123456")))
        monkeypatch.setattr('screens.payment.model.shutil.rmtree', lambda *a, **k: None)
        model.set_payment_data(self._scan_data(fee=5, print_job=False))
        model.on_enter()
        main_app.acceptors.bill_inserted.emit(5)
        wait_for(lambda: 'scan_result' in main_app.screens, "the OTP screen")

        [row] = db.get_transaction_history()
        assert (row['copies'], row['file_count']) == (0, 1)
        assert db.get_transaction_files(row['payment_ref']) == []


# ---- main_app outcome handlers ---------------------------------------------------

@pytest.fixture
def outcome_app(db, monkeypatch):
    """A PrintingSystemApp stand-in running the real outcome handlers against a real database."""
    import utils.error_logger
    monkeypatch.setattr(utils.error_logger, 'log_error', lambda *a, **k: None)
    monkeypatch.setattr(main_app_module, 'VoucherModel', VoucherModel)
    app = MagicMock()
    app._paper_empty_reported = True   # skips the SMS
    app.payment_screen.model.db_manager = db
    app.stacked_widget.currentWidget.return_value = app.thank_you_screen
    app._refund_failed_print = lambda message: PrintingSystemApp._refund_failed_print(app, message)
    app.on_file_started = lambda p, t: PrintingSystemApp.on_file_started(app, p, t)
    app.on_file_printed = lambda p, path: PrintingSystemApp.on_file_printed(app, p, path)
    return app


def paid_job(db, app, ref="ref1"):
    items = two_items() + [PrintItem({'path': PDF, 'filename': 'three.pdf'}, [1], cost=2.0)]
    db.log_transaction({'file_name': 'one.pdf +2 more', 'pages': 6, 'copies': 1, 'color_mode': 'Mixed',
                        'file_count': 3, 'total_cost': 15.0, 'amount_paid': 15.0, 'change_given': 0,
                        'status': 'paid', 'source': 'usb', 'payment_ref': ref, 'items': items})
    app.current_print_job = {'items': items, 'payment_ref': ref, 'digital_fee_refunded': 0}
    return items


def file_statuses(db, ref="ref1"):
    return [f['status'] for f in db.get_transaction_files(ref)]


def test_failure_before_any_file_printed_is_the_ordinary_full_refund(outcome_app, db):
    paid_job(db, outcome_app)
    PrintingSystemApp.on_file_started(outcome_app, 3, 3)

    PrintingSystemApp.on_print_failed(outcome_app, "No paper")

    row = db.get_transaction_by_ref("ref1")
    assert (row['status'], row['voucher_issued']) == ('print_failed', 15)
    assert file_statuses(db) == ['not_printed', 'not_printed', 'failed']
    reason = outcome_app.voucher_screen.show_issued.call_args.kwargs['reason'] \
        if outcome_app.voucher_screen.show_issued.called else outcome_app.voucher_screen.show_failure.call_args.kwargs['reason']
    assert reason == VoucherModel.REFUND


def test_failure_after_some_files_printed_refunds_the_rest_as_partly_printed(outcome_app, db):
    paid_job(db, outcome_app)
    outcome_app._update_paper_count_after_print = MagicMock()
    outcome_app._trigger_ink_analysis = MagicMock()
    PrintingSystemApp.on_file_started(outcome_app, 3, 3)
    PrintingSystemApp.on_file_printed(outcome_app, 3, "/tmp/printjob-3.pdf")
    PrintingSystemApp.on_file_started(outcome_app, 2, 3)

    PrintingSystemApp.on_print_failed(outcome_app, "No paper")

    row = db.get_transaction_by_ref("ref1")
    assert (row['status'], row['voucher_issued']) == ('partly_printed', 13)   # files 1 and 2: 4 + 9
    assert file_statuses(db) == ['not_printed', 'failed', 'printed']
    outcome_app._update_paper_count_after_print.assert_called_once_with(1)
    kwargs = outcome_app.voucher_screen.show_issued.call_args.kwargs
    assert kwargs['reason'] == VoucherModel.PARTIAL_REFUND and kwargs['file_counts'] == (1, 3)
    assert {r['source']: r['revenue'] for r in db.get_accounting_summary()}['usb'] == 2.0


def test_a_failure_with_no_transaction_does_not_crash(outcome_app):
    outcome_app.current_print_job = None
    PrintingSystemApp.on_print_failed(outcome_app, "boom")
    outcome_app.thank_you_screen.show_printing_error.assert_called_once()


# ---- thank-you timer ---------------------------------------------------------------

class TestThankYouSafetyTimer:
    @pytest.fixture
    def model(self, qapp):
        m = ThankYouModel()
        m.main_app = SimpleNamespace(printer_manager=SimpleNamespace(print_thread=None))
        m.redirects = []
        m.redirect_to_idle.connect(lambda: m.redirects.append(1))
        return m

    def test_does_not_redirect_while_the_print_thread_runs(self, model):
        model.main_app.printer_manager.print_thread = SimpleNamespace(isRunning=lambda: True)

        model._on_timer_timeout()

        assert model.redirects == []
        assert model.redirect_timer.isActive()   # waits another round
        model.redirect_timer.stop()

    def test_redirects_once_the_thread_has_finished(self, model):
        model.main_app.printer_manager.print_thread = SimpleNamespace(isRunning=lambda: False)
        model._on_timer_timeout()
        assert model.redirects == [1]

    def test_redirects_when_there_is_no_thread(self, model):
        model._on_timer_timeout()
        assert model.redirects == [1]

    def test_file_progress_counts_jobs_in_the_customers_order(self, model):
        model.current_state = "waiting"
        shown = []
        model.status_updated.connect(lambda t, b: shown.append(b))

        model._on_file_started(3, 3)   # the first job sent is the last file
        model._on_file_started(2, 3)

        assert shown == ["Printing file 1 of 3", "Printing file 2 of 3"]
        assert model.redirect_timer.isActive()   # restarted for each file
        model.show_waiting_for_print()
        assert shown[-1] == "Printing file 2 of 3"   # print_waiting doesn't overwrite it
        model.redirect_timer.stop()

    def test_a_single_file_shows_no_progress(self, model):
        model.current_state = "waiting"
        shown = []
        model.status_updated.connect(lambda t, b: shown.append(b))

        model._on_file_started(1, 1)
        model.show_waiting_for_print()

        assert shown == ["Your document is being processed."]
        model.redirect_timer.stop()


def test_two_back_and_returns_keep_the_cash_and_a_later_abandon_still_issues_the_voucher(kiosk, db):
    from tests.test_payment_change_flow import (
        VoucherManager, displayed, leave_payment, start_priced_payment)
    main_app, model = kiosk
    start_priced_payment(model)
    main_app.acceptors.coin_inserted.emit(5)

    leave_payment(main_app, model, 'printing_options')      # back, change the job, return
    start_priced_payment(model, 40)
    assert model.amount_received == 5
    leave_payment(main_app, model, 'printing_options')      # and once more
    start_priced_payment(model, 30)
    assert model.amount_received == 5 and model.amount_owed == 25
    assert db.get_transaction_history() == []                # nothing cancelled yet

    leave_payment(main_app, model, 'printing_options')
    main_app.show_screen('homepage')                         # now they walk away

    assert main_app.screens[-1] == 'voucher'
    assert VoucherManager(db).balance(displayed(main_app).code).remaining == 5
    [row] = db.get_transaction_history()
    assert (row['status'], row['voucher_issued']) == ('cancelled_partial_payment', 5)
