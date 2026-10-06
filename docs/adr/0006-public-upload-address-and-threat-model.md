# Public upload address: target design and threat model (built local-only for now)

Returning customers should be able to upload from anywhere, at an address they already know,
without scanning a QR image at the kiosk first. Otherwise a remote, Wi-Fi-based upload method
loses most of its point. Two facts frame the decision:

- **The upload flow is already independent of location.** `/upload` validates the files,
  creates a **Session**, and shows a pickup code and QR image. The customer then redeems at the
  kiosk, by typing the code or letting the **QR reader** read the image. Email uploads work the
  same way. Uploading from home needs no new flow, only a way for `/upload` to be reached from
  the internet.
- **That makes it a public, unauthenticated surface.** ADR-0002 said nothing would be
  public-facing, and our supervisor has made security a major priority. That's why the portal
  was originally planned as LAN-only behind RaspAP. So this decision comes with an explicit
  threat model for review (below).

The system may also be replicated across several kiosks as a business, which affects how
uploads get routed (see "Open question").

**What's built now:** only the local hotspot path (ADR-0007). This ADR fixes the target design
and the constraints today's work must not close off, so the public address can be added later
without rework.

## Decisions

- **Reached through Cloudflare Tunnel, under our own domain.** The Pi runs `cloudflared`, which
  only makes an outgoing connection. The router needs no port forwarding, and the Pi's IP is
  never revealed. Customers use `print.<domain>`. Chosen over:
  - **Tailscale Funnel:** it gives a hard-to-remember `*.ts.net` name, it isn't meant for
    production-level public traffic, and a mistake in the Serve/Funnel config could expose the
    dashboard (ADR-0005 forbids that).
  - **A VPS reverse proxy:** a server to maintain and patch.
  Running the public side on separate software from the admin side (Tailscale) means admin
  access and public access can't get mixed up by a config mistake.

- **The portal moves into its own sandboxed process.** Today it's a Uvicorn thread inside the
  kiosk GUI (ADR-0001). That was fine while only phones standing at the kiosk could reach it.
  Made public, it would put internet traffic into the touchscreen app's own process. Instead:
  - it runs as its own systemd service under an unprivileged user;
  - systemd sandboxing allows writes only to the upload folder;
  - it listens on loopback, where only `cloudflared` (and the hotspot, ADR-0007) can reach it.
  The hotspot rework (ADR-0007) is the natural time to split it out.

- **Remote Sessions last about 24 hours.** "Upload tonight, print tomorrow" needs more than
  the hours-long expiry used on site. The 6-digit pickup code stays, protected by:
  - the existing per-Session attempt limit;
  - a new **kiosk-wide limit on wrong-code attempts**, so guessing can't be spread across many
    Sessions.
  Most customers scan the QR image instead of typing the code. Move to a longer code for remote
  Sessions only if the logs show guessing attempts. ADR-0003 rejected 6 digits for long-lived
  Vouchers, but a Voucher lasts far longer than a day.

- **Every untrusted PDF is parsed in a sandboxed subprocess.** This applies to both email and
  web uploads, and isn't tied to the public address, so it can be built any time. The
  subprocess is short-lived, with a timeout and memory/CPU limits. A malicious or broken PDF
  can then crash or hang only that subprocess, not the portal or the kiosk. Flattening or
  re-rendering each PDF on intake is held back, since it can damage some documents.

- **The address is permanent from day one.** Stickers, bookmarks, and the on-screen QR image
  use `print.<domain>/k/<KIOSK_ID>` before anything is public. ADR-0007 answers that name
  locally today. Publishing it later doesn't change a single sticker.

## Open question: one kiosk per upload, or any kiosk?

With a tunnel per kiosk, a customer uploading from home has to pick the kiosk before
uploading, and their code works only there. **Central intake** works differently: an upload
service in the cloud holds the file, and the kiosk fetches it with an outgoing request when the
code is redeemed. That lets a code be redeemed at any kiosk, and it means the Pi accepts no
incoming traffic at all. It costs a second system (a separate codebase, likely in another
language) and puts customer documents with a third party, which brings privacy obligations.

At one kiosk, a tunnel per kiosk is simpler. **At several kiosks, central intake is favoured.**
This is decided when remote upload is actually built. The `/k/<KIOSK_ID>` path keeps both
options open: a tunnel per kiosk can route on it, and a central service can treat it as the
default kiosk.

## Threat model

Exposure comes in three layers. Only the second is new.

| Layer | What it is | Exists today? | Mitigation |
|---|---|---|---|
| 1. Parsing untrusted files | Every upload is checked for size, file count (max 20), and a `%PDF` header (`wifi_adapter.py`), then opened by PyMuPDF, a C library with a history of security bugs, and sent to CUPS. | **Yes.** Email intake already lets anyone who knows the address send a PDF that the Pi will parse. | A sandboxed parsing subprocess with limits (above). |
| 2. A listener reachable from the internet | HTTP requests from anywhere reach the portal's FastAPI code. | No. New with the public address. | Cloudflare Tunnel (no open ports, IP hidden). The portal is its own process: unprivileged, sandboxed, loopback-only. Cloudflare filters bots and rate-limits in front. |
| 3. Resource abuse | Filling the disk, using up cellular data, creating huge numbers of Sessions, guessing codes. | Partly. Only the 20-files-per-request cap exists. | Cloudflare rate limits per client. Upload size and per-day quotas. Upload retention and cleanup. Kiosk-wide wrong-code limit. |

**What stays protected no matter what:**
- The Admin Dashboard is never public (ADR-0005). It's on the tailnet only, listens on
  loopback, and sits behind its own login.
- The kiosk accepts no incoming connections from the internet. `cloudflared` and Tailscale
  both connect outward.

**Accepted risks:**
- A 6-digit pickup code valid for about 24 hours, mitigated by attempt limits.
- Cloudflare terminates TLS, so it can technically see uploads in transit. This is accepted as
  standard for tunnel/CDN setups. Central intake would go further and store documents with a
  third party, which is part of why it's still an open question.
- The Let's Encrypt certificate for local HTTPS (ADR-0007) is issued with a Cloudflare DNS
  token on each Pi. That token can edit the domain's DNS records. It's scoped to the one
  domain. Issuing certificates centrally and copying them to kiosks is the fallback if that's
  judged too much.

## Rejected alternatives

- **Upload handled off the device right away** (central intake as the first step). It sounds
  strongest, but it moves the boundary rather than removing it: the PDF is still parsed on the
  Pi at redemption (layer 1 unchanged). It also brings a second system and third-party storage
  before there's more than one kiosk. It stays the likely design at scale (open question
  above).
- **Staying local-only for good.** The safest option, but returning customers would always have
  to stand at the kiosk to start an upload, which defeats a remote upload method.
