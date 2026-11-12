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


def _fake_run(ipp_reasons, calls=None, ipptool_fails=False):
    """lpstat -l -p says no alerts (like the Smart Tank over its USB bridge);
    ipptool says `ipp_reasons`."""
    def fake_run(cmd, **kwargs):
        if calls is not None:
            calls.append(cmd)
        if cmd[:2] == ['lpstat', '-l']:
            return subprocess.CompletedProcess(cmd, 0, stdout=lpstat_p("none"), stderr="")
        if cmd[:2] == ['lpstat', '-v']:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=f"device for {PRINTER}: ipp://localhost:60000/ipp/print\n", stderr="")
        if ipptool_fails:
            raise subprocess.TimeoutExpired(cmd, 5)
        return subprocess.CompletedProcess(
            cmd, 0, stdout=f"\tprinter-state (enum) = idle\n\tprinter-state-reasons (keyword) = {ipp_reasons}\n",
            stderr="")
    return fake_run


def test_reads_configured_printer(monkeypatch):
    calls = []
    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", _fake_run("none", calls))
    assert read_printer_status() == ("Ready", "success")
    assert calls[0] == ['lpstat', '-l', '-p', PRINTER]
    assert ['lpstat', '-v', PRINTER] in calls


def test_printer_reason_missing_from_cups_is_used(monkeypatch):
    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", _fake_run("media-empty-report"))
    assert read_printer_status() == ("Out of paper", "error")


def test_several_printer_reasons(monkeypatch):
    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", _fake_run("media-low-report,door-open-report"))
    assert read_printer_status() == ("Door open", "error")


def test_ipp_failure_falls_back_to_cups(monkeypatch):
    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", _fake_run("", ipptool_fails=True))
    assert read_printer_status() == ("Ready", "success")


def test_lpstat_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(ps, "get_config", lambda: _config(False))
    monkeypatch.setattr(ps.subprocess, "run", fake_run)
    assert read_printer_status() == ("Not responding", "error")
