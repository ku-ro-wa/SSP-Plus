"""
Only one copy of the kiosk app runs at a time (managers/instance_lock.py).

Two copies fight over the acceptor/hopper GPIO pins, the QR reader, port 8000
and the database. The lock is an flock, so it's released however the holder
dies, and a refused start says which process holds it.
"""
import os
import subprocess
import sys
import textwrap
import types

import pytest

pytest.importorskip("fcntl")

import main_app  # noqa: E402
from managers.instance_lock import acquire_instance_lock  # noqa: E402

LOCK_MODULE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SSP", "managers", "instance_lock.py")


def _hold_in_child(path):
    """Start a process that takes the lock and waits; returns it once it holds it."""
    code = textwrap.dedent(f"""
        import importlib.util, time
        spec = importlib.util.spec_from_file_location("instance_lock", {LOCK_MODULE!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # alone: the managers package prints at import
        handle, holder = module.acquire_instance_lock({path!r})
        print("held" if handle else "refused", flush=True)
        time.sleep(30)
    """)
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert child.stdout.readline().strip() == "held"
    return child


def test_first_copy_gets_the_lock_and_records_itself(tmp_path):
    path = str(tmp_path / "ssp-kiosk.lock")
    handle, holder = acquire_instance_lock(path)
    try:
        assert handle is not None and holder is None
        with open(path) as f:
            assert f.read().startswith(f"pid {os.getpid()}, started ")
    finally:
        handle.close()


def test_second_copy_is_refused_and_told_who_holds_it(tmp_path):
    path = str(tmp_path / "ssp-kiosk.lock")
    child = _hold_in_child(path)
    try:
        handle, holder = acquire_instance_lock(path)
        assert handle is None
        assert holder.startswith(f"pid {child.pid}, started ")
        assert "launched by" in holder
    finally:
        child.kill()
        child.wait()


def test_lock_is_free_again_after_the_holder_is_killed(tmp_path):
    path = str(tmp_path / "ssp-kiosk.lock")
    child = _hold_in_child(path)
    child.kill()  # SIGKILL: no cleanup runs, like a segfault or abort
    child.wait()
    handle, holder = acquire_instance_lock(path)
    try:
        assert handle is not None and holder is None
    finally:
        handle.close()


def test_main_refuses_a_second_copy_before_touching_anything(monkeypatch, capsys):
    monkeypatch.setattr(main_app, 'install_run_log', lambda log_dir: "(test)")
    monkeypatch.setattr(main_app, 'acquire_instance_lock',
                        lambda: (None, "pid 4242, started 2026-11-10 19:00:00, launched by labwc"))
    monkeypatch.setattr(main_app, 'init_db', lambda: pytest.fail("database touched"))
    monkeypatch.setattr(main_app, 'gpio_problem', lambda: pytest.fail("GPIO touched"))
    monkeypatch.setattr(main_app, 'get_config', lambda: types.SimpleNamespace(sim_mode=False, ui_scale=""))

    with pytest.raises(SystemExit) as exc:
        main_app.main()
    assert exc.value.code == 1
    assert "already running (pid 4242" in capsys.readouterr().out
