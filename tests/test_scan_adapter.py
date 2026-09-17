"""
Tests for ScanAdapter — pure logic, no FastAPI/HTTP or hardware involved.
Wired to a real SessionManager backed by the same in-memory FakeDBManager
used in test_session_manager.py / test_wifi_adapter.py.
"""
import os

from managers.adapters.scan_adapter import ScanAdapter
from managers.session_manager import SessionManager
from tests.test_session_manager import FakeDBManager

PDF_BYTES = b"%PDF-1.4 fake scanned pdf content"


def _make_adapter(tmp_path):
    db = FakeDBManager()
    session_manager = SessionManager(db)
    upload_dir = str(tmp_path / "scan_uploads")
    adapter = ScanAdapter(session_manager, upload_dir)
    return adapter, db, upload_dir


class TestHandleScan:
    def test_accepts_valid_pdf_and_copies_it(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        source = tmp_path / "composed.pdf"
        source.write_bytes(PDF_BYTES)

        success, message, session = adapter.handle_scan(str(source), filename="Scan_1.pdf")

        assert success is True
        assert session is not None
        assert session.files[0]['original_filename'] == "Scan_1.pdf"
        assert os.path.dirname(session.files[0]['path']) == upload_dir
        # Copied, not moved — the source file must still exist.
        assert source.exists()
        with open(session.files[0]['path'], "rb") as f:
            assert f.read() == PDF_BYTES

    def test_creates_source_scan_session(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        source = tmp_path / "composed.pdf"
        source.write_bytes(PDF_BYTES)

        success, message, session = adapter.handle_scan(str(source))

        assert db.sessions[session.session_id]['source'] == "scan"

    def test_defaults_filename_when_not_given(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        source = tmp_path / "composed.pdf"
        source.write_bytes(PDF_BYTES)

        success, message, session = adapter.handle_scan(str(source))

        assert session.files[0]['original_filename'] == "scan.pdf"

    def test_rejects_missing_file(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_scan(str(tmp_path / "does_not_exist.pdf"))
        assert success is False
        assert session is None

    def test_rejects_missing_pdf_magic_bytes(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        source = tmp_path / "not_a_pdf.pdf"
        source.write_bytes(b"not actually a pdf")

        success, message, session = adapter.handle_scan(str(source))

        assert success is False
        assert session is None

    def test_creates_upload_dir_if_missing(self, tmp_path):
        upload_dir = str(tmp_path / "nested" / "scan_uploads")
        db = FakeDBManager()
        ScanAdapter(SessionManager(db), upload_dir)
        assert os.path.isdir(upload_dir)
