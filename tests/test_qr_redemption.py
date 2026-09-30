"""
Seam tests for the QR redemption decision (managers/qr_reader.py
decide_redemption): a classified read + current screen + a real
SessionManager on a temp SQLite database -> an outcome. No Qt.
"""
import pytest

from database.db_manager import DatabaseManager
from database.models import init_db
from managers.qr_reader import classify_payload, decide_redemption
from managers.session_manager import SessionManager, MAX_FAILED_ATTEMPTS

FILES = [{"path": "/tmp/a.pdf", "original_filename": "a.pdf"}]


@pytest.fixture
def sessions(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    db = DatabaseManager(db_path=db_path)
    yield SessionManager(db)
    db.conn.close()


def _read(session):
    return classify_payload(f"{session.session_id}:{session.otp}")


def _failed_attempts(sessions, session):
    return sessions.db_manager.get_session(session.session_id)['failed_attempts']


class TestSessionSource:
    def test_returns_source_by_id(self, sessions):
        session = sessions.create_session("email", FILES)
        assert sessions.get_session_source(session.session_id) == "email"

    def test_unknown_id_is_none(self, sessions):
        assert sessions.get_session_source("f" * 16) is None

    def test_does_not_mutate(self, sessions):
        session = sessions.create_session("wifi", FILES)
        sessions.get_session_source(session.session_id)
        row = sessions.db_manager.get_session(session.session_id)
        assert (row['status'], row['failed_attempts']) == ("pending", 0)


class TestDecideRedemption:
    @pytest.mark.parametrize("screen", ["idle", "homepage"])
    @pytest.mark.parametrize("source", ["wifi", "email"])
    def test_correct_pair_opens_files_for_that_source(self, sessions, screen, source):
        session = sessions.create_session(source, FILES)
        outcome = decide_redemption(_read(session), screen, sessions)
        assert outcome.action == "open_files"
        assert outcome.source == source
        assert outcome.files == FILES

    def test_correct_pair_marks_session_verified(self, sessions):
        session = sessions.create_session("wifi", FILES)
        decide_redemption(_read(session), "idle", sessions)
        assert sessions.db_manager.get_session(session.session_id)['status'] == "verified"

    def test_wrong_otp_counts_an_attempt(self, sessions):
        session = sessions.create_session("wifi", FILES)
        wrong = "000000" if session.otp != "000000" else "000001"
        read = classify_payload(f"{session.session_id}:{wrong}")
        outcome = decide_redemption(read, "homepage", sessions)
        assert outcome.action == "rejected"
        assert _failed_attempts(sessions, session) == 1

    def test_wrong_otps_lock_the_session_like_typed_ones(self, sessions):
        session = sessions.create_session("email", FILES)
        wrong = "000000" if session.otp != "000000" else "000001"
        read = classify_payload(f"{session.session_id}:{wrong}")
        for _ in range(MAX_FAILED_ATTEMPTS):
            decide_redemption(read, "idle", sessions)
        assert sessions.db_manager.get_session(session.session_id)['status'] == "locked"
        assert decide_redemption(_read(session), "idle", sessions).action == "rejected"

    def test_scanner_source_rejected_without_an_attempt(self, sessions):
        session = sessions.create_session("scanner", FILES)
        wrong = "000000" if session.otp != "000000" else "000001"
        for otp in (session.otp, wrong):
            outcome = decide_redemption(
                classify_payload(f"{session.session_id}:{otp}"), "idle", sessions)
            assert outcome.action == "rejected"
        assert _failed_attempts(sessions, session) == 0
        assert sessions.db_manager.get_session(session.session_id)['status'] == "pending"

    def test_unknown_session_rejected_without_error(self, sessions):
        read = classify_payload("f" * 16 + ":123456")
        assert decide_redemption(read, "idle", sessions).action == "rejected"

    def test_malformed_is_ignored_and_counts_nothing(self, sessions):
        session = sessions.create_session("wifi", FILES)
        outcome = decide_redemption(classify_payload("garbage"), "idle", sessions)
        assert outcome.action == "ignore"
        assert _failed_attempts(sessions, session) == 0

    def test_voucher_is_ignored(self, sessions):
        assert decide_redemption(classify_payload("V1:ABC"), "idle", sessions).action == "ignore"

    @pytest.mark.parametrize("screen", ["usb", "wifi", "email", "file_browser", "printing_options",
                                        "payment", "admin", "thank_you", "scanner"])
    def test_other_screens_ignore_the_read(self, sessions, screen):
        session = sessions.create_session("wifi", FILES)
        outcome = decide_redemption(_read(session), screen, sessions)
        assert outcome.action == "ignore"
        assert sessions.db_manager.get_session(session.session_id)['status'] == "pending"
