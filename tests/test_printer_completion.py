"""
PrinterThread.wait_for_print_completion against faked `lpstat` output: a job
only counts as printed once it has left the CUPS queue, and a printer that
reports `paused` (what the HP sends when it stops for missing paper) fails the
job instead of leaving it waiting. Also the thank-you screen's wording for it.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication  # noqa: E402

import managers.printer_thread as pt  # noqa: E402
from managers.printer_thread import PrinterThread, parse_printer_alerts  # noqa: E402

PRINTER = "HP_Smart_Tank_580_590_series_5E0E1D_USB"
JOB = f"{PRINTER}-2"


def lpstat_p(alerts):
    return (f"printer {PRINTER} is idle.  enabled since Thu 15 Oct 2026 17:10:35 HKT\n"
            f"\tAlerts: {alerts}\n"
            "\tDescription: HP Smart Tank 580-590 series\n")


class FakeCups:
    """Answers `lpstat -l -p` and `lpstat -o`; the job stays queued for `queued_polls` polls."""

    def __init__(self, alerts="none", queued_polls=0):
        self.alerts = alerts
        self.queued_polls = queued_polls
        self.queue_polls = 0

    def run(self, cmd, **kwargs):
        if cmd[:2] == ['lpstat', '-o']:
            self.queue_polls += 1
            queued = self.queue_polls <= self.queued_polls
            out = f"{JOB} group-c 3109888 Fri 16 Oct 2026 18:46:04 HKT\n" if queued else ""
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        return SimpleNamespace(returncode=0, stdout=lpstat_p(self.alerts), stderr="")


@pytest.fixture
def thread(monkeypatch):
    monkeypatch.setattr(pt.time, 'sleep', lambda s: None)
    monkeypatch.setattr(pt, 'send_no_paper_sms', lambda: None)
    monkeypatch.setattr(pt, 'send_paper_jam_sms', lambda: None)
    t = PrinterThread("x.pdf", 1, "Black and White", [1], PRINTER)
    t.failures = []
    t.print_failed.connect(t.failures.append)
    return t


class TestParsePrinterAlerts:
    def test_none(self):
        assert parse_printer_alerts(lpstat_p("none")) == []

    def test_several(self):
        assert parse_printer_alerts(lpstat_p("paused media-empty-report")) == ["paused", "media-empty-report"]

    def test_no_alerts_line(self):
        assert parse_printer_alerts(f"printer {PRINTER} is idle.\n") == []


class TestWaitForPrintCompletion:
    def test_paused_printer_fails_the_job(self, thread, monkeypatch):
        cups = FakeCups(alerts="paused", queued_polls=999)
        monkeypatch.setattr(pt.subprocess, 'run', cups.run)

        assert thread.wait_for_print_completion(JOB) is False
        assert len(thread.failures) == 1
        assert "paused" in thread.failures[0]

    def test_not_complete_while_job_is_still_queued(self, thread, monkeypatch):
        cups = FakeCups(alerts="none", queued_polls=20)
        monkeypatch.setattr(pt.subprocess, 'run', cups.run)

        assert thread.wait_for_print_completion(JOB) is True
        # Only finished after the queue stopped listing the job
        assert cups.queue_polls > 20
        assert thread.failures == []

    def test_media_empty_still_reported_as_no_paper(self, thread, monkeypatch):
        cups = FakeCups(alerts="media-empty-error", queued_polls=999)
        monkeypatch.setattr(pt.subprocess, 'run', cups.run)

        assert thread.wait_for_print_completion(JOB) is False
        assert thread.failures == [f"No paper detected on {PRINTER}"]


def test_thank_you_screen_explains_a_paused_printer(monkeypatch):
    QApplication.instance() or QApplication([])
    import utils.error_logger
    monkeypatch.setattr(utils.error_logger, 'log_error', lambda *a, **k: None)
    from screens.thank_you.model import ThankYouModel

    model = ThankYouModel()
    shown = []
    model.status_updated.connect(lambda title, body: shown.append((title, body)))

    model.show_printing_error(f"Printer paused on {PRINTER} (out of paper?)")

    assert model.current_state == "error"
    assert "paused" in shown[-1][1] and "out of paper" in shown[-1][1]
