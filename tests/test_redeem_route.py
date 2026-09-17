"""
Integration tests for GET/POST /redeem and its follow-up actions
(/redeem/download, /redeem/email) — drives the FastAPI routes in-process via
TestClient. get_session_manager/get_smtp_client are overridden with ones
wired to the same in-memory FakeDBManager/FakeSmtpClient used elsewhere, so
no real filesystem session, SQLite DB, or SMTP server is touched.
"""
from SSP.webapp.main import app
from fastapi.testclient import TestClient
from webapp.dependencies import get_session_manager, get_smtp_client

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
    """Registers a source='scan' session the same way ScanAdapter does,
    without going through the adapter itself."""
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    session_manager = SessionManager(db)
    return session_manager.create_session(
        source="scan",
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
