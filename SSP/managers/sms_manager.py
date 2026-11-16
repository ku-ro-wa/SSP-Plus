# sms_manager.py
import os
import re
import threading
import time
from config import get_config

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False
    print("WARNING: pyserial not found. SMS will be SIMULATED.")


_PHONE_NUMBER_RE = re.compile(r'\+?\d{7,15}')


def configured_phone_number():
    """The operator's number from PHONE_NUMBER in .env, or None when it is unset,
    blank, or not a phone number (such as .env.example's 09XXXXXXXXX placeholder)."""
    try:
        value = get_config().get('PHONE_NUMBER', str).strip()
    except KeyError:
        return None
    return value if _PHONE_NUMBER_RE.fullmatch(value) else None


class SMSManager:
    """Sends operator SMS through the GSM modem on the serial port.

    Each message opens the port, sends, and closes it again (~22 s of modem
    waits), so call it only through send_operator_alert(), which runs it off
    the caller's thread.
    """

    def __init__(self, phone_number=None, serial_port="/dev/serial0", baudrate=9600):
        self.phone_number = phone_number
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.last_error = None

    # The network answers a send with +CMGS (sent) or +CMS ERROR; Globe has taken
    # ~45 s to refuse one, so wait for the answer instead of a fixed time.
    PROMPT_TIMEOUT = 5
    SEND_TIMEOUT = 60

    def send_sms_and_close(self, message):
        """Opens the port, sends one SMS, closes the port. True only once the network
        confirms it (+CMGS ... OK); otherwise False, with the reason in last_error."""
        self.last_error = None
        if not self.phone_number:
            print(f"SMS not sent, no PHONE_NUMBER set in .env: {message}")
            self.last_error = "No PHONE_NUMBER set"
            return False
        sim_mode = os.getenv('SIM_MODE', 'false').lower() in ('true', '1', 'yes')
        if sim_mode or not SERIAL_AVAILABLE:
            print(f"[SIM] SMS to {self.phone_number}: {message}")
            return True
        ser = None
        try:
            print("Initializing modem...")
            ser = serial.Serial(self.serial_port, baudrate=self.baudrate, timeout=1)
            ser.reset_input_buffer()

            ser.write(b'AT\r')
            time.sleep(1)
            print("AT Response: " + ser.read(100).decode(errors="ignore").strip())

            # No echo (so the message text can't be mistaken for the modem's reply),
            # errors as words (e.g. "+CMS ERROR: ...") rather than numbers, text mode
            for setup in (b'ATE0\r', b'AT+CMEE=2\r'):
                ser.write(setup)
                time.sleep(1)
                ser.read(100)
            ser.write(b'AT+CMGF=1\r')
            time.sleep(1)
            print("CMGF Response: " + ser.read(100).decode(errors="ignore").strip())

            ser.write(f'AT+CMGS="{self.phone_number}"\r'.encode())
            prompt = self._read_until(ser, ('>', 'ERROR'), self.PROMPT_TIMEOUT)
            print("CMGS Prompt: " + prompt.strip())
            if '>' not in prompt:
                ser.write(bytes([27]))   # Esc: cancel the half-started message
                self.last_error = f"Modem refused the number: {self._error_text(prompt)}"
                print(f"❌ {self.last_error}")
                return False

            # The message, then Ctrl+Z (0x1A) to send it
            ser.write(message.encode() + bytes([26]))
            ser.flush()
            print("Message sent, waiting for the network...")

            response = self._read_until(ser, ('OK', 'ERROR'), self.SEND_TIMEOUT, after='+CMGS:')
            print("Final Response: " + response.strip())

            if "+CMGS:" in response and "OK" in response:
                print("✅ Message sent successfully!")
                return True
            if "ERROR" in response:
                self.last_error = f"Network refused it: {self._error_text(response)}"
            else:
                self.last_error = f"No answer from the network within {self.SEND_TIMEOUT} s"
            print(f"❌ {self.last_error}")
            return False

        except Exception as e:
            self.last_error = f"Serial error: {e}"
            print(self.last_error)
            return False
        finally:
            if ser is not None and ser.is_open:
                ser.close()
                print("Serial port closed.")

    @staticmethod
    def _read_until(ser, endings, timeout, after=None):
        """Reads what the modem says until one of `endings` appears (only counting
        text after `after`, when given, or any ERROR) or `timeout` seconds pass."""
        text = ''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = ser.read(ser.in_waiting or 1).decode(errors="ignore")
            text += chunk
            if 'ERROR' in text:
                return text
            if after:
                if after not in text:
                    continue
                tail = text.split(after, 1)[1]
            else:
                tail = text
            if any(e in tail for e in endings):
                return text
        return text

    @staticmethod
    def _error_text(response):
        """The modem's error line, e.g. '+CMS ERROR: User busy', or the whole reply."""
        for line in response.splitlines():
            if 'ERROR' in line:
                return line.strip()
        return response.strip() or "no reply"


# Global SMS manager instance
sms_manager = None


def get_sms_manager():
    """Get the global SMS manager instance."""
    global sms_manager
    if sms_manager is None:
        sms_manager = SMSManager(phone_number=configured_phone_number())
    return sms_manager


def send_low_paper_sms():
    """Send low paper SMS alert (in the background)."""
    send_operator_alert("Low paper, please refill.")


def send_paper_jam_sms():
    """Send paper jam SMS alert (in the background)."""
    send_operator_alert("Printer jam")


def send_printing_error_sms(error_message):
    """Send printing error SMS alert (in the background)."""
    send_operator_alert(f"Printing error: {error_message}")


def send_no_paper_sms():
    """Send no paper / media empty SMS alert (in the background)."""
    send_operator_alert("Printer is out of paper. Please refill.")


_operator_alert_lock = threading.Lock()


def _log_send_failure(message, reason=None):
    """One error_log row for an SMS the modem didn't confirm. Never raises."""
    try:
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        try:
            why = f" ({reason})" if reason else ""
            db.log_error("SMS", f"Could not send SMS{why}: {message}", "sms_manager")
        finally:
            db.close()
    except Exception as e:
        print(f"Could not log the SMS failure: {e}")


def send_operator_alert(message):
    """Send an operator SMS without blocking the caller (the modem round trip
    takes ~20 s); alerts are sent one at a time so they don't share the port.
    With no PHONE_NUMBER set, nothing is sent and no thread is started."""
    manager = get_sms_manager()
    if not manager.phone_number:
        print(f"SMS not sent, no PHONE_NUMBER set in .env: {message}")
        return

    def send():
        with _operator_alert_lock:
            try:
                sent = manager.send_sms_and_close(message)
                reason = manager.last_error
            except Exception as e:
                print(f"SMS send raised: {e}")
                sent, reason = False, str(e)
        if not sent:
            _log_send_failure(message, reason)
    threading.Thread(target=send, name="operator-sms", daemon=True).start()


def cleanup_sms():
    """Forget the SMS manager (the port is only ever open during a send)."""
    global sms_manager
    sms_manager = None
