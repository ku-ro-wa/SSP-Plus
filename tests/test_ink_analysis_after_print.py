"""
PrintingSystemApp.on_print_successful starts ink analysis on the temp PDF that
was printed, before it clears current_print_job (which analysis reads), and
analysis finishing deletes that temp PDF. Clearing the job first skipped
analysis on every print and left the temp PDF behind.
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from main_app import PrintingSystemApp  # noqa: E402

JOB = {'file_path': '/tmp/scan.pdf', 'selected_pages': [1, 2], 'copies': 3, 'color_mode': 'Black and White'}


def fake_app():
    app = MagicMock()
    app.current_print_job = dict(JOB)
    app.printer_manager.last_temp_pdf_path = '/tmp/printjob-abc.pdf'
    app._trigger_ink_analysis = lambda: PrintingSystemApp._trigger_ink_analysis(app)
    app._on_ink_analysis_completed = lambda op: PrintingSystemApp._on_ink_analysis_completed(app, op)
    return app


def test_print_success_analyses_the_printed_temp_pdf():
    app = fake_app()

    PrintingSystemApp.on_print_successful(app)

    app.ink_analysis_threader.analyze_and_update.assert_called_once()
    kwargs = app.ink_analysis_threader.analyze_and_update.call_args.kwargs
    assert kwargs['pdf_path'] == '/tmp/printjob-abc.pdf'
    assert kwargs['copies'] == 3
    assert kwargs['color_mode'] == 'Black and White'
    assert app.current_print_job is None


def test_analysis_finishing_deletes_the_temp_pdf():
    app = fake_app()
    PrintingSystemApp.on_print_successful(app)
    callback = app.ink_analysis_threader.analyze_and_update.call_args.kwargs['callback']

    callback({'success': True, 'database_updated': True})

    app.printer_manager.cleanup_last_temp_pdf.assert_called_once()
