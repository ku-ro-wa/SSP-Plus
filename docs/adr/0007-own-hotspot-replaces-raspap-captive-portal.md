# The kiosk's own hotspot (hostapd + dnsmasq) replaces the RaspAP captive portal

`project_objectives.txt` module 5 planned the Wi-Fi upload portal behind a RaspAP access point
with a captive portal (Nodogsplash/openNDS). ADR-0001 left that piece out for local development.
Testing it on the Pi showed that a captive portal doesn't fit our use: it's built to gate
internet access behind a splash page. We don't offer internet access at all, only a single
upload page, and the splash/redirect behaviour got in the way more than it helped.

This ADR replaces that plan. It's the local-only path that ships now. The public address that
comes later (ADR-0006) builds on it without changing it.

## Decisions

- **hostapd + dnsmasq + the FastAPI portal, no captive portal.** `hostapd` broadcasts the
  network. `dnsmasq` hands out addresses and answers the portal's name. Customers reach the
  portal by scanning a QR image, not through a redirect:
  - the touchscreen's Wi-Fi upload screen shows a "join this network" QR image (the standard
    `WIFI:` format phones understand), then the upload-page QR image;
  - the same upload address is printed on a sticker on the kiosk.

- **One permanent name: `print.<domain>/k/<KIOSK_ID>`.** The same address works today (locally)
  and later (publicly, ADR-0006), so stickers and bookmarks never change:
  - `dnsmasq` answers `print.<domain>` with the Pi's hotspot address;
  - each kiosk's `KIOSK_ID` comes from its `.env`.

- **A real certificate replaces the self-signed one.** Owning the domain lets each kiosk get a
  Let's Encrypt certificate for `print.<domain>` using a DNS check, which needs no public
  server. Phones stop showing ADR-0001's self-signed certificate warnings. (The DNS token this
  needs is an accepted risk; see ADR-0006's threat model.)

- **The hotspot is locked down:**
  - **Open network**, no WPA2 password. A password printed on the kiosk barely limits who can
    join, and HTTPS already protects the uploads. Adding WPA2 later costs nothing if wanted.
  - **Client isolation** (`ap_isolate`): phones on the hotspot can't see or reach each other.
  - **No forwarding to the router.** The hotspot isn't free internet on the cellular plan, and
    phones can't reach the router or anything beyond it.
  - **A firewall on `wlan0`** that allows only DHCP, DNS, and the portal's HTTPS port.
    Everything else is closed there, including SSH and the dashboard's port 8100, as a second
    barrier behind ADR-0005's loopback binding.

- **Switched on or off per kiosk, at install time only.** `WIFI_HOTSPOT_ENABLED` in `.env` drives
  three things:
  1. whether the setup script enables the `hostapd`/`dnsmasq` services;
  2. which QR images the touchscreen shows (join-Wi-Fi plus upload, or upload only);
  3. whether the portal listens on the hotspot interface.
  It's set at install or maintenance time, on the Pi or over Tailscale SSH, never from the
  dashboard (ADR-0005). Until the public address exists, every kiosk runs with it **on**. After
  that, it becomes a fallback for sites where customers lack reliable mobile data, since a
  customer at the kiosk can then use the public address over 4G instead.

- **Each kiosk is set up from `.env` plus the setup script.** Nothing is configured on the Pi by
  hand, so a second kiosk is a new `.env` (its own `KIOSK_ID` and secrets) and one run of the
  script.

- **ADR-0001's in-process portal thread is replaced as part of this rework.** The portal becomes
  its own sandboxed process (ADR-0006). The self-signed certificate setup in ADR-0001 stays for
  developer laptops, where `make run-sim` must work with no setup.

## To verify on hardware: phones that prefer mobile data

A phone that joins a Wi-Fi network with no internet may keep sending traffic, DNS lookups
included, over mobile data. Android does this when it marks a network "connected, no
internet". Such a phone never asks the hotspot's `dnsmasq` for `print.<domain>`, so the name
fails to resolve while it isn't public.

Planned fix: until the public address launches, publish `print.<domain>` in public DNS
pointing at the hotspot's **private** address. Whichever network resolves the name, the answer
is on the hotspot's own subnet, so the phone sends the connection over Wi-Fi. Things to test on
real Android and iOS phones:
- whether this works end to end;
- whether any carrier's DNS refuses private-address answers (DNS rebinding protection).

If it doesn't hold up, the fallback is to have `dnsmasq` answer the phones' connectivity-check
hosts, so they treat the hotspot as online and stop preferring mobile data while joined.

## Rejected alternatives

- **Keeping RaspAP with a captive portal.** It's designed to gate internet access, which we
  don't provide, and testing showed the redirect flow fights our QR-driven one.
- **A WPA2 password on the hotspot.** A shared password printed on the kiosk adds friction
  without real protection (see above).
- **Bare IP addresses on stickers** (e.g. `http://10.3.141.1/upload`). Every sticker would break
  the day the public address launches, and a real certificate is impossible for a bare IP.
