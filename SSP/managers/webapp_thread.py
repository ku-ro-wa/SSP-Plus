# managers/webapp_thread.py
#
# Runs the FastAPI Wi-Fi upload portal (webapp.main:app) on a background
# thread inside the kiosk process. Same start()/stop() shape as the other
# thread managers so it drops into main_app.py's __init__/cleanup().
#
# TLS: project_objectives.txt module 5 wants the portal served over HTTPS
# (self-signed cert, since it's only ever reached at a LAN IP). from_config()
# turns that on only when WIFI_TLS_CERTFILE / WIFI_TLS_KEYFILE both point at
# files that exist — otherwise it falls back to plain HTTP so a zero-setup
# `make run-sim` still serves the portal. Run scripts/generate_tls_cert.py
# to produce the cert/key pair.
#
# With the hotspot on, a second, plain-HTTP server answers the OSes'
# captive-portal checks (webapp/captive.py, ADR 0008) on WIFI_CAPTIVE_PORT.

import os
import socket
import threading
from typing import Optional

import uvicorn

from config import get_config
from webapp.captive import make_captive_app
from webapp.main import app

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000


def _missing_tls_files() -> list:
    """Configured cert/key paths that don't exist on disk (empty == TLS ready)."""
    config = get_config()
    return [
        p for p in (config.wifi_tls_certfile, config.wifi_tls_keyfile)
        if not (p and os.path.isfile(p))
    ]


def _lan_ip() -> str:
    """Best-guess LAN address of this machine. No packets are sent — a UDP
    connect() just picks the outbound interface — and it falls back to
    loopback when there's no route (offline laptop)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _portal_url(path: str, host: Optional[str] = None, tls: Optional[bool] = None) -> str:
    """
    The URL a phone on the same network types to reach a given portal path.

    `tls` should be the running server's actual state
    (WebAppThreadManager.tls_enabled) so the kiosk hint can't disagree with
    the server; when it's None (standalone callers, tests) the scheme is
    inferred from whether the cert/key files are present.
    """
    if tls is None:
        tls = not _missing_tls_files()
    scheme = "https" if tls else "http"
    return f"{scheme}://{host or _lan_ip()}:{get_config().wifi_portal_port}{path}"


def wifi_portal_url(host: Optional[str] = None, tls: Optional[bool] = None) -> str:
    """The URL a phone types to reach the upload portal (Wi-Fi/email intake)."""
    return _portal_url("/upload", host, tls)


def scan_redeem_portal_url(host: Optional[str] = None, tls: Optional[bool] = None) -> str:
    """The URL a phone types to redeem a scan-to-Wi-Fi/email session (see
    webapp/routers/redeem.py and screens/scan_result)."""
    return _portal_url("/redeem", host, tls)


class WebAppThreadManager:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, ssl_certfile=None, ssl_keyfile=None,
                 captive_port=None):
        self.tls_enabled = bool(ssl_certfile and ssl_keyfile)
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        self.thread = None

        # Every OS sign-in window lands on the upload page, by its permanent name.
        self.captive_server = None
        self.captive_thread = None
        if captive_port:
            portal = wifi_portal_url(host=get_config().portal_hostname, tls=self.tls_enabled)
            self.captive_server = uvicorn.Server(uvicorn.Config(
                make_captive_app(portal), host=host, port=captive_port, log_level="warning",
            ))

    @classmethod
    def from_config(cls) -> "WebAppThreadManager":
        """
        Build the manager from .env, enabling TLS only when both
        WIFI_TLS_CERTFILE and WIFI_TLS_KEYFILE resolve to files that exist.
        Anything else -> plain HTTP, with one line naming the missing path(s).
        """
        config = get_config()
        missing = _missing_tls_files()
        captive_port = config.wifi_captive_port if config.wifi_hotspot_enabled else None

        if not missing:
            print(f"🔒 Wi-Fi portal serving HTTPS (cert: {config.wifi_tls_certfile})")
            return cls(
                port=config.wifi_portal_port,
                ssl_certfile=config.wifi_tls_certfile,
                ssl_keyfile=config.wifi_tls_keyfile,
                captive_port=captive_port,
            )

        print(
            f"⚠️ Wi-Fi portal serving plain HTTP — TLS cert/key not found "
            f"({', '.join(missing)}). Run scripts/generate_tls_cert.py to enable HTTPS."
        )
        return cls(port=config.wifi_portal_port, captive_port=captive_port)

    def start(self):
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        if self.captive_server:
            self.captive_thread = threading.Thread(target=self.captive_server.run, daemon=True)
            self.captive_thread.start()

    def stop(self):
        for server, thread in ((self.server, self.thread), (self.captive_server, self.captive_thread)):
            if server:
                server.should_exit = True
            if thread and thread.is_alive():
                thread.join(timeout=1.0)
