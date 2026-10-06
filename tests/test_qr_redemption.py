"""
Seam tests for the QR redemption decision (managers/qr_reader.py
decide_redemption): a classified read + current screen + a real
SessionManager on a temp SQLite database -> an outcome. No Qt.
"""
from datetime import datetime, timedelta

import pytest

from database.db_manager import DatabaseManager
from database.models import init_db
from managers.qr_reader import (
    DuplicateReadFilter, classify_payload, decide_redemption,
    MSG_CANT_READ, MSG_CANT_USE_HERE, MSG_VOUCHER_AT_PAYMENT,
)
from managers.session_manager import SessionManager, MAX_FAILED_ATTEMPTS

FILES = [{"path": "/tmp/a.pdf", "original_filename": "a.pdf"}]


@pytest.fixture
def sessions(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    db = DatabaseManager(db_path=db_path)
    yield SessionManager(db)
    db.conn.close()


ACCEPTING_SCREENS = ["idle", "homepage", "wifi", "email"]


def _wrong_otp(session):
    return "000000" if session.otp != "000000" else "000001"


def _read(session, otp=None):
    return classify_payload(f"{session.session_id}:{otp or session.otp}")


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
    @pytest.mark.parametrize("screen", ACCEPTING_SCREENS)
    @pytest.mark.parametrize("source", ["wifi", "email"])
    def test_correct_pair_opens_files_for_that_source(self, sessions, screen, source):
        session = sessions.create_session(source, FILES)
        outcome = decide_redemption(_read(session), screen, sessions)
        assert outcome.action == "open_files"
        assert outcome.source == source
        assert outcome.files == FILES

    @pytest.mark.parametrize("screen,other", [("wifi", "email"), ("email", "wifi")])
    def test_other_sources_session_opens_its_own_flow(self, sessions, screen, other):
        session = sessions.create_session(other, FILES)
        outcome = decide_redemption(_read(session), screen, sessions)
        assert outcome.action == "open_files"
        assert outcome.source == other

    def test_correct_pair_marks_session_verified(self, sessions):
        session = sessions.create_session("wifi", FILES)
        decide_redemption(_read(session), "idle", sessions)
        assert sessions.db_manager.get_session(session.session_id)['status'] == "verified"

    def test_wrong_otp_counts_an_attempt(self, sessions):
        session = sessions.create_session("wifi", FILES)
        outcome = decide_redemption(_read(session, otp=_wrong_otp(session)), "homepage", sessions)
        assert outcome.action == "rejected"
        assert outcome.message == "Incorrect OTP"
        assert _failed_attempts(sessions, session) == 1

    def test_wrong_otps_lock_the_session_like_typed_ones(self, sessions):
        session = sessions.create_session("email", FILES)
        for _ in range(MAX_FAILED_ATTEMPTS):
            decide_redemption(_read(session, otp=_wrong_otp(session)), "idle", sessions)
        assert sessions.db_manager.get_session(session.session_id)['status'] == "locked"
        outcome = decide_redemption(_read(session), "idle", sessions)
        assert outcome.action == "rejected"
        assert "locked" in outcome.message

    @pytest.mark.parametrize("screen", ACCEPTING_SCREENS)
    def test_locked_session_read_shows_the_typed_message(self, sessions, screen):
        session = sessions.create_session("email", FILES)
        for _ in range(MAX_FAILED_ATTEMPTS):
            sessions.verify_otp(session.session_id, _wrong_otp(session))
        outcome = decide_redemption(_read(session), screen, sessions)
        assert outcome.action == "rejected"
        assert outcome.message == "Session locked after too many failed attempts"

    def test_expired_session_shows_the_typed_message(self, sessions):
        session = sessions.create_session("wifi", FILES)
        sessions.db_manager.conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            (datetime.now() - timedelta(minutes=1), session.session_id))
        outcome = decide_redemption(_read(session), "idle", sessions)
        assert (outcome.action, outcome.message) == ("rejected", "Session expired")

    @pytest.mark.parametrize("screen", ACCEPTING_SCREENS)
    def test_used_session_is_rejected_like_a_typed_code(self, sessions, screen):
        session = sessions.create_session("wifi", FILES)
        assert decide_redemption(_read(session), "idle", sessions).action == "open_files"
        outcome = decide_redemption(_read(session), screen, sessions)
        assert (outcome.action, outcome.message) == ("rejected", "Incorrect or expired code")

    @pytest.mark.parametrize("screen", ACCEPTING_SCREENS)
    def test_scanner_source_rejected_without_an_attempt(self, sessions, screen):
        session = sessions.create_session("scanner", FILES)
        for otp in (session.otp, _wrong_otp(session)):
            outcome = decide_redemption(_read(session, otp=otp), screen, sessions)
            assert (outcome.action, outcome.message) == ("rejected", MSG_CANT_USE_HERE)
        assert _failed_attempts(sessions, session) == 0
        assert sessions.db_manager.get_session(session.session_id)['status'] == "pending"

    def test_unknown_session_gets_the_typed_message(self, sessions):
        read = classify_payload("f" * 16 + ":123456")
        outcome = decide_redemption(read, "idle", sessions)
        assert (outcome.action, outcome.message) == ("rejected", "Incorrect or expired code")

    @pytest.mark.parametrize("screen", ACCEPTING_SCREENS)
    def test_malformed_says_type_your_code_and_counts_nothing(self, sessions, screen):
        session = sessions.create_session("wifi", FILES)
        outcome = decide_redemption(classify_payload("garbage"), screen, sessions)
        assert (outcome.action, outcome.message) == ("rejected", MSG_CANT_READ)
        assert _failed_attempts(sessions, session) == 0

    @pytest.mark.parametrize("screen", ACCEPTING_SCREENS)
    def test_voucher_says_vouchers_are_for_payment(self, sessions, screen):
        outcome = decide_redemption(classify_payload("V1:ABC"), screen, sessions)
        assert (outcome.action, outcome.message) == ("rejected", MSG_VOUCHER_AT_PAYMENT)

    @pytest.mark.parametrize("screen", ["usb", "file_browser", "printing_options",
                                        "payment", "admin", "thank_you", "scanner",
                                        "scan_destination", "scan_result", "data_viewer"])
    def test_mid_flow_screens_ignore_every_read_silently(self, sessions, screen):
        session = sessions.create_session("wifi", FILES)
        for text in (f"{session.session_id}:{session.otp}", "garbage", "V1:ABC"):
            outcome = decide_redemption(classify_payload(text), screen, sessions)
            assert outcome.action == "ignore"
            assert outcome.message is None
        assert sessions.db_manager.get_session(session.session_id)['status'] == "pending"


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class TestDuplicateReadFilter:
    def test_first_read_passes(self):
        assert not DuplicateReadFilter(clock=FakeClock()).is_duplicate("abc")

    def test_identical_read_within_window_is_suppressed(self):
        clock = FakeClock()
        reads = DuplicateReadFilter(window_seconds=3, clock=clock)
        reads.is_duplicate("abc")
        clock.now += 2.9
        assert reads.is_duplicate("abc")

    def test_identical_read_after_window_passes(self):
        clock = FakeClock()
        reads = DuplicateReadFilter(window_seconds=3, clock=clock)
        reads.is_duplicate("abc")
        clock.now += 3.1
        assert not reads.is_duplicate("abc")

    def test_different_payload_passes(self):
        reads = DuplicateReadFilter(clock=FakeClock())
        reads.is_duplicate("abc")
        assert not reads.is_duplicate("abd")

    def test_repeat_after_another_payload_within_window_is_suppressed(self):
        clock = FakeClock()
        reads = DuplicateReadFilter(window_seconds=3, clock=clock)
        reads.is_duplicate("abc")
        clock.now += 1.0
        assert not reads.is_duplicate("xyz")
        clock.now += 1.0
        assert reads.is_duplicate("abc")
        clock.now += 1.1  # 3.1s after the first "abc"
        assert not reads.is_duplicate("abc")

    def test_suppressed_repeats_do_not_extend_the_window(self):
        clock = FakeClock()
        reads = DuplicateReadFilter(window_seconds=3, clock=clock)
        reads.is_duplicate("abc")
        for _ in range(2):
            clock.now += 1.0
            assert reads.is_duplicate("abc")
        clock.now += 1.1  # 3.1s after the first read, 1.1s after the last repeat
        assert not reads.is_duplicate("abc")
