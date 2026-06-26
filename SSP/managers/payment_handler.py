import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal

try:
    import pigpio
    PIGPIO_AVAILABLE = True
    print("SUCCESS: pigpio library found. Payment handler is ENABLED.")
except ImportError:
    PIGPIO_AVAILABLE = False
    print("WARNING: pigpio library not found. Payment handler will be SIMULATED.")


class PaymentHandler(QObject):
    coin_inserted = pyqtSignal(int)          # value of a regular coin (can be used as change)
    special_coin_inserted = pyqtSignal(int)  # value of a coin that cannot be given as change
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.pi = None

        # Pin configuration from .env via config
        try:
            from config import get_config
            cfg = get_config()
            self.COIN_PIN = cfg.coin_pin
            self.BILL_PIN = cfg.bill_pin
            self.COIN_INHIBIT_PIN = cfg.coin_inhibit_pin
            self.BILL_INHIBIT_PIN = cfg.bill_inhibit_pin
        except Exception:
            self.COIN_PIN = 12
            self.BILL_PIN = 18
            self.COIN_INHIBIT_PIN = 22
            self.BILL_INHIBIT_PIN = 23

        # Pulse counting state
        self.coin_pulse_count = 0
        self.coin_last_pulse_time = time.time()
        self.coin_pulse_start_tick = None

        self.bill_pulse_count = 0
        self.bill_last_pulse_time = time.time()
        self.bill_pulse_start_tick = None

        # Timing constants
        self.COIN_TIMEOUT = 0.3
        self.PULSE_TIMEOUT = 0.5
        self.DEBOUNCE_TIME = 0.1

        # Noise filtering — valid pulses are 10–100 ms; outside that range is noise or stuck signal
        self.MIN_PULSE_WIDTH = 0.01   # 10 ms
        self.MAX_PULSE_WIDTH = 0.1    # 100 ms

        # Payment state
        self.coin_enabled = False
        self.bill_enabled = False
        self.accepting_payments = False

        # Callbacks / processing thread
        self.coin_callback = None
        self.bill_callback = None
        self.processing_thread = None
        self.stop_processing = False

    def initialize(self) -> bool:
        if not PIGPIO_AVAILABLE:
            print("pigpio not available — payment handler running in simulation mode")
            self._start_processing_thread()
            return True

        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                print("Failed to connect to pigpio daemon")
                return False

            print("Successfully connected to pigpio daemon")
            self._setup_gpio_pins()
            self.disable_all_acceptors()
            self._start_processing_thread()
            print("Payment system initialization complete")
            return True

        except Exception as e:
            print(f"Initialization failed - {e}")
            return False

    def _setup_gpio_pins(self):
        # Use EITHER_EDGE so we can measure pulse width for noise filtering
        self.pi.set_mode(self.COIN_PIN, pigpio.INPUT)
        self.pi.set_pull_up_down(self.COIN_PIN, pigpio.PUD_UP)
        self.pi.set_mode(self.COIN_INHIBIT_PIN, pigpio.OUTPUT)
        self.coin_callback = self.pi.callback(self.COIN_PIN, pigpio.EITHER_EDGE, self._coin_pulse_detected)

        self.pi.set_mode(self.BILL_PIN, pigpio.INPUT)
        self.pi.set_pull_up_down(self.BILL_PIN, pigpio.PUD_UP)
        self.pi.set_mode(self.BILL_INHIBIT_PIN, pigpio.OUTPUT)
        self.bill_callback = self.pi.callback(self.BILL_PIN, pigpio.EITHER_EDGE, self._bill_pulse_detected)

        print(f"GPIO pins configured - Coin: {self.COIN_PIN}, Bill: {self.BILL_PIN}")
        print(f"Inhibit pins - Coin: {self.COIN_INHIBIT_PIN}, Bill: {self.BILL_INHIBIT_PIN}")

    def _coin_pulse_detected(self, gpio, level, tick):
        if not self.accepting_payments:
            return

        if level == 0:  # falling edge — pulse starts
            self.coin_pulse_start_tick = tick
        elif level == 1 and self.coin_pulse_start_tick is not None:  # rising edge — pulse ends
            pulse_width_us = tick - self.coin_pulse_start_tick
            if pulse_width_us < 0:
                pulse_width_us += 2**32
            pulse_width_sec = pulse_width_us / 1_000_000

            if pulse_width_sec < self.MIN_PULSE_WIDTH or pulse_width_sec > self.MAX_PULSE_WIDTH:
                self.coin_pulse_start_tick = None
                return

            current_time = time.time()
            if current_time - self.coin_last_pulse_time > self.DEBOUNCE_TIME:
                self.coin_pulse_count += 1
                self.coin_last_pulse_time = current_time
                print(f"Coin pulse detected - Count: {self.coin_pulse_count}, Width: {pulse_width_sec*1000:.2f}ms")

            self.coin_pulse_start_tick = None

    def _bill_pulse_detected(self, gpio, level, tick):
        if not self.accepting_payments:
            return

        if level == 0:
            self.bill_pulse_start_tick = tick
        elif level == 1 and self.bill_pulse_start_tick is not None:
            pulse_width_us = tick - self.bill_pulse_start_tick
            if pulse_width_us < 0:
                pulse_width_us += 2**32
            pulse_width_sec = pulse_width_us / 1_000_000

            if pulse_width_sec < self.MIN_PULSE_WIDTH or pulse_width_sec > self.MAX_PULSE_WIDTH:
                self.bill_pulse_start_tick = None
                return

            current_time = time.time()
            if current_time - self.bill_last_pulse_time > self.DEBOUNCE_TIME:
                self.bill_pulse_count += 1
                self.bill_last_pulse_time = current_time
                print(f"Bill pulse detected - Count: {self.bill_pulse_count}, Width: {pulse_width_sec*1000:.2f}ms")

            self.bill_pulse_start_tick = None

    def _start_processing_thread(self):
        self.stop_processing = False
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()

    def _processing_loop(self):
        while not self.stop_processing:
            try:
                now = time.time()

                if self.coin_pulse_count > 0 and (now - self.coin_last_pulse_time > self.COIN_TIMEOUT):
                    value, is_special = self._get_coin_value(self.coin_pulse_count)
                    if value > 0:
                        if is_special:
                            print(f"Special coin - {value} peso")
                            self.special_coin_inserted.emit(value)
                        else:
                            print(f"Regular coin - {value} peso")
                            self.coin_inserted.emit(value)
                    else:
                        print(f"Coin with {self.coin_pulse_count} pulses not recognized")
                    self.coin_pulse_count = 0

                if self.bill_pulse_count > 0 and (now - self.bill_last_pulse_time > self.PULSE_TIMEOUT):
                    value = self._get_bill_value(self.bill_pulse_count)
                    if value > 0:
                        print(f"Bill - {value} peso")
                        self.bill_inserted.emit(value)
                    else:
                        print(f"Bill with {self.bill_pulse_count} pulses not recognized")
                    self.bill_pulse_count = 0

                time.sleep(0.05)

            except Exception as e:
                print(f"Error in processing loop - {e}")
                time.sleep(0.1)

    def _get_coin_value(self, pulses: int) -> tuple:
        """Returns (value, is_special). is_special=True means coin cannot be given as change."""
        if 3 <= pulses <= 4:
            return (1, False)
        elif 5 <= pulses <= 6:
            return (5, False)
        elif 8 <= pulses <= 9:
            return (10, False)
        elif 11 <= pulses <= 12:
            return (20, False)
        elif 14 <= pulses <= 15:
            return (5, True)   # special ₱5 variant
        print(f"Unknown coin pulse count: {pulses}")
        return (0, False)

    def _get_bill_value(self, pulses: int) -> int:
        mapping = {2: 20, 5: 50, 10: 100, 50: 500}
        value = mapping.get(pulses, 0)
        if value == 0:
            print(f"Unknown bill pulse count: {pulses}")
        return value

    def enable_payments(self):
        if not PIGPIO_AVAILABLE or not self.pi:
            print("GPIO not available — simulating payment enable")
            self.coin_enabled = True
            self.bill_enabled = True
            self.accepting_payments = True
            self.payment_status.emit("Insert coins or bills")
            return True

        try:
            self.coin_pulse_count = 0
            self.bill_pulse_count = 0
            self.pi.write(self.COIN_INHIBIT_PIN, 1)  # HIGH = coin acceptor enabled (active high)
            self.pi.write(self.BILL_INHIBIT_PIN, 0)  # LOW = bill acceptor enabled (active low)
            self.coin_enabled = True
            self.bill_enabled = True
            self.accepting_payments = True
            print("Payment acceptors enabled")
            self.payment_status.emit("Insert coins or bills")
            return True
        except Exception as e:
            print(f"Failed to enable payments - {e}")
            return False

    def disable_payments(self):
        if not PIGPIO_AVAILABLE or not self.pi:
            print("GPIO not available — simulating payment disable")
            self.coin_enabled = False
            self.bill_enabled = False
            self.accepting_payments = False
            self.payment_status.emit("Payment acceptors disabled")
            return True

        try:
            self.pi.write(self.COIN_INHIBIT_PIN, 0)  # LOW = coin acceptor disabled
            self.pi.write(self.BILL_INHIBIT_PIN, 1)  # HIGH = bill acceptor disabled
            self.coin_enabled = False
            self.bill_enabled = False
            self.accepting_payments = False
            print("Payment acceptors disabled")
            self.payment_status.emit("Payment acceptors disabled")
            return True
        except Exception as e:
            print(f"Failed to disable payments - {e}")
            return False

    def disable_all_acceptors(self):
        if PIGPIO_AVAILABLE and self.pi:
            try:
                self.pi.write(self.COIN_INHIBIT_PIN, 0)
                self.pi.write(self.BILL_INHIBIT_PIN, 1)
            except Exception as e:
                print(f"Error disabling acceptors - {e}")
        self.coin_enabled = False
        self.bill_enabled = False
        self.accepting_payments = False

    def cleanup(self):
        print("PaymentHandler: starting cleanup")
        self.stop_processing = True
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1.0)

        if PIGPIO_AVAILABLE and self.pi:
            try:
                self.disable_all_acceptors()
            except Exception as e:
                print(f"Error disabling acceptors during cleanup - {e}")

            for attr, label in [('coin_callback', 'coin'), ('bill_callback', 'bill')]:
                cb = getattr(self, attr, None)
                if cb:
                    try:
                        cb.cancel()
                    except Exception as e:
                        print(f"Error canceling {label} callback - {e}")
                    finally:
                        setattr(self, attr, None)

            try:
                if self.pi.connected:
                    self.pi.stop()
            except Exception as e:
                print(f"Error stopping pigpio - {e}")
            finally:
                self.pi = None

        self.coin_pulse_count = 0
        self.bill_pulse_count = 0
        print("PaymentHandler: cleanup complete")

    def __del__(self):
        self.cleanup()


# Singleton — create once, reuse; only recreate after cleanup
_payment_handler_instance = None


def get_payment_handler() -> PaymentHandler:
    global _payment_handler_instance
    if _payment_handler_instance is not None:
        return _payment_handler_instance

    instance = PaymentHandler()
    if not instance.initialize():
        try:
            instance.cleanup()
        except Exception:
            pass
        return None

    _payment_handler_instance = instance
    return _payment_handler_instance


def cleanup_payment_handler():
    global _payment_handler_instance
    if _payment_handler_instance:
        try:
            _payment_handler_instance.cleanup()
        except Exception as e:
            print(f"Error during payment handler cleanup - {e}")
        finally:
            _payment_handler_instance = None
