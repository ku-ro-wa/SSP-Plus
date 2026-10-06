# Wi-Fi portal served by the in-process Uvicorn thread with self-signed TLS

> **Superseded for the Pi deployment (2026-10-06)** by ADR-0007 (own hotspot with hostapd +
> dnsmasq, no RaspAP captive portal, real certificate) and ADR-0006 (the portal becomes its own
> sandboxed process). The self-signed TLS setup below still applies to developer laptops.

`project_objectives.txt` module 5 specifies the Wi-Fi upload portal behind a RaspAP access
point with a Nodogsplash captive portal, on a TLS-secured Uvicorn instance. For local
end-to-end development we serve the portal from the Uvicorn instance that
`WebAppThreadManager` already runs inside the kiosk process, reached directly at
`https://<host>:8000/upload`, with TLS from a locally generated self-signed cert
(`scripts/generate_tls_cert.py`) that is wired in only when `WIFI_TLS_CERTFILE` /
`WIFI_TLS_KEYFILE` are set — otherwise the server falls back to plain HTTP so a
zero-setup `make run-sim` still works.

We chose this because RaspAP + Nodogsplash is Raspberry-Pi-only infrastructure that cannot
run or be tested on the dev laptops, and the three developers need the upload workflow
runnable without kiosk hardware. The captive-portal layer and a real cert story remain
future work for the Pi deployment; a reader who compares the objectives doc to the code
should expect the AP/captive-portal piece to be simply absent for now, not removed on
purpose.
