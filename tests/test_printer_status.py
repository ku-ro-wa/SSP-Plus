"""
Kiosk Admin's printer status line, from `lpstat -l -p` output: the printer's
own paper/jam/door sensors win over the idle/printing state, and SIM_MODE
shows a fixed status without calling CUPS.
"""
import subprocess

import pytest

import managers.printer_status as ps
from managers.printer_status import describe_printer_status, read_printer_status

PRINTER = "HP_Smart_Tank_580_590_series_5E0E1D_USB"


def lpstat_p(alerts, state="is idle.  enabled"):
    return (f"printer {PRINTER} {state} since Thu 15 Oct 2026 17:10:35 HKT\n"
            f"\tAlerts: {alerts}\n"
            "\tDescription: HP Smart Tank 580-590 series\n")


@pytest.mark.parametrize("alerts, expected", [
    ("none", ("Ready", "success")),
    ("media-jam-error", ("Paper jam", "error")),
    ("media-empty-error media-needed-error", ("Out of paper", "error")),
    ("media-empty-report", ("Out of paper", "error")),
    ("door-open-report", ("Door open", "error")),
    ("offline-report", ("Offline", "error")),
    ("paused", ("Paused (queue disabled)", "error")),
    ("media-low-report", ("Paper low", "warning")),
])
def test_alerts(alerts, expected):
    assert describe_printer_status(lpstat_p(alerts)) == expected


def test_printing():
    out = lpstat_p("none", state=f"now printing {PRINTER}-12.  enabled")
    assert describe_printer_status(out) == ("Printing", "success")


def test_disabled_queue():
    out = (f"printer {PRINTER} disabled since Fri 16 Oct 2026 18:41:46 HKT -\n"
           "\treason unknown\n\tAlerts: none\n")
    assert describe_printer_status(out) == ("Paused (queue disabled)", "error")


def test_jam_wins_over_printing():
    out = lpstat_p("media-jam-error", state=f"now printing {PRINTER}-12.  enabled")
    assert describe_printer_status(out) == ("Paper jam", "error")


def test_printer_not_found():
    assert describe_printer_status("", found=False) == ("Not found", "error")


def _config(sim_mode):
    return type("Cfg", (), {"sim_mode": sim_mode, "printer_name": PRINTER})()


def test_sim_mode_skips_cups(monkeypatch):
    monkeypatch.setattr(ps, "get_config", lambda: _config(True))
    monkeypatch.setattr(ps.subprocess, "run", lambda *a, **k: pytest.fail("called lpstat"))
    assert read_printer_status() == ("Ready (SIM)", "success")


def test_reads_configured_printer(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=lpstat_p("media-empty-error"), stderr="")

    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", fake_run)
    assert read_printer_status() == ("Out of paper", "error")
    assert calls == [['lpstat', '-l', '-p', PRINTER]]


def test_lpstat_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", fake_run)
    assert read_printer_status() == ("Not responding", "error")
