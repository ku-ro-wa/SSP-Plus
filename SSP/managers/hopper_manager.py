# screens/hopper_manager.py

import time
from PyQt5.QtCore import QThread, pyqtSignal

# --- Check for pigpio and set a flag ---
try:
    import pigpio
    PIGPIO_AVAILABLE = True
    print("SUCCESS: pigpio library found. Hopper control is ENABLED.")
except ImportError:
    PIGPIO_AVAILABLE = False
    print("WARNING: pigpio library not found. Hopper control will be SIMULATED.")


# --- General Configuration ---
COIN_DELAY = 1.0         # Delay after a successful dispense before next one
# Longest the motor runs waiting for one coin. The hoppers pay ~5 coins/s, so a
# sensor that sees nothing (empty, jammed, unwired) lets out a few coins at most
# before the hopper is given up and the rest of the change becomes a Voucher.
# There is no retry: each one would run the motor blind again.
DISPENSING_TIMEOUT = 1.5
SIM_COIN_SECONDS = 1.5   # Simulated time per coin when pigpio isn't available

# Coin-out sensor filtering. The sensor lines pick up motor noise (thousands of
# edges a second while a motor runs); a coin is one low pulse, 43-183 ms on the kiosk.
SENSOR_GLITCH_FILTER_US = 5000  # pigpiod drops level changes shorter than this
SENSOR_PULSE_MIN_MS = 20
SENSOR_PULSE_MAX_MS = 300


def hopper_configs():
    """Pins for the two hoppers, from .env (see config.py for defaults).
    Hopper A dispenses ₱1 coins, hopper B ₱5 coins."""
    from config import get_config
    cfg = get_config()
    return {
        'A': {'signal_pin': cfg.hopper_a_signal_pin, 'enable_pin': cfg.hopper_a_enable_pin},
        'B': {'signal_pin': cfg.hopper_b_signal_pin, 'enable_pin': cfg.hopper_b_enable_pin},
    }


def stop_all_hopper_motors():
    """Switch both hopper motors off over a fresh pigpio connection. pigpiod keeps an
    output's level after the app exits, so a motor left on keeps running until the
    hopper is empty or the power is cut. Safe to call any time; True if written."""
    if not PIGPIO_AVAILABLE:
        return False
    pi = None
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("WARNING: pigpio not connected, could not stop the hopper motors")
            return False
        pins = [cfg['enable_pin'] for cfg in hopper_configs().values()]
        for pin in pins:
            pi.write(pin, 1)  # active low: HIGH = motor off
        print(f"Hopper motors stopped (GPIO {', '.join(map(str, pins))})")
        return True
    except Exception as e:
        print(f"WARNING: could not stop the hopper motors: {e}")
        return False
    finally:
        if pi is not None:
            pi.stop()


