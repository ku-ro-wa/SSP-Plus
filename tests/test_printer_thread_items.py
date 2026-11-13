"""
PrinterThread and PrinterManager with several items (#119): one CUPS job per
item, last item first; every temporary PDF built before the first submission;
a failure stops everything and keeps file_printed ahead of print_failed.
"""
import glob
import os
from types import SimpleNamespace

import fitz
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QCoreApplication, QThread  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import managers.printer_manager as pm  # noqa: E402
import managers.printer_thread as pt  # noqa: E402
from managers.print_items import PrintItem  # noqa: E402
from managers.printer_thread import PrinterThread  # noqa: E402

PRINTER = "HP_Smart_Tank_580_590_series_5E0E1D_USB"


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def private_temp_dir(tmp_path, monkeypatch):
    """Temporary PDFs go to a folder the test can inspect."""
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(pt.tempfile, 'tempdir', str(folder))
    monkeypatch.setattr(pt.time, 'sleep', lambda s: None)
    monkeypatch.setattr(pt, 'send_no_paper_sms', lambda: None)
    monkeypatch.setattr(pt, 'send_paper_jam_sms', lambda: None)
    monkeypatch.delenv('SIM_MODE', raising=False)
    return folder


def temp_pdfs(folder):
    return sorted(glob.glob(str(folder / "printjob-*.pdf")))


def make_pdf(path, pages=3):
    doc = fitz.open()
    for number in range(1, pages + 1):
        doc.new_page().insert_text((72, 72), f"Page {number}")
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def items(tmp_path):
    """Three files: B&W x2, Color x1, a page subset."""
    return [
        PrintItem({'path': make_pdf(tmp_path / "a.pdf")}, [1, 2, 3], copies=2, color_mode="Black and White"),
        PrintItem({'path': make_pdf(tmp_path / "b.pdf")}, [1, 2, 3], copies=1, color_mode="Color"),
        PrintItem({'path': make_pdf(tmp_path / "c.pdf")}, [2], copies=3, color_mode="Black and White"),
    ]


class FakeCups:
    """`lp` hands out job ids and records the commands; lpstat answers as the printer
    reports. `fail_job` is the Nth submission (1-based) whose printer reports paper out
    mid-job: the printer waits for paper, so that job stays in the queue (a job that has
    left the queue with the tray empty finished, and counts as printed)."""

    def __init__(self, fail_job=None, on_submit=None):
        self.submitted = []
        self.fail_job = fail_job
        self.on_submit = on_submit
        self.cancelled = []
        self.job = None

    def run(self, cmd, **kwargs):
        if cmd[0] == 'lp':
            self.submitted.append(cmd)
            if self.on_submit:
                self.on_submit(len(self.submitted))
            self.job = f"{PRINTER}-{len(self.submitted)}"
            return SimpleNamespace(returncode=0, stdout=f"request id is {self.job} (1 file(s))\n", stderr="")
        if cmd[0] == 'cancel':
            self.cancelled.append(cmd[1])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == ['lpstat', '-o']:
            stuck = len(self.submitted) == self.fail_job
            return SimpleNamespace(returncode=0, stderr="",
                                   stdout=f"{self.job} group-c 1024 Fri 13 Nov 2026 14:00:00 HKT\n" if stuck else "")
        alerts = "media-empty-error" if len(self.submitted) == self.fail_job else "none"
        return SimpleNamespace(returncode=0, stderr="", stdout=(
            f"printer {PRINTER} is idle.  enabled since Thu 15 Oct 2026 17:10:35 HKT\n"
            f"\tAlerts: {alerts}\n"))


def record(thread):
    events = []
    thread.file_started.connect(lambda p, t: events.append(("started", p, t)))
    thread.file_printed.connect(lambda p, path: events.append(("printed", p, os.path.exists(path))))
    thread.print_success.connect(lambda: events.append(("success",)))
    thread.print_failed.connect(lambda m: events.append(("failed", m)))
    thread.paper_empty.connect(lambda: events.append(("paper_empty",)))
    return events


def test_three_items_print_last_first_each_with_its_own_settings(qapp, items, monkeypatch, private_temp_dir):
    cups = FakeCups()
    monkeypatch.setattr(pt.subprocess, 'run', cups.run)
    thread = PrinterThread(items, PRINTER)
    events = record(thread)

    thread.run()

    assert [(c[c.index("-n") + 1], next(o for o in c if o.startswith("print-color-mode="))) for c in cups.submitted] == [
        ("3", "print-color-mode=monochrome"),   # file 3
        ("1", "print-color-mode=color"),        # file 2
        ("2", "print-color-mode=monochrome"),   # file 1
    ]
    assert events == [
        ("started", 3, 3), ("printed", 3, True),
        ("started", 2, 3), ("printed", 2, True),
        ("started", 1, 3), ("printed", 1, True),
        ("success",),
    ]
    assert len(temp_pdfs(private_temp_dir)) == 3   # kept for ink analysis; the receiver deletes them


def test_each_job_is_the_files_own_pages_last_page_first(qapp, items, monkeypatch):
    cups = FakeCups()
    monkeypatch.setattr(pt.subprocess, 'run', cups.run)
    thread = PrinterThread(items, PRINTER)
    pages = []
    thread.file_printed.connect(lambda p, path: pages.append(
        (p, [pg.get_text().strip() for pg in fitz.open(path)])))

    thread.run()

    assert pages == [(3, ["Page 2"]), (2, ["Page 3", "Page 2", "Page 1"]), (1, ["Page 3", "Page 2", "Page 1"])]


