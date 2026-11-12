"""
PrintingSystemApp.on_file_printed starts ink analysis on each printed file's
temporary PDF, and that analysis finishing deletes that PDF. The path is bound
into the callback (it runs on the ink worker thread), so two files in flight
can't delete each other's PDFs. on_print_successful no longer touches either.
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from main_app import PrintingSystemApp  # noqa: E402
from managers.print_items import PrintItem  # noqa: E402

ITEM = PrintItem({'path': '/tmp/scan.pdf'}, [1, 2], copies=3, color_mode='Black and White')
OTHER = PrintItem({'path': '/tmp/other.pdf'}, [1], copies=1, color_mode='Color')


def fake_app(*items):
    app = MagicMock()
    app.current_print_job = {'items': list(items), 'payment_ref': 'ref'}
    app._trigger_ink_analysis = lambda item, path: PrintingSystemApp._trigger_ink_analysis(app, item, path)
    app._on_ink_analysis_completed = lambda op, path: PrintingSystemApp._on_ink_analysis_completed(app, op, path)
    return app


def test_a_printed_file_is_analysed_from_its_temp_pdf():
    app = fake_app(ITEM)

    PrintingSystemApp.on_file_printed(app, 1, '/tmp/printjob-abc.pdf')

    kwargs = app.ink_analysis_threader.analyze_and_update.call_args.kwargs
    assert kwargs['pdf_path'] == '/tmp/printjob-abc.pdf'
    assert kwargs['copies'] == 3
    assert kwargs['color_mode'] == 'Black and White'
    app._update_paper_count_after_print.assert_called_once_with(6)
    app.payment_screen.model.db_manager.set_transaction_file_status.assert_called_once_with('ref', 1, 'printed')
    assert app.current_print_job['printed'] == [1]


def test_success_does_not_analyse_or_clear_paper_again():
    app = fake_app(ITEM)

    PrintingSystemApp.on_print_successful(app)

    app.ink_analysis_threader.analyze_and_update.assert_not_called()
    app._update_paper_count_after_print.assert_not_called()
    assert app.current_print_job is None


def test_analysis_finishing_deletes_only_its_own_temp_pdf():
    app = fake_app(ITEM, OTHER)
    PrintingSystemApp.on_file_printed(app, 2, '/tmp/printjob-two.pdf')
    PrintingSystemApp.on_file_printed(app, 1, '/tmp/printjob-one.pdf')
    first, second = [c.kwargs['callback'] for c in app.ink_analysis_threader.analyze_and_update.call_args_list]

    second({'success': True, 'database_updated': True})
    app.printer_manager.cleanup_temp_pdf.assert_called_once_with('/tmp/printjob-one.pdf')
    first({'success': True, 'database_updated': True})
    app.printer_manager.cleanup_temp_pdf.assert_called_with('/tmp/printjob-two.pdf')