class HopperController:
    """
    Controls a single coin hopper motor and sensor.
    This class is adapted from the user-provided script.
    """

    def __init__(self, pi_instance, name, signal_pin, enable_pin):
        self.pi = pi_instance
        if not self.pi.connected:
            raise Exception("Failed to connect to pigpiod")

        # Hopper-specific identifiers
        self.name = name
        self.signal_pin = signal_pin
        self.enable_pin = enable_pin

        # State variables
        self.enabled = False
        self.dispensing = False

        # Sensor state tracking
        self.coin_passage_count = 0
        self.pulse_start_tick = None  # pigpio tick of the current low pulse's falling edge

        if PIGPIO_AVAILABLE and self.pi and self.pi.connected:
            try:
                # Motor off before the pin becomes an output (write() makes it one):
                # setting the mode first could leave it low, i.e. running, for a moment.
                self._disable_hopper()
                self.pi.set_mode(self.enable_pin, pigpio.OUTPUT)

                self.pi.set_mode(self.signal_pin, pigpio.INPUT)
                self.pi.set_pull_up_down(self.signal_pin, pigpio.PUD_UP)
                self.pi.set_glitch_filter(self.signal_pin, SENSOR_GLITCH_FILTER_US)

                # Both edges, so each low pulse can be timed
                self.callback = self.pi.callback(self.signal_pin, pigpio.EITHER_EDGE, self._sensor_callback)
                print(f"[{self.name}] GPIO setup completed: sensor GPIO {self.signal_pin}, "
                      f"motor enable GPIO {self.enable_pin}")
            except Exception as e:
                print(f"[{self.name}] ERROR: Failed to setup GPIO: {e}")
                self.callback = None
        else:
            print(f"[{self.name}] WARNING: pigpio not available or not connected")
            self.callback = None

    def cleanup(self):
        """Clean up GPIO resources."""
        try:
            # First disable the hopper to stop any ongoing operations
            if self.pi and hasattr(self.pi, 'connected') and self.pi.connected:
                self._disable_hopper()
                print(f"[{self.name}] Hopper disabled during cleanup")
            elif self.pi is None:
                print(f"[{self.name}] No pigpio connection to clean up")

            # Then cancel the callback
            if self.callback:
                try:
                    self.callback.cancel()
                    self.callback = None
                    print(f"[{self.name}] Callback cleaned up")
                except Exception as callback_error:
                    print(f"[{self.name}] Error canceling callback: {callback_error}")
            if self.pi and getattr(self.pi, 'connected', False):
                self.pi.set_glitch_filter(self.signal_pin, 0)  # pigpiod keeps it after we exit

        except Exception as e:
            print(f"[{self.name}] Error during cleanup: {e}")

    def _enable_hopper(self):
        if not self.pi or not self.pi.connected:
            print(f"[{self.name}] ERROR: pigpio connection not available")
            return False
        try:
            self.pi.write(self.enable_pin, 0)  # Active low
            self.enabled = True
            print(f"[{self.name}] Hopper motor ENABLED")
            return True
        except Exception as e:
            print(f"[{self.name}] ERROR: Failed to enable hopper: {e}")
            return False

    def _disable_hopper(self):
        if not self.pi or not self.pi.connected:
            print(f"[{self.name}] ERROR: pigpio connection not available")
            return False
        try:
            self.pi.write(self.enable_pin, 1)  # Inactive high
            self.enabled = False
            return True
        except Exception as e:
            print(f"[{self.name}] ERROR: Failed to disable hopper: {e}")
            return False

    def _sensor_callback(self, gpio, level, tick):
        """A coin passing the sensor is one low pulse SENSOR_PULSE_MIN_MS-MAX_MS wide.
        Uses the edge's own tick: the time the callback runs is not the edge time."""
        if level == 0:  # falling edge: a low pulse starts
            self.pulse_start_tick = tick
            return
        if level != 1 or self.pulse_start_tick is None:
            return
        # Rising edge: the pulse ends. Ticks are µs and wrap at 2**32.
        width_ms = ((tick - self.pulse_start_tick) & 0xFFFFFFFF) / 1000
        self.pulse_start_tick = None
        if not SENSOR_PULSE_MIN_MS <= width_ms <= SENSOR_PULSE_MAX_MS:
            return
        self.coin_passage_count += 1
        print(f"[{self.name}] SENSOR: Coin passage ({width_ms:.0f}ms). "
              f"Total passages in this cycle: {self.coin_passage_count}")

    def _wait_for_coin_passage(self):
        """Wait for exactly one coin passage through the sensor."""
        print(f"[{self.name}] Waiting for exactly one coin passage...")

        # Reset detection counters for this attempt
        self.coin_passage_count = 0
        self.pulse_start_tick = None

        timeout_start = time.time()
        while (time.time() - timeout_start) < DISPENSING_TIMEOUT:
            if self.coin_passage_count == 1:
                print(f"[{self.name}] SUCCESS: Exactly one coin passage detected!")
                return True
            if self.coin_passage_count > 1:
                print(f"[{self.name}] FAILURE: Multiple coins detected ({self.coin_passage_count})! Stopping motor.")
                return False
            time.sleep(0.01)

        # Handle timeout condition
        if self.coin_passage_count == 1:
            print(f"[{self.name}] SUCCESS: Exactly one coin passage detected (at timeout).")
            return True
        else:
            print(f"[{self.name}] TIMEOUT: Waited {DISPENSING_TIMEOUT}s. Found {self.coin_passage_count} passages.")
            return False

    def _dispense_single_coin_attempt(self):
        """Single attempt to dispense exactly one coin."""
        # Enable hopper motor
        self._enable_hopper()

        # Wait for exactly one coin passage
        success = self._wait_for_coin_passage()

        # Stop motor immediately after detection (success or failure)
        self._disable_hopper()

        return success

    def dispense_single_coin(self):
        """Dispense exactly one coin: one attempt, no retry (see DISPENSING_TIMEOUT)."""
        if self.dispensing:
            print(f"[{self.name}] Cannot start new dispense, already in progress.")
            return False

        self.dispensing = True
        print(f"\n--- [{self.name}] Dispensing 1 coin ---")

        success = self._dispense_single_coin_attempt()
        if success:
            print(f"[{self.name}] SUCCESS: Coin dispensed and verified.")
        elif self.coin_passage_count > 1:
            print(f"[{self.name}] CRITICAL: Dispensed too many coins ({self.coin_passage_count}). Stopping this hopper.")
        else:
            print(f"[{self.name}] CRITICAL FAILURE: No coin seen within {DISPENSING_TIMEOUT}s "
                  "(empty, jammed or sensor not seeing coins). Stopping this hopper.")

        # Brief pause to allow system to settle before next command
        time.sleep(COIN_DELAY)
        self.dispensing = False
        return success


