# Captive-portal detection opens the Portal, with no splash page

> **Proposed (2026-10-12).** Waiting on supervisor review and testing on real phones and
> laptops (see "To verify on hardware"). Changes part of ADR-0007; see "What this changes".

ADR-0007 reached the **Portal** by QR image and a sticker naming `print.<domain>`. Two things
have changed since:

- **No domain.** Our supervisor turned down buying one because of the extra cost to the
  operator. ADR-0007's permanent `print.<domain>` name, its Let's Encrypt certificate and its
  public-DNS fix for phones that prefer mobile data all depended on owning one.
- **Laptops need a way in.** A laptop can't scan the kiosk's QR image. Our supervisor proposed
  openNDS: join the **Hotspot**, get a captive-portal splash page, press "Continue", land on
  the upload page.

## Decisions

- **Use captive-portal detection, without a captive portal.** Every OS checks whether it's
  online when it joins Wi-Fi, by fetching a known plain-HTTP address. If that fetch is
  redirected, the OS opens a sign-in window on the redirect target. So we:
  1. have `dnsmasq` answer every name with the Pi (`address=/#/`), so the checks reach the Pi;
  2. redirect the Hotspot's port 80 on the Pi to a small plain-HTTP **probe responder**
     (`webapp/captive.py`, port `WIFI_CAPTIVE_PORT`, default 8080);
  3. have the probe responder send every request from a device that hasn't opened the Portal
     yet to `/upload`, so the OS's sign-in window opens straight onto the upload page;
  4. release a device as soon as it makes any request to the Portal. From then on its checks
     get the exact "online" reply its OS expects (Android/Chrome `204`, Apple's `Success` page,
     Windows' `Microsoft Connect Test`/`Microsoft NCSI`, Firefox's `success`).

  Step 4 does the one useful thing openNDS's "Continue" button does: once released, the OS
  stops treating the network as captive and has no reason to push traffic over mobile data.
  But the user doesn't have to press anything first.

- **No openNDS.** Its main job is a firewall that holds back internet access until the user
  presses "Continue". The Hotspot has no internet to hold back, so that machinery would sit
  unused, and its splash page is an extra tap in front of the page the user came for. The parts
  we need come to about 100 lines in the existing FastAPI code, and they're tested with the rest
  of the suite.

- **Devices are released by IP address, for one hour.** That matches the DHCP lease
  (`setup_hotspot.render_dnsmasq`). The Portal only sees IP addresses, not hardware addresses.
  If an address is reused within the hour, the worst outcome is that the next device doesn't get
  a sign-in window. It can still use the sticker address.

- **The probe responder runs in the Portal's process,** as a second Uvicorn server started by
  `WebAppThreadManager`, and only when `WIFI_HOTSPOT_ENABLED=true`. The two servers share the
  list of released devices in memory. When the Portal moves into its own sandboxed process
  (ADR-0006), the probe responder moves with it.

- **The firewall changes as little as possible:**
  - only port 80 traffic to the Pi's own address is redirected. Port 80 traffic to anywhere
    else is still refused like all other forwarding;
  - HTTPS to the Pi (port 443) is reset, so the OSes' HTTPS checks fail at once instead of
    timing out;
  - SSH and the dashboard stay closed on the Hotspot.

- **Windows' DNS check gets its real answer.** `dns.msftncsi.com` is answered with
  `131.107.255.255`, as Windows expects. Without that, Windows reports "no internet" even after
  release.

- **Any name typed on the Hotspot reaches the Portal.** Since every name resolves to the Pi and
  port 80 goes to the probe responder, `http://<PORTAL_HOSTNAME>` with no port lands on `/upload`.
  No domain has to be bought for that. The sticker should print the address with `http://` in
  front, so browsers don't treat it as a search. `PORTAL_HOSTNAME` must not use a top-level
  domain that browsers force onto HTTPS (`.app`, `.dev`) or `.local` (mDNS). It shouldn't be a
  real public domain either, since a phone using mobile-data DNS would get someone else's
  address. The reserved `.example` placeholder in use now meets all three.

- **QR images stay.** They're still the quickest way in for phones, and the Wi-Fi join QR image
  still saves typing the network name.

## Open question: HTTPS on the Hotspot

ADR-0007 justified an open network partly because "HTTPS already protects the uploads", using a
real certificate for `print.<domain>`. Without a domain there's no trusted certificate for the
Portal, which leaves two options:

- **Keep HTTPS with the self-signed certificate (ADR-0001).** Every browser shows a certificate
  warning. The OSes' sign-in windows may refuse the page outright, which would undo this ADR for
  exactly the users it's meant for.
- **Serve the Portal over plain HTTP on the Hotspot, and encrypt the Wi-Fi instead** with OWE
  ("Enhanced Open", hostapd `owe_transition`). OWE encrypts each device's traffic with no
  password. Devices too old for OWE would still join the open half of the network in the clear.

Not decided yet. The probe responder redirects to whatever scheme the Portal is serving
(`WebAppThreadManager.tls_enabled`), so either choice works without changing it.

## To verify on hardware

Test on iPhone, Android (with mobile data on and off), a Mac and a Windows laptop:
- the sign-in window opens by itself, on the upload page;
- a PDF can be picked and uploaded inside the sign-in window;
- after release, the device stays on the Hotspot and the window can be closed or kept open;
- **downloads** (scan-to-Wi-Fi redemption, `/redeem`): iOS sign-in windows can't download
  files. If that's confirmed, `/redeem` should tell the user to open the address in their
  browser;
- Android after release: it also checks over HTTPS, which can never succeed here. It may mark
  the network "limited" or "no internet" and still prefer mobile data. If so, the fallback is
  ADR-0007's: requests to the Pi's own subnet still go over Wi-Fi.

## What this changes in ADR-0007

- "No captive portal" becomes "captive-portal detection, no splash page".
- `dnsmasq` answers every name with the Pi, not only `PORTAL_HOSTNAME`.
- The firewall also allows the probe responder's port, redirects port 80 to it, and resets 443.
- On hold until a domain exists: the permanent `print.<domain>/k/<KIOSK_ID>` address, the
  Let's Encrypt certificate, and the public-DNS fix for phones that prefer mobile data.

## Rejected alternatives

- **openNDS with a splash page** (above): gates internet access we don't provide, and adds a
  tap.
- **Buying a domain:** turned down by our supervisor over the cost to the operator.
- **Answering "online" from the first check:** no sign-in window would open, so laptops would
  lose the automatic way in. That was the reason for this change.
- **Releasing a device on its first check:** the sign-in window loads the check address itself,
  so it would show Apple's "Success" page instead of the Portal.