def test_deleting_the_sources_mid_job_does_not_stop_it(qapp, items, monkeypatch):
    """Another customer's timeout deletes the Session folders; the PDFs were built up front."""
    def delete_sources(_):
        for item in items:
            if os.path.exists(item.path):
                os.remove(item.path)

    cups = FakeCups(on_submit=delete_sources)
    monkeypatch.setattr(pt.subprocess, 'run', cups.run)
    thread = PrinterThread(items, PRINTER)
    events = record(thread)

    thread.run()

    assert len(cups.submitted) == 3
    assert events[-1] == ("success",)


def test_an_unbuildable_item_submits_nothing_and_fails_once(qapp, items, monkeypatch, private_temp_dir):
    items[1].pages = [1, 9]   # the second file has no page 9
    cups = FakeCups()
    monkeypatch.setattr(pt.subprocess, 'run', cups.run)
    thread = PrinterThread(items, PRINTER)
    events = record(thread)

    thread.run()

    assert cups.submitted == []
    assert [e[0] for e in events] == ["failed"]
    assert "Failed to create temporary PDF" in events[0][1]
    assert temp_pdfs(private_temp_dir) == []


def test_a_failure_on_the_second_job_stops_there(qapp, items, monkeypatch, private_temp_dir):
    cups = FakeCups(fail_job=2)
    monkeypatch.setattr(pt.subprocess, 'run', cups.run)
    thread = PrinterThread(items, PRINTER)
    events = record(thread)

    thread.run()

    assert events == [
        ("started", 3, 3), ("printed", 3, True),
        ("started", 2, 3), ("paper_empty",), ("failed", f"No paper detected on {PRINTER}"),
    ]
    assert len(cups.submitted) == 2            # file 1 is never submitted
    assert cups.cancelled == [f"{PRINTER}-2"]   # the failing job is cancelled
    # only the printed file's PDF survives (for ink analysis)
    assert len(temp_pdfs(private_temp_dir)) == 1


def test_a_failure_on_the_first_job_prints_nothing(qapp, items, monkeypatch, private_temp_dir):
    cups = FakeCups(fail_job=1)
    monkeypatch.setattr(pt.subprocess, 'run', cups.run)
    thread = PrinterThread(items, PRINTER)
    events = record(thread)

    thread.run()

    assert [e[0] for e in events] == ["started", "paper_empty", "failed"]
    assert temp_pdfs(private_temp_dir) == []


def test_cups_refusing_the_job_fails_and_cleans_up(qapp, items, monkeypatch, private_temp_dir):
    monkeypatch.setattr(pt.subprocess, 'run',
                        lambda cmd, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    thread = PrinterThread(items, PRINTER)
    events = record(thread)

    thread.run()

    assert [e[0] for e in events] == ["started", "failed"]
    assert temp_pdfs(private_temp_dir) == []


# ---- signal order through PrinterManager ------------------------------------

class SimulatedThread(PrinterThread):
    """Emits like the real thread (file_printed per item, last first, then a failure or
    success) without CUPS, so the forwarding through PrinterManager is what's tested."""

    def __init__(self, n, fail_at):
        super().__init__([], PRINTER)
        self.n, self.fail_at = n, fail_at

    def run(self):
        for pos in range(self.n, 0, -1):
            if pos == self.fail_at:
                self.paper_empty.emit()
                self.print_failed.emit("No paper")
                return
            self.file_printed.emit(pos, f"/tmp/{pos}.pdf")
        self.print_success.emit()


def test_file_printed_always_reaches_the_main_thread_before_the_outcome(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv('SIM_MODE', 'true')
    n = 4
    log = []
    main = QThread.currentThread()
    manager = pm.PrinterManager()
    manager.file_printed.connect(lambda p, _: log.append(("printed", p, QThread.currentThread() is main)))
    manager.print_job_failed.connect(lambda m: log.append(("failed", None, QThread.currentThread() is main)))
    manager.print_job_successful.connect(lambda: log.append(("success", None, QThread.currentThread() is main)))

    source = make_pdf(tmp_path / "x.pdf", 1)
    bad = []
    for run in range(60):
        fail_at = run % (n + 1)   # 0 = no failure
        log.clear()
        monkeypatch.setattr(pm, 'PrinterThread', lambda items, printer_name, f=fail_at: SimulatedThread(n, f))
        manager.print_items([PrintItem({'path': source}, [1])])
        thread = manager.print_thread
        thread.wait(5000)
        deadline = 0
        while not any(e[0] in ("failed", "success") for e in log) and deadline < 500:
            QCoreApplication.processEvents()
            deadline += 1
            QThread.msleep(2)
        expected = [("printed", p, True) for p in range(n, fail_at, -1)]
        expected.append(("failed" if fail_at else "success", None, True))
        if log != expected:
            bad.append((run, fail_at, list(log)))
        QCoreApplication.processEvents()
        manager.print_thread = None

    assert bad == []


def test_a_missing_source_file_is_refused_before_a_thread_starts(qapp, monkeypatch):
    monkeypatch.setenv('SIM_MODE', 'true')
    manager = pm.PrinterManager()
    failures = []
    manager.print_job_failed.connect(failures.append)

    manager.print_items([PrintItem({'path': '/nope/missing.pdf'}, [1])])

    assert failures == ["File not found: /nope/missing.pdf"]
    assert manager.print_thread is None
