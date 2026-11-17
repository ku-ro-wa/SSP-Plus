# Issue #162: security headers and a strict Content-Security-Policy on the
# Admin Dashboard. Headers are checked through real requests (TestClient);
# the templates are checked for anything the CSP would block.

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from SSP.admin_dashboard.main import app
from admin_dashboard.cli import create_account
from admin_dashboard.dependencies import get_db
from admin_dashboard.security_headers import CONTENT_SECURITY_POLICY
from database.db_manager import DatabaseManager
from database.models import init_db

DASHBOARD = Path(__file__).resolve().parent.parent / "SSP" / "admin_dashboard"
TEMPLATES = sorted((DASHBOARD / "templates").glob("*.html"))
PAGES = ["/kiosk", "/accounting", "/logs", "/settings"]


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "dashboard.db")
    init_db(path)
    manager = DatabaseManager(db_path=path)
    yield manager
    manager.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, db, role="admin"):
    create_account(db, "sam", "s3cret!", role)
    assert client.post("/login", json={"username": "sam", "password": "s3cret!"}).status_code == 200


def assert_security_headers(response):
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_csp_allows_no_inline_code():
    assert "script-src 'self';" in CONTENT_SECURITY_POLICY + ";"
    assert "style-src 'self';" in CONTENT_SECURITY_POLICY + ";"
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert "unsafe-eval" not in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY


def test_login_page_has_the_headers_and_no_store(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert_security_headers(response)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("role", ["admin", "operator"])
@pytest.mark.parametrize("path", PAGES)
def test_signed_in_pages_have_the_headers_and_no_store(client, db, role, path):
    login(client, db, role)
    response = client.get(path)
    assert response.status_code == 200
    assert_security_headers(response)
    assert response.headers["cache-control"] == "no-store"


def test_json_and_redirects_have_the_headers(client, db):
    assert_security_headers(client.get("/kiosk", follow_redirects=False))  # 303 to /login
    login(client, db)
    response = client.get("/accounting/data?range=all")
    assert response.status_code == 200
    assert_security_headers(response)
    assert response.headers["cache-control"] == "no-store"


def test_static_files_have_the_headers_but_may_be_cached(client):
    for path in ("/static/css/dashboard.css", "/static/js/login.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert_security_headers(response)
        assert "no-store" not in response.headers.get("cache-control", "")


def test_every_script_and_stylesheet_a_page_loads_exists(client, db):
    login(client, db)
    pages = [client.get(p).text for p in PAGES]
    client.cookies.clear()
    pages.append(client.get("/login").text)
    for html in pages:
        for src in re.findall(r'<(?:script[^>]*\bsrc|link[^>]*\bhref)="(/static/[^"]+)"', html):
            assert client.get(src).status_code == 200, src


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_has_nothing_the_csp_blocks(template):
    html = template.read_text()
    assert "<style" not in html, "inline <style> block"
    assert not re.search(r"\sstyle\s*=", html), "style= attribute"
    assert not re.search(r"\son[a-z]+\s*=", html), "inline on*= handler"
    assert "javascript:" not in html.lower()
    for tag in re.findall(r"<script\b[^>]*>", html):
        # Only external scripts or inert JSON data blocks.
        assert 'src="/static/' in tag or 'type="application/json"' in tag, tag
    for body in re.findall(r"<script\b(?![^>]*application/json)[^>]*>(.*?)</script>", html, re.S):
        assert body.strip() == "", "inline script code"


def test_ink_bar_is_drawn_without_a_style_attribute(client, db):
    db.update_cmyk_ink_levels(87.5, 30, 10, 0)
    login(client, db)
    html = client.get("/kiosk").text
    assert '<rect height="100%" width="88%"/>' in html  # levels show rounded
    assert '<rect height="100%" width="0%"/>' in html
    assert not re.search(r"\sstyle\s*=", html)
