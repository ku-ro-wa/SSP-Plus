"""
Integration tests for GET/POST /upload — drives the FastAPI route in-process
via TestClient (no real Uvicorn socket). The get_wifi_adapter dependency is
overridden with one wired to a temp dir and the same in-memory FakeDBManager
used elsewhere, so no real filesystem location or SQLite DB is touched.
"""
from SSP.webapp.main import app
from fastapi.testclient import TestClient
from webapp.dependencies import get_wifi_adapter

from managers.adapters.wifi_adapter import WifiAdapter
from managers.session_manager import SessionManager
from tests.test_session_manager import FakeDBManager

PDF_BYTES = b"%PDF-1.4 fake pdf content"

client = TestClient(app)


def _override_with_temp_adapter(tmp_path):
    db = FakeDBManager()
    adapter = WifiAdapter(SessionManager(db), str(tmp_path / "uploads"), 1024 * 1024)

    def _get():
        yield adapter

    return _get


class TestUploadForm:
    def test_get_upload_returns_form(self):
        response = client.get("/upload")
        assert response.status_code == 200
        assert "<form" in response.text


class TestPostUpload:
    def test_valid_pdf_returns_otp_and_qr(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files={"file": ("document.pdf", PDF_BYTES, "application/pdf")},
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 200
        assert "Code:" in response.text
        assert "data:image/png;base64," in response.text

    def test_non_pdf_rejected_with_400(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files={"file": ("document.png", b"not a pdf", "image/png")},
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 400

    def test_fake_pdf_extension_without_magic_bytes_rejected(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files={"file": ("document.pdf", b"not really a pdf", "application/pdf")},
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 400
