"""HopperController against a fake pigpio: pins from .env, the motor is off before its
pin becomes an output, the coin-out sensor counts only coin-width low pulses, and a
coin the sensor never sees stops the hopper after one short attempt.

The sensor callback is called directly with synthetic (level, tick) edges, ticks in µs
as pigpio reports them.
"""
import threading
from types import SimpleNamespace

import pytest

import managers.hopper_manager as hm

MS = 1000  # µs per ms, in pigpio ticks


class FakePi:
    connected = True

    def __init__(self):
        self.calls = []        # ('write'|'set_mode'|'glitch', pin, value) in order
        self.callbacks = {}

    def write(self, pin, value):
        self.calls.append(('write', pin, value))

    def set_mode(self, pin, mode):
        self.calls.append(('set_mode', pin, mode))

    def set_pull_up_down(self, pin, pud):
        pass

    def set_glitch_filter(self, pin, us):
        self.calls.append(('glitch', pin, us))

    def callback(self, pin, edge, func):
        self.callbacks[pin] = func
        return SimpleNamespace(cancel=lambda: self.callbacks.pop(pin, None))


@pytest.fixture
def fake_pigpio(monkeypatch):
    monkeypatch.setattr(hm, 'PIGPIO_AVAILABLE', True)
    monkeypatch.setattr(hm, 'pigpio', SimpleNamespace(INPUT=0, OUTPUT=1, PUD_UP=2, EITHER_EDGE=2),
                        raising=False)
    monkeypatch.setattr(hm, 'COIN_DELAY', 0)


@pytest.fixture
def hopper(fake_pigpio):
    pi = FakePi()
    return hm.HopperController(pi, 'A', signal_pin=9, enable_pin=24)


def pulse(hopper, start_ms, width_ms):
    """One low pulse on the sensor: falling edge, then rising edge width_ms later."""
    hopper._sensor_callback(hopper.signal_pin, 0, int(start_ms * MS))
    hopper._sensor_callback(hopper.signal_pin, 1, int((start_ms + width_ms) * MS))


def test_pins_come_from_env(monkeypatch):
    for key, value in {'HOPPER_A_SIGNAL_PIN': 9, 'HOPPER_A_ENABLE_PIN': 24,
                       'HOPPER_B_SIGNAL_PIN': 26, 'HOPPER_B_ENABLE_PIN': 25}.items():
        monkeypatch.setenv(key, str(value))
    assert hm.hopper_configs() == {'A': {'signal_pin': 9, 'enable_pin': 24},
                                   'B': {'signal_pin': 26, 'enable_pin': 25}}


def test_motor_is_off_before_its_pin_becomes_an_output(hopper):
    calls = hopper.pi.calls
    off = calls.index(('write', 24, 1))
    assert all(c[1] != 24 for c in calls[:off])  # nothing touched the enable pin before
    assert ('set_mode', 24, 1) in calls[off:]


def test_sensor_glitch_filter_set_and_cleared(hopper):
    assert ('glitch', 9, hm.SENSOR_GLITCH_FILTER_US) in hopper.pi.calls
    hopper.cleanup()
    assert hopper.pi.calls[-1] == ('glitch', 9, 0)


@pytest.mark.parametrize('width_ms', [43, 48, 59, 183])  # widths measured on the kiosk
def test_coin_width_low_pulse_counts_one_coin(hopper, width_ms):
    pulse(hopper, 0, width_ms)
    assert hopper.coin_passage_count == 1


@pytest.mark.parametrize('width_ms', [0.5, 6, 400])
def test_noise_and_too_wide_pulses_are_not_counted(hopper, width_ms):
    pulse(hopper, 0, width_ms)
    assert hopper.coin_passage_count == 0


def test_pulse_spanning_tick_wraparound_is_measured(hopper):
    start = 2**32 - 10 * MS
    hopper._sensor_callback(9, 0, start)
    hopper._sensor_callback(9, 1, (start + 45 * MS) % 2**32)
    assert hopper.coin_passage_count == 1


def test_unseen_coin_stops_after_one_short_attempt(hopper, monkeypatch):
    monkeypatch.setattr(hm, 'DISPENSING_TIMEOUT', 0.05)
    assert hopper.dispense_single_coin() is False
    motor_on = [c for c in hopper.pi.calls if c == ('write', 24, 0)]
    assert len(motor_on) == 1                            # no retry
    assert hopper.pi.calls[-1] == ('write', 24, 1)       # and the motor is off


def test_seen_coin_succeeds_and_stops_the_motor(hopper):
    # The sensor sees one coin 50 ms after the motor starts, while the hopper waits.
    threading.Timer(0.05, pulse, args=(hopper, 0, 45)).start()
    assert hopper.dispense_single_coin() is True
    assert hopper.pi.calls[-1] == ('write', 24, 1)
