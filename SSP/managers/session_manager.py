# managers/session_manager.py
#
# Core of the Wi-Fi/email intake pipeline (see project_objectives.txt #7).
# Modality-agnostic on purpose: email_adapter and wifi_adapter both call
# create_session() with a file already validated and saved to disk, and get
# back a single Session shape (session_id, OTP, QR PNG bytes, expiry). Each
# adapter decides how to *deliver* that Session — email_adapter attaches it
# to an SMTP reply, wifi_adapter renders it on the upload confirmation page —
# session_manager itself never branches on source.
#
# The OTP is only ever held in memory / returned once, at creation time.
# The DB stores a session_id-salted SHA-256 hash so a DB read alone can't
# reproduce a valid OTP (6 digits is only 1e6 possibilities — unsalted
# hashing would be rainbow-tableable in seconds).

import hashlib
import io
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta

import qrcode

MAX_FAILED_ATTEMPTS = 5  # fixed per project_objectives.txt, not operator-configurable
DEFAULT_EXPIRY_MINUTES = 15  # fallback if the 'session_expiry_minutes' setting is unset


@dataclass
class Session:
    session_id: str
    otp: str
    qr_bytes: bytes
    file_path: str
    expires_at: datetime


def _hash_otp(session_id: str, otp: str) -> str:
    # Salted with session_id so the same OTP string hashes differently per session.
    return hashlib.sha256(f"{session_id}:{otp}".encode()).hexdigest()


def _generate_qr_bytes(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class SessionManager:
    """
    Issues and validates OTP + QR sessions that map a temporary file to a
    pickup code. Used by both the Wi-Fi upload portal and the email intake
    poller — neither adapter touches the sessions table directly.
    """

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def _expiry_minutes(self) -> int:
        value = self.db_manager.get_setting('session_expiry_minutes', DEFAULT_EXPIRY_MINUTES)
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULT_EXPIRY_MINUTES

    def create_session(
        self, source: str, file_path: str, original_filename: str = None, metadata: str = None
    ) -> Session:
        """
        Register a new intake session for a file that's already been
        validated and saved to disk by the calling adapter.

        source: 'email' or 'wifi' — stored for reporting, doesn't affect behavior.
        """
        session_id = secrets.token_hex(8)
        otp = f"{secrets.randbelow(1_000_000):06d}"
        created_at = datetime.now()
        expires_at = created_at + timedelta(minutes=self._expiry_minutes())

        inserted = self.db_manager.create_session(
            session_id=session_id,
            otp_hash=_hash_otp(session_id, otp),
            source=source,
            file_path=file_path,
            original_filename=original_filename,
            created_at=created_at,
            expires_at=expires_at,
            metadata=metadata,
        )
        if not inserted:
            raise RuntimeError(f"Failed to persist session {session_id} to the database")

        qr_bytes = _generate_qr_bytes(f"{session_id}:{otp}")
        return Session(
            session_id=session_id,
            otp=otp,
            qr_bytes=qr_bytes,
            file_path=file_path,
            expires_at=expires_at,
        )

    def verify_qr_payload(self, payload: str):
        """Parse a scanned 'session_id:otp' QR payload and verify it."""
        try:
            session_id, otp = payload.split(":", 1)
        except ValueError:
            return False, "Malformed QR payload", None
        return self.verify_otp(session_id, otp)

    def verify_otp(self, session_id: str, otp: str):
        """
        Validate an OTP against a session (QR scan or manual entry both land
        here). Returns (success, message, file_path).
        """
        row = self.db_manager.get_session(session_id)
        if row is None:
            return False, "Session not found", None

        if row['status'] == 'locked':
            return False, "Session locked after too many failed attempts", None

        expires_at = row['expires_at']
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if row['status'] == 'expired' or datetime.now() > expires_at:
            self.db_manager.set_session_status(session_id, 'expired')
            return False, "Session expired", None

        if row['status'] == 'verified':
            return True, "Session already verified", row['file_path']

        if _hash_otp(session_id, otp) != row['otp_hash']:
            attempts = self.db_manager.increment_session_failed_attempts(session_id)
            if attempts is not None and attempts >= MAX_FAILED_ATTEMPTS:
                self.db_manager.set_session_status(session_id, 'locked')
                return False, "Incorrect OTP — session now locked", None
            return False, "Incorrect OTP", None

        self.db_manager.set_session_status(session_id, 'verified')
        return True, "Session verified", row['file_path']

    def cleanup_expired_sessions(self) -> int:
        """
        Mark past-expiry sessions as expired, delete their temp files, and
        remove the DB row. Returns the number of sessions cleaned up.
        Intended to run on a background schedule (see ink_analysis_threader
        for the existing QThread pattern this can follow).
        """
        expired = self.db_manager.get_expired_sessions(datetime.now())
        cleaned = 0
        for row in expired:
            file_path = row['file_path']
            try:
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path, ignore_errors=True)
                elif os.path.isfile(file_path):
                    os.remove(file_path)
            except OSError as e:
                print(f"Error removing session file '{file_path}': {e}")
            self.db_manager.delete_session(row['session_id'])
            cleaned += 1
        return cleaned
