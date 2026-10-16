"""
A real kiosk (SIM_MODE off) must not run without pigpio: the payment screen
would otherwise offer customers simulated coins and bills, i.e. free credit.

- gpio_problem() names the missing piece (library or daemon).
- main() exits before creating the window when SIM_MODE is off and GPIO is missing.
- The payment screen shows the simulation buttons only in SIM_MODE.
"""
import locale
import os
import sys
import types

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication  # noqa: E402

import main_app  # noqa: E402
import screens.payment.view as view_module  # noqa: E402
import utils.error_logger as error_logger  # noqa: E402
from managers.gpio_check import gpio_problem  # noqa: E402
from managers.voucher_manager import CODE_ALPHABET  # noqa: E402
from ui.widgets import SecondaryButton  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    # See test_payment_change_flow.py: QApplication() would localise strftime.
    saved = locale.setlocale(locale.LC_ALL)
    app = QApplication.instance() or QApplication([])
    locale.setlocale(locale.LC_ALL, saved)
    return app


def fake_pigpio(connected):
    stopped = []

    class FakePi:
        def __init__(self):
            self.connected = connected

        def stop(self):
            stopped.append(True)

    return types.SimpleNamespace(pi=FakePi), stopped


def test_missing_library_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pigpio', None)  # makes `import pigpio` raise ImportError
    assert "library is not installed" in gpio_problem()


def test_daemon_not_running_is_reported(monkeypatch):
    module, stopped = fake_pigpio(connected=False)
    monkeypatch.setitem(sys.modules, 'pigpio', module)
    assert "pigpiod daemon is not running" in gpio_problem()
    assert stopped


def test_library_and_daemon_present_is_fine(monkeypatch):
    module, stopped = fake_pigpio(connected=True)
    monkeypatch.setitem(sys.modules, 'pigpio', module)
    assert gpio_problem() is None
    assert stopped  # the check's own connection is closed


def _fake_main_deps(monkeypatch, sim_mode, problem):
    logged = []
    monkeypatch.setattr(main_app, 'init_db', lambda: None)
    monkeypatch.setattr(main_app, 'get_config', lambda: types.SimpleNamespace(sim_mode=sim_mode, ui_scale=""))
    monkeypatch.setattr(main_app, 'gpio_problem', lambda: problem)
    monkeypatch.setattr(error_logger, 'log_error', lambda *args: logged.append(args))
    return logged


def test_main_refuses_to_start_without_gpio(monkeypatch):
    logged = _fake_main_deps(monkeypatch, sim_mode=False, problem="the pigpiod daemon is not running")

    def no_window(*args):
        raise AssertionError("the window must not be created")
    monkeypatch.setattr(main_app, 'QApplication', no_window)

    with pytest.raises(SystemExit) as exc:
        main_app.main()
    assert exc.value.code == 1
    assert logged and "pigpiod daemon is not running" in logged[0][1]


def test_sim_mode_skips_the_gpio_check(monkeypatch):
    _fake_main_deps(monkeypatch, sim_mode=True, problem="should not be checked")
    monkeypatch.setattr(main_app, 'gpio_problem', lambda: pytest.fail("checked in SIM_MODE"))
    monkeypatch.setattr(main_app, 'apply_ui_scale', lambda value: 1.0)

    reached = []

    def window_created(*args):
        reached.append(True)
        raise RuntimeError("stop here")  # main() reports it and exits
    monkeypatch.setattr(main_app, 'QApplication', window_created)

    with pytest.raises(SystemExit):
        main_app.main()
    assert reached


def _sim_buttons(view):
    return [b for b in view.findChildren(SecondaryButton) if b.text() in ("P1", "P5", "P100")]


@pytest.mark.parametrize("sim_mode, shown", [(True, True), (False, False)])
def test_simulation_buttons_only_in_sim_mode(qapp, monkeypatch, sim_mode, shown):
    monkeypatch.setattr(view_module, 'get_config', lambda: types.SimpleNamespace(sim_mode=sim_mode))
    view = view_module.PaymentScreenView(voucher_keys=CODE_ALPHABET)
    view.setLayout(view.main_layout)  # the controller does this in the app
    assert bool(_sim_buttons(view)) is shown
