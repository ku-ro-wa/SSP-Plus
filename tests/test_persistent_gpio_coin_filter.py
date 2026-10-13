"""Coin pulse decoding in PersistentGPIO: pins from .env and the pulse-width noise filter.

Drives the real PersistentGPIO with pigpio switched off and calls its pigpio callback
directly with synthetic (level, tick) edges, ticks in µs as pigpio reports them.
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
        gpio.coins = []
        gpio.coin_inserted.connect(gpio.coins.append)
        gpio.enable_payment()
        return gpio

    yield make
    pg.PersistentGPIO._instance = None


def pulse(gpio, start_ms, width_ms):
    """One low pulse on the coin pin: falling edge, then rising edge width_ms later."""
    gpio._coin_pulse_detected(gpio.COIN_PIN, 0, int(start_ms * MS))
    gpio._coin_pulse_detected(gpio.COIN_PIN, 1, int((start_ms + width_ms) * MS))


def finish_coin(gpio):
    """Let the coin timeout pass and run the timer's check."""
    gpio.coin_last_pulse_time -= gpio.COIN_TIMEOUT + 1
    gpio.process_coin_timeout()


def test_pins_come_from_env(make_gpio):
    gpio = make_gpio(COIN_PIN=12, COIN_INHIBIT_PIN=22, BILL_PIN=18, BILL_INHIBIT_PIN=23)
    assert (gpio.COIN_PIN, gpio.COIN_INHIBIT_PIN, gpio.BILL_PIN, gpio.INHIBIT_PIN) == (12, 22, 18, 23)


def test_five_coin_width_pulses_credit_p5(make_gpio):
    gpio = make_gpio(COIN_PULSE_FILTER='true')
    for i in range(5):
        pulse(gpio, i * 60, 16)
    finish_coin(gpio)
    assert gpio.coins == [5]


def test_noise_spikes_between_pulses_are_not_counted(make_gpio):
    gpio = make_gpio(COIN_PULSE_FILTER='true')
    t = 0
    for _ in range(5):
        for _ in range(4):  # sub-millisecond spikes, like the idle line on the kiosk
            pulse(gpio, t, 0.4)
            t += 3
        pulse(gpio, t, 16)
        t += 60
    finish_coin(gpio)
    assert gpio.coins == [5]


def test_pulses_wider_than_max_are_not_counted(make_gpio):
    gpio = make_gpio(COIN_PULSE_FILTER='true', COIN_PULSE_MAX_MS=150)
    pulse(gpio, 0, 400)
    assert gpio.coin_pulse_count == 0


def test_pulse_spanning_tick_wraparound_is_measured(make_gpio):
    gpio = make_gpio(COIN_PULSE_FILTER='true')
    start = 2**32 - 5 * MS
    gpio._coin_pulse_detected(gpio.COIN_PIN, 0, start)
    gpio._coin_pulse_detected(gpio.COIN_PIN, 1, (start + 16 * MS) % 2**32)
    assert gpio.coin_pulse_count == 1


def test_unmatched_pulse_count_is_logged_not_credited(make_gpio, capsys):
    gpio = make_gpio(COIN_PULSE_FILTER='true')
    for i in range(3):
        pulse(gpio, i * 60, 16)
    finish_coin(gpio)
    assert gpio.coins == []
    assert "3 pulses match no coin" in capsys.readouterr().out


def test_pulses_ignored_while_payment_disabled(make_gpio):
    gpio = make_gpio(COIN_PULSE_FILTER='true')
    gpio.disable_payment()
    pulse(gpio, 0, 16)
    assert gpio.coin_pulse_count == 0


def test_enable_payment_drops_half_counted_coin(make_gpio):
    gpio = make_gpio(COIN_PULSE_FILTER='true')
    pulse(gpio, 0, 16)
    gpio.disable_payment()
    gpio.enable_payment()
    assert gpio.coin_pulse_count == 0


def test_filter_off_counts_falling_edges_with_debounce(make_gpio, monkeypatch):
    gpio = make_gpio(COIN_PULSE_FILTER='false')
    now = [1000.0]
    monkeypatch.setattr(pg.time, 'time', lambda: now[0])
    for _ in range(5):
        gpio._coin_pulse_detected(gpio.COIN_PIN, 0, 0)
        now[0] += 0.05  # inside the 0.1 s debounce: not counted
        gpio._coin_pulse_detected(gpio.COIN_PIN, 0, 0)
        now[0] += 0.1
    assert gpio.coin_pulse_count == 5
