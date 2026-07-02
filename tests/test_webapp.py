"""
Tests for the FastAPI skeleton (webapp/main.py) — TestClient drives the app
in-process (no real Uvicorn socket needed), so this runs offline like the
rest of the suite.
"""
from fastapi.testclient import TestClient

from SSP.webapp.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_availability_matches_config():
    # app.docs_url is fixed at import time from config.docs_enabled, so
    # rather than fake a different .env mid-test, just assert the live
    # app's /docs status agrees with whatever the current config says.
    from SSP.config import get_config

    expected_status = 200 if get_config().docs_enabled else 404
    assert client.get("/docs").status_code == expected_status
