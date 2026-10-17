"""
Tests for webapp/captive.py, the captive-portal probe responder (ADR 0008),
and the Portal middleware that releases a device once it opens the Portal.
TestClient drives both apps in-process, so no socket is opened.
"""
import pytest
from fastapi.testclient import TestClient

from managers.webapp_thread import WebAppThreadManager
from webapp.captive import PROBE_ONLINE, CaptiveClients, captive_clients, make_captive_app
from webapp.main import app as portal_app

PORTAL = "http://print.aio-spark.example:8000/upload"
PHONE = "10.3.141.23"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _probe_client(clients, ip=PHONE):
    # TestClient's client= sets request.client, which is how a real phone's IP arrives.
    return TestClient(make_captive_app(PORTAL, clients), client=(ip, 50000), follow_redirects=False)


class TestCaptiveClients:
    def test_unknown_device_is_not_released(self):
        assert not CaptiveClients().is_released(PHONE)

    def test_release_lasts_until_the_ttl(self):
        clock = FakeClock()
        clients = CaptiveClients(ttl=60, clock=clock)
        clients.release(PHONE)
        clock.now += 59
        assert clients.is_released(PHONE)
        clock.now += 2
        assert not clients.is_released(PHONE)

    def test_release_is_per_device(self):
        clients = CaptiveClients()
        clients.release(PHONE)
        assert not clients.is_released("10.3.141.24")

    def test_missing_ip_is_ignored(self):
        clients = CaptiveClients()
        clients.release(None)
        assert not clients.is_released(None)


class TestProbeResponder:
    @pytest.mark.parametrize("path", sorted(PROBE_ONLINE))
    def test_new_device_is_sent_to_the_portal(self, path):
        response = _probe_client(CaptiveClients()).get(path, headers={"Host": "captive.apple.com"})
        assert response.status_code == 302
        assert response.headers["location"] == PORTAL
        assert response.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize("path", sorted(PROBE_ONLINE))
    def test_released_device_is_told_it_is_online(self, path):
        clients = CaptiveClients()
        clients.release(PHONE)
        response = _probe_client(clients).get(path)
        status, body = PROBE_ONLINE[path]
        assert response.status_code == status
        assert response.text == body

    def test_apple_success_page_is_exact(self):
        clients = CaptiveClients()
        clients.release(PHONE)
        body = _probe_client(clients).get("/hotspot-detect.html").text
        assert body == "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"

    def test_head_requests_are_answered(self):
        response = _probe_client(CaptiveClients()).head("/generate_204")
        assert response.status_code == 302

    def test_anything_else_typed_on_the_hotspot_goes_to_the_portal(self):
        # A released device typing http://print.aio-spark.example (no port) still lands on /upload.
        clients = CaptiveClients()
        clients.release(PHONE)
        response = _probe_client(clients).get("/", headers={"Host": "print.aio-spark.example"})
        assert response.status_code == 302
        assert response.headers["location"] == PORTAL

    def test_release_of_one_device_does_not_release_another(self):
        clients = CaptiveClients()
        clients.release(PHONE)
        assert _probe_client(clients, ip="10.3.141.99").get("/generate_204").status_code == 302


class TestPortalReleasesDevice:
    def test_opening_the_portal_releases_the_device(self):
        ip = "10.3.141.77"
        assert not captive_clients.is_released(ip)
        TestClient(portal_app, client=(ip, 50000)).get("/health")
        assert captive_clients.is_released(ip)


class TestThreadManager:
    def test_probe_responder_only_with_the_hotspot_on(self, monkeypatch):
        monkeypatch.setenv("WIFI_HOTSPOT_ENABLED", "false")
        assert WebAppThreadManager.from_config().captive_server is None

        monkeypatch.setenv("WIFI_HOTSPOT_ENABLED", "true")
        monkeypatch.setenv("WIFI_CAPTIVE_PORT", "8081")
        manager = WebAppThreadManager.from_config()
        assert manager.captive_server.config.port == 8081

    def test_probe_redirect_uses_the_portal_name_and_scheme(self, monkeypatch):
        monkeypatch.setenv("WIFI_HOTSPOT_ENABLED", "true")
        monkeypatch.setenv("PORTAL_HOSTNAME", "print.kiosk.example")
        monkeypatch.setenv("WIFI_PORTAL_PORT", "8000")
        monkeypatch.setenv("WIFI_TLS_CERTFILE", "/nonexistent/cert.pem")
        manager = WebAppThreadManager.from_config()

        probe = TestClient(manager.captive_server.config.app, follow_redirects=False)
        assert probe.get("/generate_204").headers["location"] == "http://print.kiosk.example:8000/upload"
