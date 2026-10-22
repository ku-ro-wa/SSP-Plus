"""Bill pulse decoding in PersistentGPIO: the pulse-width noise filter on the bill line.

Shapes are from the new kiosk's GPIO scan (2026-10-22): bill pulses ~50 ms wide,
50-100 ms apart, with sub-0.1 ms spikes in and between bills that used to be
counted (a ₱50 read as 7 pulses, a ₱100 as 13).
"""
import pytest

import managers.persistent_gpio as pg

MS = 1000  # µs per ms, in pigpio ticks


@pytest.fixture
def make_gpio(monkeypatch):
    monkeypatch.setattr(pg, 'PIGPIO_AVAILABLE', False)

    def make(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        pg.PersistentGPIO._instance = None
        gpio = pg.PersistentGPIO()
        gpio.bills = []
        gpio.bill_inserted.connect(gpio.bills.append)
        gpio.enable_payment()
        return gpio

    yield make
    pg.PersistentGPIO._instance = None


def pulse(gpio, start_ms, width_ms):
    """One low pulse on the bill pin: falling edge, then rising edge width_ms later."""
    gpio._bill_pulse_detected(gpio.BILL_PIN, 0, int(start_ms * MS))
    gpio._bill_pulse_detected(gpio.BILL_PIN, 1, int((start_ms + width_ms) * MS))


def bill(gpio, pulses, spikes_after=()):
    """`pulses` 50 ms pulses 100 ms apart, with a 0.05 ms spike after each listed pulse."""
    for i in range(pulses):
        pulse(gpio, i * 100, 50)
        if i in spikes_after:
            pulse(gpio, i * 100 + 54, 0.05)


def finish_bill(gpio):
    """Let the bill timeout pass and run the timer's check."""
    gpio.bill_last_pulse_time -= gpio.BILL_TIMEOUT + 1
    gpio.process_coin_timeout()


@pytest.mark.parametrize('pulses, value', [(2, 20), (5, 50), (10, 100)])
def test_clean_bills_credit_their_value(make_gpio, pulses, value):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    bill(gpio, pulses)
    finish_bill(gpio)
    assert gpio.bills == [value]


@pytest.mark.parametrize('pulses, spikes, value', [
    (5, (0, 3), 50),       # the ₱50 the kiosk read as 7 pulses
    (10, (1, 4, 8), 100),  # the ₱100 it read as 13
])
def test_spikes_inside_a_bill_are_not_counted(make_gpio, pulses, spikes, value):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    bill(gpio, pulses, spikes_after=spikes)
    finish_bill(gpio)
    assert gpio.bills == [value]


def test_lone_spikes_credit_nothing(make_gpio):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    pulse(gpio, 0, 0.05)
    pulse(gpio, 30, 0.05)  # two spikes close together used to read as a ₱20 bill
    finish_bill(gpio)
    assert gpio.bill_pulse_count == 0
    assert gpio.bills == []


def test_pulses_wider_than_max_are_not_counted(make_gpio):
    gpio = make_gpio(BILL_PULSE_FILTER='true', BILL_PULSE_MAX_MS=150)
    pulse(gpio, 0, 400)
    assert gpio.bill_pulse_count == 0


def test_pulse_spanning_tick_wraparound_is_measured(make_gpio):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    start = 2**32 - 5 * MS
    gpio._bill_pulse_detected(gpio.BILL_PIN, 0, start)
    gpio._bill_pulse_detected(gpio.BILL_PIN, 1, (start + 50 * MS) % 2**32)
    assert gpio.bill_pulse_count == 1


@pytest.mark.parametrize('pulses', [1, 3, 7, 13])
def test_unmatched_pulse_count_is_logged_not_credited(make_gpio, capsys, pulses):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    bill(gpio, pulses)
    finish_bill(gpio)
    assert gpio.bills == []
    assert f"Bill ignored: {pulses} pulses match no bill" in capsys.readouterr().out


def test_pulses_ignored_while_payment_disabled(make_gpio):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    gpio.disable_payment()
    pulse(gpio, 0, 50)
    assert gpio.bill_pulse_count == 0


def test_enable_payment_drops_half_counted_bill(make_gpio):
    gpio = make_gpio(BILL_PULSE_FILTER='true')
    pulse(gpio, 0, 50)
    gpio.disable_payment()
    gpio.enable_payment()
    assert gpio.bill_pulse_count == 0


def test_filter_off_counts_falling_edges_with_debounce(make_gpio, monkeypatch):
    gpio = make_gpio(BILL_PULSE_FILTER='false')
    now = [1000.0]
    monkeypatch.setattr(pg.time, 'time', lambda: now[0])
    for _ in range(5):
        gpio._bill_pulse_detected(gpio.BILL_PIN, 0, 0)
        now[0] += 0.05  # inside the 0.1 s debounce: not counted
        gpio._bill_pulse_detected(gpio.BILL_PIN, 0, 0)
        now[0] += 0.1
    assert gpio.bill_pulse_count == 5
