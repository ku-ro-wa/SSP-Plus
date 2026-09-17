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

import os
import socket
import threading
from typing import Optional

import uvicorn

from config import get_config
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
    return f"{scheme}://{host or _lan_ip()}:{DEFAULT_PORT}{path}"


def wifi_portal_url(host: Optional[str] = None, tls: Optional[bool] = None) -> str:
    """The URL a phone types to reach the upload portal (Wi-Fi/email intake)."""
    return _portal_url("/upload", host, tls)


def scan_redeem_portal_url(host: Optional[str] = None, tls: Optional[bool] = None) -> str:
    """The URL a phone types to redeem a scan-to-Wi-Fi/email session (see
    webapp/routers/redeem.py and screens/scan_result)."""
    return _portal_url("/redeem", host, tls)


class WebAppThreadManager:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, ssl_certfile=None, ssl_keyfile=None):
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

    @classmethod
    def from_config(cls) -> "WebAppThreadManager":
        """
        Build the manager from .env, enabling TLS only when both
        WIFI_TLS_CERTFILE and WIFI_TLS_KEYFILE resolve to files that exist.
        Anything else -> plain HTTP, with one line naming the missing path(s).
        """
        config = get_config()
        missing = _missing_tls_files()

        if not missing:
            print(f"🔒 Wi-Fi portal serving HTTPS (cert: {config.wifi_tls_certfile})")
            return cls(
                ssl_certfile=config.wifi_tls_certfile,
                ssl_keyfile=config.wifi_tls_keyfile,
            )

        print(
            f"⚠️ Wi-Fi portal serving plain HTTP — TLS cert/key not found "
            f"({', '.join(missing)}). Run scripts/generate_tls_cert.py to enable HTTPS."
        )
        return cls()

    def start(self):
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
