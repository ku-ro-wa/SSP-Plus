# webapp/captive.py
#
# Captive-portal detection for the kiosk hotspot (ADR 0008). There is no
# captive portal gating anything: the hotspot has no internet to gate. This
# only answers the "am I online?" checks phones and laptops make when they
# join a network, so the OS opens the upload page by itself:
#
#   1. dnsmasq answers every name with the Pi (setup_hotspot.py), and the
#      firewall sends the hotspot's port 80 here.
#   2. A device that hasn't opened the Portal yet gets a redirect to /upload
#      for every request, probes included -> the OS shows its sign-in window.
#   3. Any Portal request marks that device's IP as released (webapp/main.py).
#      From then on its probes get the "online" answer each OS expects, so the
#      OS stops treating the Wi-Fi as captive, closes or relabels the sign-in
#      window, and doesn't push traffic over mobile data instead.
#
# Served by its own plain-HTTP Uvicorn server (WebAppThreadManager), since OS
# probes are plain HTTP on port 80 and the Portal may be on HTTPS.

import threading
import time
from typing import Callable, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response

# Same as the hotspot's DHCP lease (setup_hotspot.render_dnsmasq), so a
# released IP doesn't outlive the device it was released for by much.
RELEASE_SECONDS = 60 * 60

_APPLE_SUCCESS = "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"

# Probe path -> (status, body) the OS treats as "online". Hosts aren't
# checked: every name resolves to the Pi, and no other site is served here.
PROBE_ONLINE = {
    "/generate_204": (204, ""),                           # Android, ChromeOS, Chrome
    "/gen_204": (204, ""),                                # Android (older)
    "/hotspot-detect.html": (200, _APPLE_SUCCESS),        # iOS, macOS
    "/library/test/success.html": (200, _APPLE_SUCCESS),  # iOS (older)
    "/connecttest.txt": (200, "Microsoft Connect Test"),  # Windows 10/11
    "/ncsi.txt": (200, "Microsoft NCSI"),                 # Windows (older)
    "/success.txt": (200, "success\n"),                   # Firefox
}

_NO_STORE = {"Cache-Control": "no-store"}


class CaptiveClients:
    """Device IPs that have opened the Portal, each released for a while.

    Shared by the Portal's and the probe responder's Uvicorn threads, hence
    the lock."""

    def __init__(self, ttl: float = RELEASE_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._released: Dict[str, float] = {}
        self._lock = threading.Lock()

    def release(self, ip: Optional[str]) -> None:
        if not ip:
            return
        with self._lock:
            now = self._clock()
            self._released = {k: t for k, t in self._released.items() if t > now}
            self._released[ip] = now + self._ttl

    def is_released(self, ip: Optional[str]) -> bool:
        with self._lock:
            return bool(ip) and self._released.get(ip, 0) > self._clock()


captive_clients = CaptiveClients()


def make_captive_app(portal_url: str, clients: CaptiveClients = captive_clients) -> FastAPI:
    """The probe responder: every path, every host, GET or HEAD."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def answer(request: Request, path: str):
        online = PROBE_ONLINE.get("/" + path)
        if online and clients.is_released(request.client.host if request.client else None):
            status, body = online
            return Response(body, status_code=status, media_type="text/html", headers=_NO_STORE)
        # 302, not 301: a cached permanent redirect would outlive the release.
        return RedirectResponse(portal_url, status_code=302, headers=_NO_STORE)

    return app
