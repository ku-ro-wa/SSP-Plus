# managers/persistent_gpio.py

import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal

try:
    import pigpio
    PIGPIO_AVAILABLE = True
    print("SUCCESS: pigpio library found. Persistent GPIO is ENABLED.")
except ImportError:
    PIGPIO_AVAILABLE = False
    print("WARNING: pigpio library not found. Persistent GPIO will be SIMULATED.")


class PersistentGPIO(QObject):
    """Singleton GPIO service that maintains a persistent pigpio connection."""

    # Global signals
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Always call parent __init__ first
        super().__init__()
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self.pi = None
        self.gpio_available = PIGPIO_AVAILABLE
        self.enabled = False
        self.running = False

        # GPIO pins and coin noise filter, from .env (see config.py for defaults)
        from config import get_config
        cfg = get_config()
        self.KIOSK_MODEL = cfg.kiosk_model
        self.COIN_PIN = cfg.coin_pin
        self.BILL_PIN = cfg.bill_pin
        self.INHIBIT_PIN = cfg.bill_inhibit_pin
        self.COIN_INHIBIT_PIN = cfg.coin_inhibit_pin
        self.coin_filter = cfg.coin_pulse_filter
        self.COIN_GLITCH_FILTER_US = cfg.coin_glitch_filter_us
        self.COIN_PULSE_MIN_MS = cfg.coin_pulse_min_ms
        self.COIN_PULSE_MAX_MS = cfg.coin_pulse_max_ms
        self.bill_filter = cfg.bill_pulse_filter
        self.BILL_GLITCH_FILTER_US = cfg.bill_glitch_filter_us
        self.BILL_PULSE_MIN_MS = cfg.bill_pulse_min_ms
        self.BILL_PULSE_MAX_MS = cfg.bill_pulse_max_ms

        # Timing constants (matching original GPIOPaymentThread)
        self.DEBOUNCE_TIME = 0.1   # Minimum time between pulses
        self.COIN_TIMEOUT = 0.5    # seconds without pulses = end of coin
        self.BILL_TIMEOUT = 0.5    # Time to wait for additional bill pulses (PULSE_TIMEOUT)

        # State tracking
        self.coin_pulse_count = 0
        self.coin_last_pulse_time = 0
        self.coin_pulse_start_tick = None  # pigpio tick of the current low pulse's falling edge
        self.bill_pulse_count = 0
        self.bill_last_pulse_time = 0
        self.bill_pulse_start_tick = None  # pigpio tick of the current low pulse's falling edge

        # Callbacks
        self.coin_callback = None
        self.bill_callback = None

        # Thread safety
        self._state_lock = threading.Lock()

        # Initialize GPIO if available
        if self.gpio_available:
            self._initialize_gpio()

    def _initialize_gpio(self):
        """Initialize persistent GPIO connection."""
        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise Exception("Could not connect to pigpio daemon")

            # Setup coin acceptor GPIO
            self.pi.set_mode(self.COIN_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.COIN_PIN, pigpio.PUD_UP)
            if self.coin_filter:
                # Drop the line's sub-millisecond spikes in pigpiod, then time each low
                # pulse (both edges) so only coin-width pulses are counted.
                self.pi.set_glitch_filter(self.COIN_PIN, self.COIN_GLITCH_FILTER_US)
                edge = pigpio.EITHER_EDGE
            else:
                self.pi.set_glitch_filter(self.COIN_PIN, 0)
                edge = pigpio.FALLING_EDGE
            self.coin_callback = self.pi.callback(self.COIN_PIN, edge, self._coin_pulse_detected)
            print(f"Coin acceptor ({self.KIOSK_MODEL} kiosk model): pulses on GPIO {self.COIN_PIN}, inhibit on GPIO {self.COIN_INHIBIT_PIN}, "
                  + (f"filter {self.COIN_GLITCH_FILTER_US}us glitch / "
                     f"{self.COIN_PULSE_MIN_MS:g}-{self.COIN_PULSE_MAX_MS:g}ms pulses"
                     if self.coin_filter else "filter OFF"))

            # Setup coin acceptor inhibit pin (pin 22)
            self.pi.set_mode(self.COIN_INHIBIT_PIN, pigpio.OUTPUT)
            self._set_coin_acceptor_state(False)  # Start disabled

            # Setup bill acceptor GPIO
            self.pi.set_mode(self.BILL_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.BILL_PIN, pigpio.PUD_UP)
            self.pi.set_mode(self.INHIBIT_PIN, pigpio.OUTPUT)
            self._set_acceptor_state(False)  # Start disabled
            if self.bill_filter:
                # Same as the coin line: drop spikes in pigpiod, count bill-width pulses.
                self.pi.set_glitch_filter(self.BILL_PIN, self.BILL_GLITCH_FILTER_US)
                edge = pigpio.EITHER_EDGE
            else:
                self.pi.set_glitch_filter(self.BILL_PIN, 0)
                edge = pigpio.FALLING_EDGE
            self.bill_callback = self.pi.callback(self.BILL_PIN, edge, self._bill_pulse_detected)
            print(f"Bill acceptor: pulses on GPIO {self.BILL_PIN}, inhibit on GPIO {self.INHIBIT_PIN}, "
                  + (f"filter {self.BILL_GLITCH_FILTER_US}us glitch / "
                     f"{self.BILL_PULSE_MIN_MS:g}-{self.BILL_PULSE_MAX_MS:g}ms pulses"
                     if self.bill_filter else "filter OFF"))

            self.running = True
            self.payment_status.emit("Persistent GPIO ready - Coin and bill acceptors disabled")
            print("SUCCESS: Persistent GPIO initialized successfully")

        except Exception as e:
            self.payment_status.emit(f"GPIO Error: {str(e)}")
            self.gpio_available = False
            print(f"ERROR: Persistent GPIO initialization failed: {e}")

    def _coin_pulse_detected(self, gpio, level, tick):
        """Handle coin pulse detection."""
        if not self.enabled:
            return

        if not self.coin_filter:
            current_time = time.time()
            with self._state_lock:
                if current_time - self.coin_last_pulse_time > self.DEBOUNCE_TIME:
                    self.coin_pulse_count += 1
                    self.coin_last_pulse_time = current_time
                    print(f"Coin pulse detected: {self.coin_pulse_count}")
            return

        with self._state_lock:
            if level == 0:  # falling edge: a low pulse starts
                self.coin_pulse_start_tick = tick
                return
            if level != 1 or self.coin_pulse_start_tick is None:
                return
            # Rising edge: the pulse ends. Ticks are µs and wrap at 2**32.
            width_ms = ((tick - self.coin_pulse_start_tick) & 0xFFFFFFFF) / 1000
            self.coin_pulse_start_tick = None
            if not self.COIN_PULSE_MIN_MS <= width_ms <= self.COIN_PULSE_MAX_MS:
                return
            self.coin_pulse_count += 1
            self.coin_last_pulse_time = time.time()
            print(f"Coin pulse detected: {self.coin_pulse_count} ({width_ms:.1f}ms)")

    def _bill_pulse_detected(self, gpio, level, tick):
        """Handle bill pulse detection."""
        if not self.enabled:
            return

        if not self.bill_filter:
            current_time = time.time()
            with self._state_lock:
                if current_time - self.bill_last_pulse_time > self.DEBOUNCE_TIME:
                    self.bill_pulse_count += 1
                    self.bill_last_pulse_time = current_time
                    print(f"Bill pulse detected: {self.bill_pulse_count}")
            return

        with self._state_lock:
            if level == 0:  # falling edge: a low pulse starts
                self.bill_pulse_start_tick = tick
                return
            if level != 1 or self.bill_pulse_start_tick is None:
                return
            # Rising edge: the pulse ends. Ticks are µs and wrap at 2**32.
            width_ms = ((tick - self.bill_pulse_start_tick) & 0xFFFFFFFF) / 1000
            self.bill_pulse_start_tick = None
            if not self.BILL_PULSE_MIN_MS <= width_ms <= self.BILL_PULSE_MAX_MS:
                return
            self.bill_pulse_count += 1
            self.bill_last_pulse_time = time.time()
            print(f"Bill pulse detected: {self.bill_pulse_count} ({width_ms:.1f}ms)")

    def _set_acceptor_state(self, enable):
        """Enable or disable the bill acceptor."""
        print(f"DEBUG: _set_acceptor_state called with enable={enable}")
        if self.gpio_available and self.pi and self.pi.connected:
            pin_value = 0 if enable else 1
            print(f"DEBUG: Writing to INHIBIT_PIN {self.INHIBIT_PIN} with value {pin_value}")
            self.pi.write(self.INHIBIT_PIN, pin_value)  # LOW = enabled, HIGH = disabled
            print(f"Bill acceptor {'enabled' if enable else 'disabled'}")
        else:
            print(f"Bill acceptor {'enabled' if enable else 'disabled'} (simulation mode)")

    def _set_coin_acceptor_state(self, enable):
        """Enable or disable the coin acceptor."""
        print(f"DEBUG: _set_coin_acceptor_state called with enable={enable}")
        if self.gpio_available and self.pi and self.pi.connected:
            pin_value = 1 if enable else 0
            print(f"DEBUG: Writing to COIN_INHIBIT_PIN {self.COIN_INHIBIT_PIN} with value {pin_value}")
            self.pi.write(self.COIN_INHIBIT_PIN, pin_value)  # HIGH = enabled, LOW = disabled
            print(f"Coin acceptor {'enabled' if enable else 'disabled'}")
        else:
            print(f"Coin acceptor {'enabled' if enable else 'disabled'} (simulation mode)")

    def enable_payment(self):
        """Enable payment processing."""
        with self._state_lock:  # drop any half-counted coin or bill from before
            self.coin_pulse_count = 0
            self.coin_pulse_start_tick = None
            self.bill_pulse_count = 0
            self.bill_pulse_start_tick = None
        self.enabled = True
        self._set_acceptor_state(True)  # Enable bill acceptor
        self._set_coin_acceptor_state(True)  # Enable coin acceptor
        self.payment_status.emit("Payment enabled - Insert coins or bills")
        print("SUCCESS: Persistent GPIO payment enabled")

    def disable_payment(self):
        """Disable payment processing."""
        print("DEBUG: disable_payment() called")
        self.enabled = False
        print("DEBUG: About to disable bill acceptor")
        self._set_acceptor_state(False)  # Disable bill acceptor
        print("DEBUG: About to disable coin acceptor")
        self._set_coin_acceptor_state(False)  # Disable coin acceptor
        self.payment_status.emit("Payment disabled")
        print("SUCCESS: Persistent GPIO payment disabled")

    def process_coin_timeout(self):
        """Process coin timeout and emit coin value if applicable."""
        if not self.enabled:
            return

        with self._state_lock:
            current_time = time.time()

            # Process coin timeout
            if self.coin_pulse_count > 0 and (current_time - self.coin_last_pulse_time > self.COIN_TIMEOUT):
                coin_value = self._get_coin_value(self.coin_pulse_count)
                if coin_value > 0:
                    self.coin_inserted.emit(coin_value)
                    print(f"Coin processed: ₱{coin_value}")
                else:
                    print(f"WARNING: Coin ignored: {self.coin_pulse_count} pulses match no coin")
                self.coin_pulse_count = 0

            # Process bill timeout
            if self.bill_pulse_count > 0 and (current_time - self.bill_last_pulse_time > self.BILL_TIMEOUT):
                bill_value = self._get_bill_value(self.bill_pulse_count)
                if bill_value > 0:
                    self.bill_inserted.emit(bill_value)
                    print(f"Bill processed: ₱{bill_value}")
                else:
                    print(f"WARNING: Bill ignored: {self.bill_pulse_count} pulses match no bill")
                self.bill_pulse_count = 0

    def _get_coin_value(self, pulse_count):
        """Get coin value based on pulse count, as this kiosk's acceptor is programmed
        (₱1 = 3 pulses, ₱5 = 5 seen on the kiosk; each range allows one extra pulse)."""
        if 3 <= pulse_count <= 4:
            return 1
        elif 5 <= pulse_count <= 6:
            return 5
        elif 8 <= pulse_count <= 9:
            return 10
        elif 11 <= pulse_count <= 12:
            return 20
        return 0

    def _get_bill_value(self, pulse_count):
        """Get bill value based on pulse count (matching original GPIOPaymentThread)."""
        if pulse_count == 2:
            return 20
        elif pulse_count == 5:
            return 50
        elif pulse_count == 10:
            return 100
        elif pulse_count == 50:
            return 500
        return 0

    def is_connected(self):
        """Check if GPIO is connected and running."""
        return self.gpio_available and self.pi and self.pi.connected and self.running

    def get_status(self):
        """Get current GPIO status."""
        if self.is_connected():
            return "Persistent GPIO ready"
        elif self.gpio_available:
            return "Persistent GPIO connected but not ready"
        else:
            return "Persistent GPIO not available (simulation mode)"

    def cleanup(self):
        """Clean up GPIO resources (only called on app shutdown)."""
        print("Cleaning up Persistent GPIO...")
        self.running = False
        self.enabled = False

        if self.gpio_available and self.pi:
            try:
                # Cancel callbacks
                if self.coin_callback:
                    self.coin_callback.cancel()
                    self.coin_callback = None
                if self.bill_callback:
                    self.bill_callback.cancel()
                    self.bill_callback = None
                self.pi.set_glitch_filter(self.COIN_PIN, 0)  # pigpiod keeps it after we exit

                # Disable acceptor
                self._set_acceptor_state(False)
                time.sleep(0.1)  # Small delay for state change

                # Stop pigpio
                self.pi.stop()
                print("SUCCESS: Persistent GPIO cleaned up successfully")
            except Exception as e:
                print(f"WARNING: Error during Persistent GPIO cleanup: {e}")
            finally:
                self.pi = None


# Global instance
_persistent_gpio = None


def get_persistent_gpio():
    """Get the global persistent GPIO instance."""
    global _persistent_gpio
    if _persistent_gpio is None:
        _persistent_gpio = PersistentGPIO()
    return _persistent_gpio


def cleanup_persistent_gpio():
    """Clean up the global persistent GPIO instance."""
    global _persistent_gpio
    if _persistent_gpio:
        _persistent_gpio.cleanup()
        _persistent_gpio = None