class ChangeDispenser:
    """High-level manager for all hoppers."""

    def __init__(self):
        self.pi = None
        self.hoppers = {}
        self.simulated = not PIGPIO_AVAILABLE

        if not self.simulated:
            try:
                self.pi = pigpio.pi()
                if not self.pi.connected:
                    raise RuntimeError("Could not connect to pigpiod daemon.")

                # Create a controller for each hopper defined in config
                for name, config in hopper_configs().items():
                    print(f"Initializing Hopper '{name}' on Signal={config['signal_pin']}, Enable={config['enable_pin']}")
                    self.hoppers[name] = HopperController(
                        pi_instance=self.pi,
                        name=name,
                        signal_pin=config['signal_pin'],
                        enable_pin=config['enable_pin']
                    )

            except Exception as e:
                print(f"CRITICAL: Failed to initialize pigpio or hoppers: {e}. Switching to simulation mode.")
                self.simulated = True

    def check_connection(self):
        """Check if pigpio connection is still valid and try to reconnect if needed."""
        if self.simulated:
            return True

        if not self.pi or not self.pi.connected:
            print("pigpio connection lost, attempting to reconnect...")
            try:
                # Clean up existing connection
                if self.pi:
                    self.cleanup_all_hoppers()
                    self.pi.stop()

                # Create new connection
                self.pi = pigpio.pi()
                if self.pi.connected:
                    print("pigpio connection restored")
                    # Recreate all hopper controllers with new pi instance
                    for name, config in hopper_configs().items():
                        print(f"Reinitializing Hopper '{name}' with new pigpio connection")
                        self.hoppers[name] = HopperController(
                            pi_instance=self.pi,
                            name=name,
                            signal_pin=config['signal_pin'],
                            enable_pin=config['enable_pin']
                        )
                    return True
                else:
                    print("Failed to restore pigpio connection")
                    return False
            except Exception as e:
                print(f"Error reconnecting to pigpio: {e}")
                return False
        return True

    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            self.cleanup_all_hoppers()
            if self.pi:
                self.pi.stop()
        except Exception as e:
            print(f"Error in destructor: {e}")

    def reinitialize_hoppers(self):
        """Reinitialize all hoppers with current pigpio connection."""
        if self.simulated or not self.pi or not self.pi.connected:
            return False

        try:
            # Clean up existing hoppers
            self.cleanup_all_hoppers()

            # Recreate all hopper controllers
            for name, config in hopper_configs().items():
                print(f"Reinitializing Hopper '{name}' on Signal={config['signal_pin']}, Enable={config['enable_pin']}")
                self.hoppers[name] = HopperController(
                    pi_instance=self.pi,
                    name=name,
                    signal_pin=config['signal_pin'],
                    enable_pin=config['enable_pin']
                )
            return True
        except Exception as e:
            print(f"Error reinitializing hoppers: {e}")
            return False

    def dispense_change(self, amount: float, status_callback=None, admin_screen=None, db_threader=None,
                        coin_limits=None):
        """Dispenses up to `amount` in change, one coin at a time, and reports what
        actually came out. `coin_limits` ({5: n, 1: m}: the coins in each hopper,
        from PaymentAlgorithmManager.get_coin_inventory) caps how many coins of
        each kind are attempted; without it the hoppers are assumed full."""
        if amount <= 0:
            return {'success': True, 'coins_1': 0, 'coins_5': 0}

        # Check connection before starting
        if not self.check_connection():
            error_msg = "CRITICAL: pigpio connection not available. Cannot dispense change."
            print(error_msg)
            if status_callback:
                status_callback(error_msg)
            return {'success': False, 'coins_1': 0, 'coins_5': 0, 'error': 'pigpio_connection_failed'}

        # Reinitialize hoppers if needed (simulated mode has none by design)
        if not self.simulated and not self.hoppers:
            print("Hoppers not properly initialized, reinitializing...")
            if not self.reinitialize_hoppers():
                error_msg = "CRITICAL: Failed to reinitialize hoppers. Cannot dispense change."
                print(error_msg)
                if status_callback:
                    status_callback(error_msg)
                return {'success': False, 'coins_1': 0, 'coins_5': 0, 'error': 'hopper_initialization_failed'}

        owed = int(round(amount))
        limits = coin_limits or {}
        num_fives = int(owed // 5)
        if 5 in limits:
            num_fives = min(num_fives, max(0, int(limits[5])))
        ones_limit = max(0, int(limits[1])) if 1 in limits else None

        def ones_for(remaining):
            return remaining if ones_limit is None else min(remaining, ones_limit)

        planned_change = num_fives * 5 + ones_for(owed - num_fives * 5)

        print(f"Dispensing ₱{amount:.2f}: up to {num_fives}x ₱5, rest in ₱1 (plan ₱{planned_change})")
        if status_callback:
            status_callback(f"Preparing to dispense ₱{amount:.2f}...")

        stopped_early = False

        # Dispense 5-peso coins
        actual_fives = 0
        for i in range(num_fives):
            msg = f"Dispensing ₱5 coin ({i + 1} of {num_fives})"
            if status_callback:
                status_callback(msg)
            print(msg)

            if self._dispense_coin(5):
                actual_fives += 1
                print(f"DEBUG: Successfully dispensed ₱5 coin {actual_fives}/{num_fives}")
            else:
                stopped_early = True
                error_msg = f"CRITICAL: Failed to dispense ₱5 coin {i + 1}. Dispensed {actual_fives}/{num_fives} so far."
                if status_callback:
                    status_callback(error_msg)
                print(error_msg)
                # Make up the rest in ₱1 coins below instead of failing completely
                break

        # Dispense 1-peso coins (also covers any ₱5 coins that didn't come out)
        num_ones = ones_for(owed - actual_fives * 5)
        actual_ones = 0
        for i in range(num_ones):
            msg = f"Dispensing ₱1 coin ({i + 1} of {num_ones})"
            if status_callback:
                status_callback(msg)
            print(msg)

            if self._dispense_coin(1):
                actual_ones += 1
                print(f"DEBUG: Successfully dispensed ₱1 coin {actual_ones}/{num_ones}")
            else:
                stopped_early = True
                error_msg = f"CRITICAL: Failed to dispense ₱1 coin {i + 1}. Dispensed {actual_ones}/{num_ones} so far."
                if status_callback:
                    status_callback(error_msg)
                print(error_msg)
                break

        actual_change = (actual_fives * 5) + (actual_ones * 1)

        final_msg = f"Change dispensing complete. Dispensed ₱{actual_change:.2f} (₱{actual_fives}x5 + ₱{actual_ones}x1) of ₱{owed:.2f} owed."
        if status_callback:
            status_callback(final_msg)
        print(final_msg)

        # expected_change is the change OWED; planned_change is what the coin
        # limits allowed. success is False only when a hopper stopped early.
        result = {
            'success': not stopped_early,
            'coins_1': actual_ones,
            'coins_5': actual_fives,
            'actual_change': actual_change,
            'expected_change': owed,
            'planned_change': planned_change,
            'stopped_early': stopped_early,
        }
        if stopped_early:
            result['error'] = 'hopper_stopped_early'
        return result

    def _dispense_coin(self, denomination):
        """Dispense one ₱5 (hopper B) or ₱1 (hopper A) coin. True if it came out."""
        if self.simulated:
            time.sleep(SIM_COIN_SECONDS)
            return True
        return self.hoppers['B' if denomination == 5 else 'A'].dispense_single_coin()

    def cleanup_all_hoppers(self):
        """Clean up all hopper controllers."""
        print("Cleaning up all hopper controllers...")
        for name, hopper in self.hoppers.items():
            try:
                hopper.cleanup()
                print(f"[{name}] Hopper cleaned up")
            except Exception as e:
                print(f"[{name}] Error cleaning up hopper: {e}")
        # Clear the hoppers dictionary
        self.hoppers.clear()

    def cleanup(self):
        """Safely shut down all hoppers and the pigpio connection."""
        if self.pi and not self.simulated:
            print("Cleaning up all hopper controllers...")
            # Clean up all hoppers first
            self.cleanup_all_hoppers()

            # Then stop the pigpio connection
            try:
                self.pi.stop()
                print("pigpio connection stopped.")
            except Exception as e:
                print(f"Error stopping pigpio connection: {e}")
            finally:
                self.pi = None


class DispenseThread(QThread):
    """A dedicated thread to run the dispensing logic without freezing the GUI."""
    status_update = pyqtSignal(str)
    dispensing_finished = pyqtSignal(dict)  # Changed to emit the full result dict

    def __init__(self, dispenser: ChangeDispenser, amount: float, admin_screen=None, db_threader=None,
                 coin_limits=None):
        super().__init__()
        self.dispenser = dispenser
        self.amount = amount
        self.coin_limits = coin_limits
        self.admin_screen = admin_screen
        self.db_threader = db_threader

    def run(self):
        """This method is executed when the thread starts."""
        if self.dispenser is None:
            print("ERROR: Dispenser is None, cannot dispense change")
            result = {
                'success': False,
                'coins_1': 0,
                'coins_5': 0,
                'error': 'dispenser_not_available'
            }
            self.dispensing_finished.emit(result)
            return

        result = self.dispenser.dispense_change(
            self.amount,
            self.status_update.emit,
            self.admin_screen,
            self.db_threader,
            coin_limits=self.coin_limits
        )
        self.dispensing_finished.emit(result)
