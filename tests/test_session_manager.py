"""
Tests for SessionManager — pure logic, no hardware or real DB required.
DatabaseManager is replaced with an in-memory FakeDBManager that mimics the
session CRUD methods added to database/db_manager.py, so these tests run on
any laptop with no SQLite file or IMAP/AP setup.
"""
from datetime import datetime, timedelta

from managers.session_manager import SessionManager, MAX_FAILED_ATTEMPTS


class FakeDBManager:
    """
    In-memory stand-in for DatabaseManager's session + email_intake_log
    methods. Reused by test_wifi_adapter.py and test_email_adapter.py so
    both exercise the exact same method names/signatures as the real DB.
    """

    def __init__(self, settings=None):
        self.settings = settings or {}
        self.sessions = {}
        self.email_log = {}  # (uidvalidity, uid) -> row dict

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def create_session(
        self, session_id, otp_hash, source, file_path, original_filename,
        created_at, expires_at, metadata=None
    ):
        self.sessions[session_id] = {
            'session_id': session_id,
            'otp_hash': otp_hash,
            'source': source,
            'file_path': file_path,
            'original_filename': original_filename,
            'status': 'pending',
            'failed_attempts': 0,
            'created_at': created_at,
            'expires_at': expires_at,
            'metadata': metadata,
        }
        return True

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def get_verifiable_sessions(self, source):
        matches = [
            s for s in self.sessions.values()
            if s['source'] == source and s['status'] in ('pending', 'locked')
        ]
        return sorted(matches, key=lambda s: s['created_at'], reverse=True)

    def increment_session_failed_attempts(self, session_id):
        if session_id not in self.sessions:
            return None
        self.sessions[session_id]['failed_attempts'] += 1
        return self.sessions[session_id]['failed_attempts']

    def set_session_status(self, session_id, status):
        if session_id in self.sessions:
            self.sessions[session_id]['status'] = status

    def get_expired_sessions(self, now):
        return [s for s in self.sessions.values() if s['expires_at'] <= now and s['status'] != 'expired']

    def delete_session(self, session_id):
        self.sessions.pop(session_id, None)

    def get_email_intake_log(self, uidvalidity, uid):
        return self.email_log.get((uidvalidity, uid))

    def log_email_intake(self, uidvalidity, uid, message_id, outcome, session_id):
        key = (uidvalidity, uid)
        if key in self.email_log:
            return False
        self.email_log[key] = {
            'uidvalidity': uidvalidity,
            'uid': uid,
            'message_id': message_id,
            'outcome': outcome,
            'session_id': session_id,
        }
        return True


