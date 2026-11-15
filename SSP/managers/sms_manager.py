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

    def send_sms_and_close(self, message):
        """
        Sends an SMS message and closes the connection (like your working code).
        This method opens a new connection, sends the SMS, and closes it.
        """
        if not self.phone_number:
            print(f"SMS not sent, no PHONE_NUMBER set in .env: {message}")
            return False
        sim_mode = os.getenv('SIM_MODE', 'false').lower() in ('true', '1', 'yes')
        if sim_mode or not SERIAL_AVAILABLE:
            print(f"[SIM] SMS to {self.phone_number}: {message}")
            return True
        try:
            print("Initializing modem...")
            # Give modem time to boot up
            time.sleep(5)

            # Open serial connection
            ser = serial.Serial(self.serial_port, baudrate=self.baudrate, timeout=1)

            # Basic AT check
            ser.write(b'AT\r')
            time.sleep(1)
            print("AT Response: " + ser.read(100).decode(errors="ignore").strip())

            # Set SMS to text mode
            ser.write(b'AT+CMGF=1\r')
            time.sleep(1)
            print("CMGF Response: " + ser.read(100).decode(errors="ignore").strip())

            # Set the recipient's phone number
            cmd = f'AT+CMGS="{self.phone_number}"\r'
            ser.write(cmd.encode())
            time.sleep(1)
            print("CMGS Prompt: " + ser.read(100).decode(errors="ignore").strip())

            # Send the message followed immediately by Ctrl+Z (0x1A)
            ser.write(message.encode() + bytes([26]))
            ser.flush()
            print("Message sent, waiting for confirmation...")

            # Wait for the final response
            time.sleep(15)
            response = ser.read(500).decode(errors="ignore").strip()
            print("Final Response: " + response)

            if "+CMGS:" in response and "OK" in response:
                print("✅ Message sent successfully!")
                return True
            else:
                print("❌ Failed to send message.")
                return False

        except serial.SerialException as e:
            print(f"Serial error: {e}")
            return False
        except Exception as e:
            print(f"An error occurred: {e}")
            return False
        finally:
            # Close the serial port
            if 'ser' in locals() and ser.is_open:
                ser.close()
                print("Serial port closed.")


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


def _log_send_failure(message):
    """One error_log row for an SMS the modem didn't confirm. Never raises."""
    try:
        from database.db_manager import DatabaseManager
        db = DatabaseManager()
        try:
            db.log_error("SMS", f"Could not send SMS: {message}", "sms_manager")
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
            except Exception as e:
                print(f"SMS send raised: {e}")
                sent = False
        if not sent:
            _log_send_failure(message)
    threading.Thread(target=send, name="operator-sms", daemon=True).start()


def cleanup_sms():
    """Forget the SMS manager (the port is only ever open during a send)."""
    global sms_manager
    sms_manager = None
