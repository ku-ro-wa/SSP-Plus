# managers/gpio_check.py
#
# The coin/bill acceptors and the change hoppers need the pigpio library and a
# running pigpiod daemon. Without either, the payment code quietly falls back to
# simulation (no acceptor reads, simulated dispensing), so a kiosk with SIM_MODE
# off must not start without them. main() checks this before opening the window.


def gpio_problem():
    """None if pigpio imports and pigpiod answers; otherwise what's wrong and how to fix it."""
    try:
        import pigpio
    except ImportError:
        return "the pigpio library is not installed in this Python (.venv/bin/pip install pigpio)"
    pi = pigpio.pi()
    try:
        if not pi.connected:
            return "the pigpiod daemon is not running (sudo systemctl enable --now pigpiod)"
    finally:
        pi.stop()
    return None
