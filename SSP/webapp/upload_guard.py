"""Limits on Portal uploads that the per-upload checks don't cover.

Each upload is capped (MAX_UPLOAD_SIZE_MB per file, 20 files), but nothing
stopped a phone repeating uploads, and every accepted one stays on the SD card
until its Session's pickup window ends (12 h). Two checks run before the
request body is read:

- a per-phone limit: PORTAL_UPLOADS_PER_PHONE upload requests inside
  PORTAL_UPLOAD_WINDOW_MINUTES from one address, then 429 + Retry-After until
  the oldest leaves the window. Every request counts, accepted or refused by the
  file checks, because each one is received and spooled before those checks.
  The counter is ClientAttemptLimiter (webapp/rate_limit.py), a separate
  instance from /redeem's.
- a storage floor: refused with 507 when the upload folder's filesystem would
  have less than MIN_FREE_STORAGE_MB left after the request's declared size.
  One error_log row per hour while it lasts, so the operator sees it.

Like /redeem's limit this is per address and in memory: a phone that changes
its address starts again, and a restart forgets the counts.
"""
import os
import shutil
import time

from webapp.rate_limit import ClientAttemptLimiter

ERROR_SOURCE = "Wi-Fi Portal"
STORAGE_LOG_INTERVAL_SECONDS = 60 * 60


def too_many_message(seconds: int) -> str:
    minutes = max(1, -(-int(seconds) // 60))  # ceil
    return f"Too many uploads from this phone. Try again in {minutes} minute(s)."


STORAGE_FULL_MESSAGE = "The kiosk's storage is full right now. Please try again later."


def _existing_dir(path: str) -> str:
    """The nearest folder that exists, so a not-yet-created upload dir still has a filesystem."""
    path = os.path.abspath(path)
    while not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def free_bytes(path: str) -> int:
    return shutil.disk_usage(_existing_dir(path)).free


class UploadGuard:
    def __init__(self, upload_dir, uploads_per_phone=10, window_minutes=10,
                 min_free_mb=1024, clock=time.monotonic, free_bytes=free_bytes,
                 log_error=None):
        self.upload_dir = upload_dir
        self.limiter = ClientAttemptLimiter(uploads_per_phone, window_minutes * 60, clock=clock)
        self.min_free_bytes = int(min_free_mb) * 1024 * 1024
        self.clock = clock
        self.free_bytes = free_bytes
        self.log_error = log_error
        self._last_storage_log = None

    def check(self, client: str, declared_bytes: int):
        """(status, message, retry_after) to refuse the upload, or None to let it through
        (and count it against the phone)."""
        blocked = self.limiter.blocked_for(client)
        if blocked:
            print(f"Wi-Fi Portal: upload refused, per-phone limit ({blocked} s left)")
            return 429, too_many_message(blocked), blocked

        try:
            free = self.free_bytes(self.upload_dir)
        except OSError as e:
            print(f"Wi-Fi Portal: could not read free storage ({e}); upload allowed")
            free = None
        if free is not None and free - max(0, declared_bytes) < self.min_free_bytes:
            self._log_storage(free)
            return 507, STORAGE_FULL_MESSAGE, None

        self.limiter.record_failure(client)  # counts the attempt; "failure" is the limiter's name
        return None

    def _log_storage(self, free):
        message = (f"Upload refused: {free // (1024 * 1024)} MB free, "
                   f"below the {self.min_free_bytes // (1024 * 1024)} MB floor")
        print(f"Wi-Fi Portal: {message}")
        now = self.clock()
        if self._last_storage_log is not None and now - self._last_storage_log < STORAGE_LOG_INTERVAL_SECONDS:
            return
        self._last_storage_log = now
        if self.log_error is None:
            return
        try:
            self.log_error(ERROR_SOURCE, message, "Wi-Fi Portal")
        except Exception as e:
            print(f"Wi-Fi Portal: could not log storage refusal: {e}")


def _log_error_to_db(error_type, message, context):
    from database.db_manager import DatabaseManager
    db = DatabaseManager()
    try:
        db.log_error(error_type, message, context)
    finally:
        db.close()


def from_config():
    from config import get_config
    config = get_config()
    return UploadGuard(
        config.wifi_upload_dir,
        uploads_per_phone=config.portal_uploads_per_phone,
        window_minutes=config.portal_upload_window_minutes,
        min_free_mb=config.min_free_storage_mb,
        log_error=_log_error_to_db,
    )
