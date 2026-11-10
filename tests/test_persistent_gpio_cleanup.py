"""
PersistentGPIO.cleanup() leaves both acceptors switched off.

pigpiod keeps pin levels after the app exits. cleanup() used to inhibit only the
bill acceptor, so after Ctrl+C on the kiosk `pigs r 22` still read 1 and the
coin acceptor kept taking coins that nothing credited.
"""
import managers.persistent_gpio as pg


class FakePi:
    connected = True

    def __init__(self):
        self.writes = {}
        self.glitch_filters = {}
        self.stopped = False

    def write(self, pin, value):
        self.writes[pin] = value

    def set_glitch_filter(self, pin, steady_us):
        self.glitch_filters[pin] = steady_us

    def stop(self):
        self.stopped = True


def test_cleanup_disables_coin_and_bill_acceptors(monkeypatch):
    monkeypatch.setattr(pg, 'PIGPIO_AVAILABLE', False)
    monkeypatch.setattr(pg.time, 'sleep', lambda s: None)
    pg.PersistentGPIO._instance = None
    gpio = pg.PersistentGPIO()
    try:
        pi = FakePi()
        gpio.gpio_available, gpio.pi = True, pi
        gpio.enable_payment()
        assert pi.writes == {gpio.COIN_INHIBIT_PIN: 1, gpio.INHIBIT_PIN: 0}  # both taking money

        gpio.cleanup()

        assert pi.writes[gpio.COIN_INHIBIT_PIN] == 0  # coin acceptor: HIGH = enabled
        assert pi.writes[gpio.INHIBIT_PIN] == 1       # bill acceptor: LOW = enabled
        assert pi.glitch_filters == {gpio.COIN_PIN: 0, gpio.BILL_PIN: 0}
        assert pi.stopped
    finally:
        pg.PersistentGPIO._instance = None
