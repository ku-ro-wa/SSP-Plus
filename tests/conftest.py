import sys
import os

# Make SSP/ importable so tests can import managers and database modules directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'SSP')))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_upload_guard():
    """Each test gets a fresh Portal upload guard, so POSTs to /upload in one test
    don't use up another's per-phone limit, and free storage on the test machine
    doesn't matter. tests/test_upload_guard.py builds its own guards."""
    from webapp.upload_guard import UploadGuard
    for name in ("webapp.main", "SSP.webapp.main"):
        module = sys.modules.get(name)
        if module is not None:
            module.upload_guard = UploadGuard("unused", free_bytes=lambda _path: 1 << 50)
    yield
