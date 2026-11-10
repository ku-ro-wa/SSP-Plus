"""Per-client attempt limit for the Portal's pickup-code form (`/redeem`).

A scan pickup code is 6 digits and `/redeem` is unauthenticated — any phone on
the Hotspot can reach it — so until issue #104 a wrong code there cost nothing
and the code space could simply be walked. Unlike the kiosk keypad, which has
one screen to lock (`managers/pickup_code_lockout.py`, a `settings`-row
deadline shared by the Wi-Fi and Email screens), the Portal has no single
screen: each client gets its own sliding window instead. MAX_ATTEMPTS wrong
codes inside WINDOW_SECONDS refuse that client until its oldest counted failure
ages out; a correct code clears the client's failures.

Deliberately not the kiosk's counter, in either direction: a phone guessing at
codes must not lock the keypad in front of a customer who is paying, and a
customer's typos at the kiosk must not refuse a phone's redemption.

State is per-process and in-memory by design. The kiosk runs a single uvicorn
server with no workers (`managers/webapp_thread.py`), so one dict is the whole
Portal; a restart forgiving a guesser costs nothing (the codes themselves live
an hour), and the low-trust Portal gets no schema of its own to write to. A
client is its request's address, so a kiosk behind NAT/one hotspot shares one
budget — which is exactly the deployment this ships to.
"""
import threading
import time

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
# Bound on tracked clients, so rotating source addresses can't grow the dict
# without limit; stale entries are dropped as they age out of their window.
MAX_TRACKED_CLIENTS = 1024


def blocked_message(seconds: int) -> str:
    minutes = max(1, -(-int(seconds) // 60))  # ceil
    return f"Too many incorrect codes. Try again in {minutes} minute(s)."


class ClientAttemptLimiter:
    def __init__(self, max_attempts=MAX_ATTEMPTS, window_seconds=WINDOW_SECONDS,
                 clock=time.monotonic):
        self.max_attempts = max(1, int(max_attempts))
        self.window = float(window_seconds)
        self.clock = clock
        self._lock = threading.Lock()
        self._failures = {}  # client -> [monotonic timestamps, oldest first]

    def _recent(self, client):
        """The client's failures still inside the window, dropping stale ones."""
        cutoff = self.clock() - self.window
        times = self._failures.get(client)
        if times is None:
            return []
        while times and times[0] <= cutoff:
            times.pop(0)
        if not times:
            self._failures.pop(client, None)
        return times

    def _blocked_for(self, times):
        """Seconds until the client has an attempt back (0 == not blocked)."""
        if len(times) < self.max_attempts:
            return 0
        # One attempt returns as the oldest counted failure leaves the window.
        return max(1, int(self.window - (self.clock() - times[0]) + 0.999))

    def blocked_for(self, client):
        """Seconds this client must wait before another attempt (0 == allowed)."""
        with self._lock:
            return self._blocked_for(self._recent(client))

    def record_failure(self, client):
        """Count a wrong code; returns seconds now blocked (>0 if it tripped)."""
        with self._lock:
            times = self._recent(client)
            times.append(self.clock())
            self._failures[client] = times
            self._evict_stale()
            return self._blocked_for(times)

    def record_success(self, client):
        with self._lock:
            self._failures.pop(client, None)

    def _evict_stale(self):
        if len(self._failures) <= MAX_TRACKED_CLIENTS:
            return
        for client in list(self._failures):
            self._recent(client)
            if len(self._failures) <= MAX_TRACKED_CLIENTS:
                return
