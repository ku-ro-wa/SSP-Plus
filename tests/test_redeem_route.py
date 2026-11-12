"""
Integration tests for GET/POST /redeem and its follow-up actions
(/redeem/download, /redeem/email) — drives the FastAPI routes in-process via
TestClient. get_session_manager/get_smtp_client/get_db are overridden with
ones wired to the same in-memory FakeDBManager/FakeSmtpClient used elsewhere,
so no real filesystem session, SQLite DB, or SMTP server is touched, and the
per-client wrong-code limit (#104) is swapped for a fresh one on a fake clock.
"""
from SSP.webapp.main import app
from fastapi.testclient import TestClient
from webapp.dependencies import get_db, get_pickup_code_limiter, get_session_manager, get_smtp_client
from webapp.rate_limit import MAX_ATTEMPTS, WINDOW_SECONDS, ClientAttemptLimiter

from managers.session_manager import SessionManager
from tests.test_email_adapter import FakeSmtpClient
from tests.test_session_manager import FakeDBManager

PDF_BYTES = b"%PDF-1.4 fake scanned pdf content"

client = TestClient(app)


def _override_session_manager(db):
    def _get():
        yield SessionManager(db)
    return _get


def _override_smtp_client(smtp):
    def _get():
        yield smtp
    return _get


def _make_scan_session(tmp_path, db):
    """Registers a source='scanner' session the same way ScanAdapter does,
    without going through the adapter itself."""
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    session_manager = SessionManager(db)
    return session_manager.create_session(
        source="scanner",
        files=[{"path": str(pdf_path), "original_filename": "Scan_1.pdf"}],
    )


class TestRedeemForm:
    def test_get_redeem_returns_form(self):
        response = client.get("/redeem")
        assert response.status_code == 200
        assert "<form" in response.text


