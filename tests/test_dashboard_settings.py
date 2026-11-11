"""/settings on the Admin Dashboard (issue #106): admin edits, operator reads."""
import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from database.db_manager import DatabaseManager
from database.models import init_db
from managers.settings_catalog import CATALOG


@pytest.fixture
def temp_db(tmp_path):
    path = str(tmp_path / "settings.db")
    init_db(path)
    db = DatabaseManager(db_path=path)
    yield db
    db.close()


@pytest.fixture
def client(temp_db):
    app.dependency_overrides[get_db] = lambda: temp_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _login(client, db, role):
    create_account(db, "u", "s3cret!", role)
    client.post("/login", json={"username": "u", "password": "s3cret!"})


def _by_key(client):
    return {s["key"]: s for s in client.get("/settings/data").json()["settings"]}


def test_requires_login(client):
    assert client.get("/settings", follow_redirects=False).status_code == 303
    assert client.get("/settings/data").status_code == 401
    assert client.post("/settings", json={"values": {}}).status_code == 401


def test_operator_reads_but_cannot_save(client, temp_db):
    _login(client, temp_db, "operator")
    page = client.get("/settings")
    assert page.status_code == 200 and "Read-only" in page.text and "<button" not in page.text
    assert set(_by_key(client)) == {s.key for s in CATALOG}
    r = client.post("/settings", json={"values": {"max_change_limit": 80}})
    assert r.status_code == 403
    assert temp_db.get_setting("max_change_limit") is None


def test_admin_page_has_form(client, temp_db):
    _login(client, temp_db, "admin")
    page = client.get("/settings").text
    assert "Read-only" not in page and "<button" in page
    assert "Voucher expiry" in page


def test_admin_save_takes_effect_immediately(client, temp_db):
    _login(client, temp_db, "admin")
    assert _by_key(client)["max_change_limit"]["value"] == 50
    r = client.post("/settings", json={"values": {"max_change_limit": "80", "voucher_expiry_days": 7}})
    assert r.status_code == 200 and r.json()["saved"] == {"max_change_limit": 80, "voucher_expiry_days": 7}
    assert temp_db.get_setting("max_change_limit") == 80
    assert _by_key(client)["voucher_expiry_days"]["value"] == 7


@pytest.mark.parametrize("bad", ["abc", "", "5.5", "-1", 99999, True])
def test_invalid_value_rejected_with_message_and_nothing_written(client, temp_db, bad):
    _login(client, temp_db, "admin")
    r = client.post("/settings", json={"values": {"voucher_expiry_days": 9, "max_change_limit": bad}})
    assert r.status_code == 422
    assert list(r.json()["errors"]) == ["max_change_limit"]
    assert r.json()["errors"]["max_change_limit"]
    # the valid sibling was not saved either
    assert temp_db.get_setting("voucher_expiry_days") == 30
    assert temp_db.get_setting("max_change_limit") is None


@pytest.mark.parametrize("key", ["vouchers_enabled", "unknown_key"])
def test_non_catalog_keys_rejected(client, temp_db, key):
    _login(client, temp_db, "admin")
    r = client.post("/settings", json={"values": {key: 0}})
    assert r.status_code == 422 and key in r.json()["errors"]
    assert temp_db.get_setting(key) in (None, 1)


def test_nav_links_to_settings(client, temp_db):
    _login(client, temp_db, "operator")
    assert 'href="/settings"' in client.get("/kiosk").text