class TestCreateSession:
    def test_returns_six_digit_otp(self):
        sm = SessionManager(FakeDBManager())
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        assert len(session.otp) == 6
        assert session.otp.isdigit()

    def test_qr_bytes_is_png(self):
        sm = SessionManager(FakeDBManager())
        session = sm.create_session('email', '/tmp/fake/upload.pdf')
        assert session.qr_bytes.startswith(b'\x89PNG')

    def test_expiry_uses_default_when_unset(self):
        sm = SessionManager(FakeDBManager())
        before = datetime.now() + timedelta(minutes=15)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        assert abs((session.expires_at - before).total_seconds()) < 5

    def test_expiry_reads_operator_setting(self):
        sm = SessionManager(FakeDBManager(settings={'session_expiry_minutes': '30'}))
        expected = datetime.now() + timedelta(minutes=30)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        assert abs((session.expires_at - expected).total_seconds()) < 5

    def test_db_never_stores_plaintext_otp(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        stored = db.sessions[session.session_id]
        assert session.otp not in stored['otp_hash']


class TestVerifyOtp:
    def test_correct_otp_succeeds(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        ok, msg, file_path = sm.verify_otp(session.session_id, session.otp)
        assert ok is True
        assert file_path == '/tmp/fake/upload.pdf'

    def test_wrong_otp_fails_without_locking(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        ok, msg, file_path = sm.verify_otp(session.session_id, '000000')
        assert ok is False
        assert db.sessions[session.session_id]['status'] == 'pending'

    def test_unknown_session_fails(self):
        sm = SessionManager(FakeDBManager())
        ok, msg, file_path = sm.verify_otp('does-not-exist', '123456')
        assert ok is False
        assert file_path is None

    def test_five_failed_attempts_locks_session(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        for _ in range(MAX_FAILED_ATTEMPTS):
            sm.verify_otp(session.session_id, '000000')
        assert db.sessions[session.session_id]['status'] == 'locked'

        # Even the correct OTP is rejected once locked
        ok, msg, file_path = sm.verify_otp(session.session_id, session.otp)
        assert ok is False
        assert 'locked' in msg.lower()

    def test_expired_session_fails(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        db.sessions[session.session_id]['expires_at'] = datetime.now() - timedelta(minutes=1)

        ok, msg, file_path = sm.verify_otp(session.session_id, session.otp)
        assert ok is False
        assert 'expired' in msg.lower()
        assert db.sessions[session.session_id]['status'] == 'expired'

    def test_qr_payload_round_trips(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('email', '/tmp/fake/upload.pdf')
        ok, msg, file_path = sm.verify_qr_payload(f"{session.session_id}:{session.otp}")
        assert ok is True
        assert file_path == '/tmp/fake/upload.pdf'

    def test_malformed_qr_payload_fails(self):
        sm = SessionManager(FakeDBManager())
        ok, msg, file_path = sm.verify_qr_payload("not-a-valid-payload")
        assert ok is False


class TestVerifyOtpForSource:
    def test_matches_the_only_pending_session(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')

        ok, msg, file_path = sm.verify_otp_for_source('wifi', session.otp)

        assert ok is True
        assert file_path == '/tmp/fake/upload.pdf'
        assert db.sessions[session.session_id]['status'] == 'verified'

    def test_wrong_otp_matches_no_session(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')

        ok, msg, file_path = sm.verify_otp_for_source('wifi', '000000')

        assert ok is False
        assert file_path is None
        # No candidate matched, so nothing was mutated
        assert db.sessions[session.session_id]['status'] == 'pending'
        assert db.sessions[session.session_id]['failed_attempts'] == 0

    def test_ignores_sessions_from_a_different_source(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        email_session = sm.create_session('email', '/tmp/fake/upload.pdf')

        ok, msg, file_path = sm.verify_otp_for_source('wifi', email_session.otp)

        assert ok is False
        assert file_path is None

    def test_locked_session_match_surfaces_locked_message(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')
        db.sessions[session.session_id]['status'] = 'locked'

        ok, msg, file_path = sm.verify_otp_for_source('wifi', session.otp)

        assert ok is False
        assert 'locked' in msg.lower()

    def test_no_pending_sessions_returns_generic_failure(self):
        sm = SessionManager(FakeDBManager())
        ok, msg, file_path = sm.verify_otp_for_source('wifi', '123456')
        assert ok is False
        assert file_path is None


class TestCleanupExpiredSessions:
    def test_removes_expired_session_and_file(self, tmp_path):
        db = FakeDBManager()
        sm = SessionManager(db)
        f = tmp_path / "upload.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        session = sm.create_session('wifi', str(f))
        db.sessions[session.session_id]['expires_at'] = datetime.now() - timedelta(minutes=1)

        cleaned = sm.cleanup_expired_sessions()

        assert cleaned == 1
        assert session.session_id not in db.sessions
        assert not f.exists()

    def test_leaves_active_sessions_alone(self):
        db = FakeDBManager()
        sm = SessionManager(db)
        session = sm.create_session('wifi', '/tmp/fake/upload.pdf')

        cleaned = sm.cleanup_expired_sessions()

        assert cleaned == 0
        assert session.session_id in db.sessions
