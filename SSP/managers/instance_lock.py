# managers/instance_lock.py
#
# Only one copy of the kiosk app may run at a time. Two copies fight over the
# coin/bill acceptor and hopper GPIO pins, the QR reader's serial port, the
# Wi-Fi portal's port 8000 and the database: a second copy's startup disables
# the acceptors under the first one's payment screen, and coins credit in
# whichever process happens to be watching. On the kiosk the app is started by
# hand from a desktop terminal, with no service to stop first, so `make run` over
# SSH used to start a second copy silently. main() takes this lock before anything
# touches hardware and refuses to start when it's held.
#
# The lock is an flock() on a file in the temp directory, shared by every clone
# on the machine (the hardware is shared too). The kernel drops it when the
# process ends, however it ends (segfault, abort, kill -9), so it never goes stale.

import os
import tempfile
import time

LOCK_NAME = "ssp-kiosk.lock"


def default_lock_path():
    return os.path.join(tempfile.gettempdir(), LOCK_NAME)


def _launched_by():
    """The parent process's name (e.g. labwc, bash, make), or '?' off Linux."""
    try:
        with open(f"/proc/{os.getppid()}/comm") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"


def acquire_instance_lock(path=None):
    """
    Take the single-instance lock for this process's lifetime.

    Returns (handle, None) on success; keep the handle open, closing it releases
    the lock. Returns (None, holder) if another process holds it, where holder is
    that process's description ("pid 1234, started ..., launched by labwc").
    Where flock isn't available (Windows) there's no lock and it always succeeds.
    """
    try:
        import fcntl
    except ImportError:
        return object(), None

    path = path or default_lock_path()
    handle = open(path, "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.seek(0)
        holder = handle.read().strip() or "pid unknown"
        handle.close()
        return None, holder

    handle.seek(0)
    handle.truncate()
    handle.write(f"pid {os.getpid()}, started {time.strftime('%Y-%m-%d %H:%M:%S')}, "
                 f"launched by {_launched_by()}\n")
    handle.flush()
    return handle, None