class TestPostRedeem:
    def test_valid_otp_shows_actions_page(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        try:
            response = client.post("/redeem", data={"otp": session.otp})
        finally:
            app.dependency_overrides.pop(get_session_manager, None)

        assert response.status_code == 200
        assert "Scan_1.pdf" in response.text
        assert f'value="{session.session_id}"' in response.text

    def test_the_same_code_works_a_second_time(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        try:
            first = client.post("/redeem", data={"otp": session.otp})
            second = client.post("/redeem", data={"otp": session.otp})
        finally:
            app.dependency_overrides.pop(get_session_manager, None)

        assert first.status_code == 200
        assert second.status_code == 200
        assert "Scan_1.pdf" in second.text

    def test_invalid_otp_returns_400(self, tmp_path):
        db = FakeDBManager()
        _make_scan_session(tmp_path, db)
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        try:
            response = client.post("/redeem", data={"otp": "000000"})
        finally:
            app.dependency_overrides.pop(get_session_manager, None)

        assert response.status_code == 400


class TestRedeemDownload:
    def test_valid_session_streams_pdf(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        try:
            response = client.post(
                "/redeem/download",
                data={"session_id": session.session_id, "otp": session.otp},
            )
        finally:
            app.dependency_overrides.pop(get_session_manager, None)

        assert response.status_code == 200
        assert response.content == PDF_BYTES

    def test_wrong_session_id_returns_400(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        try:
            response = client.post(
                "/redeem/download",
                data={"session_id": "does-not-exist", "otp": session.otp},
            )
        finally:
            app.dependency_overrides.pop(get_session_manager, None)

        assert response.status_code == 400

    def test_a_used_session_needs_its_code(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        wrong = "000000" if session.otp != "000000" else "000001"
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        try:
            client.post("/redeem", data={"otp": session.otp})
            response = client.post(
                "/redeem/download",
                data={"session_id": session.session_id, "otp": wrong},
            )
        finally:
            app.dependency_overrides.pop(get_session_manager, None)

        assert response.status_code == 400
        assert response.content != PDF_BYTES


class TestRedeemEmail:
    def test_sends_pdf_attachment_to_recipient(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        smtp = FakeSmtpClient()
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        app.dependency_overrides[get_smtp_client] = _override_smtp_client(smtp)
        try:
            response = client.post(
                "/redeem/email",
                data={
                    "session_id": session.session_id,
                    "otp": session.otp,
                    "recipient": "student@example.com",
                },
            )
        finally:
            app.dependency_overrides.pop(get_session_manager, None)
            app.dependency_overrides.pop(get_smtp_client, None)

        assert response.status_code == 200
        assert "student@example.com" in response.text
        assert len(smtp.sent) == 1
        sent_msg = smtp.sent[0]
        assert sent_msg["To"] == "student@example.com"
        attachments = list(sent_msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_content() == PDF_BYTES

    def test_download_then_email_both_succeed_with_same_hidden_fields(self, tmp_path):
        """Exercises the 'already verified' re-auth path both follow-up
        actions rely on (see managers/session_manager.py:verify_otp)."""
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)
        smtp = FakeSmtpClient()
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        app.dependency_overrides[get_smtp_client] = _override_smtp_client(smtp)
        try:
            download_response = client.post(
                "/redeem/download",
                data={"session_id": session.session_id, "otp": session.otp},
            )
            email_response = client.post(
                "/redeem/email",
                data={
                    "session_id": session.session_id,
                    "otp": session.otp,
                    "recipient": "student@example.com",
                },
            )
        finally:
            app.dependency_overrides.pop(get_session_manager, None)
            app.dependency_overrides.pop(get_smtp_client, None)

        assert download_response.status_code == 200
        assert email_response.status_code == 200
        assert len(smtp.sent) == 1

    def test_smtp_failure_returns_502_with_error(self, tmp_path):
        db = FakeDBManager()
        session = _make_scan_session(tmp_path, db)

        class ExplodingSmtpClient:
            def send(self, msg):
                raise RuntimeError("connection refused")

        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        app.dependency_overrides[get_smtp_client] = _override_smtp_client(ExplodingSmtpClient())
        try:
            response = client.post(
                "/redeem/email",
                data={
                    "session_id": session.session_id,
                    "otp": session.otp,
                    "recipient": "student@example.com",
                },
            )
        finally:
            app.dependency_overrides.pop(get_session_manager, None)
            app.dependency_overrides.pop(get_smtp_client, None)

        assert response.status_code == 502


class Clock:
    """Monotonic seconds, as webapp.rate_limit's window expects."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _override_limiter(limiter):
    def _get():
        return limiter
    return _get


def _override_db(db):
    def _get():
        yield db
    return _get


class TestRedeemWrongCodeLimit:
    """The Portal's pick-up code is 6 digits on an unauthenticated page, so one
    client's repeated wrong codes have to stop being free (issue #104)."""

    def _post(self, db, limiter, otp, tmp_path):
        _make_scan_session(tmp_path, db)
        app.dependency_overrides[get_session_manager] = _override_session_manager(db)
        app.dependency_overrides[get_pickup_code_limiter] = _override_limiter(limiter)
        app.dependency_overrides[get_db] = _override_db(db)
        try:
            return client.post("/redeem", data={"otp": otp})
        finally:
            for dependency in (get_session_manager, get_pickup_code_limiter, get_db):
                app.dependency_overrides.pop(dependency, None)

    def test_repeated_wrong_codes_get_429(self, tmp_path):
        db = FakeDBManager()
        limiter = ClientAttemptLimiter(clock=Clock())

        for _ in range(MAX_ATTEMPTS - 1):
            assert self._post(db, limiter, "000000", tmp_path).status_code == 400
        # The attempt that trips the limit is the first refused with a 429.
        blocked = self._post(db, limiter, "000000", tmp_path)

        assert blocked.status_code == 429
        assert "Too many incorrect codes" in blocked.text
        assert int(blocked.headers["Retry-After"]) > 0
        assert self._post(db, limiter, "000000", tmp_path).status_code == 429

    def test_the_right_code_is_also_refused_while_blocked(self, tmp_path):
        db = FakeDBManager()
        limiter = ClientAttemptLimiter(clock=Clock())
        for _ in range(MAX_ATTEMPTS):
            self._post(db, limiter, "000000", tmp_path)

        session = _make_scan_session(tmp_path, db)
        response = self._post(db, limiter, session.otp, tmp_path)
        assert response.status_code == 429

    def test_a_correct_code_clears_the_client(self, tmp_path):
        db = FakeDBManager()
        limiter = ClientAttemptLimiter(clock=Clock())
        session = _make_scan_session(tmp_path, db)

        for _ in range(MAX_ATTEMPTS - 1):
            self._post(db, limiter, "000000", tmp_path)
        assert self._post(db, limiter, session.otp, tmp_path).status_code == 200

        for _ in range(MAX_ATTEMPTS - 1):
            assert self._post(db, limiter, "000000", tmp_path).status_code == 400

    def test_the_window_expires(self, tmp_path):
        db = FakeDBManager()
        clock = Clock()
        limiter = ClientAttemptLimiter(clock=clock)
        for _ in range(MAX_ATTEMPTS):
            self._post(db, limiter, "000000", tmp_path)
        assert self._post(db, limiter, "000000", tmp_path).status_code == 429

        clock.advance(WINDOW_SECONDS + 1)
        assert self._post(db, limiter, "000000", tmp_path).status_code == 400

    def test_one_error_log_row_per_lockout(self, tmp_path):
        db = FakeDBManager()
        limiter = ClientAttemptLimiter(clock=Clock())
        for _ in range(MAX_ATTEMPTS + 3):
            self._post(db, limiter, "000000", tmp_path)

        assert len(db.errors) == 1
        assert "5 wrong pickup codes" in db.errors[0][1]

    def test_clients_do_not_share_a_counter(self, tmp_path):
        db = FakeDBManager()
        limiter = ClientAttemptLimiter(clock=Clock())
        for _ in range(MAX_ATTEMPTS):
            limiter.record_failure("192.168.4.9")

        # A different phone (request.client.host under TestClient) is unaffected.
        assert self._post(db, limiter, "000000", tmp_path).status_code == 400
