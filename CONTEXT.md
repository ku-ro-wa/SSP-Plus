# SSP-Plus / AIO SPARK

The self-service printing kiosk and the backend services around it. The glossary is
grouped by area: **intake** (how a document gets from a user's phone or inbox onto the
kiosk and into the print path) and the **Admin Dashboard** (the separate web-based
reporting/back-office surface, see `docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md`).

## Language

### Intake

**Intake**:
The pipeline that accepts a document from outside the kiosk, validates it, and makes it
redeemable at the touchscreen. Every non-USB way of getting a document in (Wi-Fi upload,
email submission, and later scanning) is an intake path.
_Avoid_: ingestion, import.

**Workflow**:
One user-facing journey end to end — e.g. the *Wi-Fi workflow* is "connect, upload, get a
code, type it at the kiosk, pay, collect the printout". A workflow spans both the intake
pipeline and the shared kiosk print path.
_Avoid_: flow (reserve "flow" for informal use), user story.

**Source**:
Which intake path a document arrived through: `usb`, `wifi`, `email`, or `scanner`. Stored
on the session and carried through the kiosk screens for reporting; it does not change how
the document prints. This is also the grouping key behind the Admin Dashboard's per-service
revenue view (see **Photocopy** for the `scanner` case).
_Avoid_: channel, method, origin, modality.

**Session**:
A record that ties one batch of already-validated, on-disk files to a single pickup code,
with an expiry and a failed-attempt count. Created by the Session Manager, consumed once at
redemption. One session can carry several files.
_Avoid_: job, ticket, upload, transfer.

**OTP**:
The 6-digit one-time code that identifies a session to the person collecting the printout.
Shown once at creation (on the upload success page, or emailed back), never recoverable from
storage. The salted hash is what's persisted.
_Avoid_: PIN, passcode, token (a "token" here is the raw session id, not the OTP).

**Pickup code**:
User-facing name for the OTP in messages and on-screen copy. Same thing as the OTP.
_Avoid_: collection code, claim code.

**QR payload**:
The `session_id:otp` string encoded in the QR image handed to the user. Redeemable the same
way a typed OTP is; kiosk-side QR *scanning* is not built yet, so today it's decorative.
_Avoid_: QR token, QR code (say "QR image" for the picture, "QR payload" for its contents).

**Redemption**:
The act at the kiosk of proving you hold a session — typing the OTP (or, later, scanning the
QR) — which flips the session to `verified` and copies its files into a private working
directory for the print path.
_Avoid_: claim, verification (verification is one step inside redemption), unlock.

**Portal**:
The FastAPI-served web page a user reaches from their own device to upload PDFs over the
kiosk's network. Reached directly by URL for now; a captive-portal front end is future work.
_Avoid_: upload site, web app, captive portal (that names the future RaspAP/Nodogsplash
layer specifically, not this page).

**Poll cycle**:
One pass of the email poller: fetch unseen inbox messages, process each (subject check, PDF
extract, session create, reply), and record the outcome so the same message is never
processed twice.
_Avoid_: sweep, tick, scan.

### Admin Dashboard

**Kiosk Admin**:
The PIN-gated `screens/admin` surface reached at the touchscreen, with full read/write
control over paper, coin, and CMYK state. A physical-possession threat model — unrelated to
the Admin Dashboard's login. Always say "Kiosk Admin" rather than bare "admin" when the web
dashboard is anywhere nearby in the conversation, since the dashboard also has a role called
`admin` (see **Dashboard admin role**) that is *less* privileged than Kiosk Admin, not more.
_Avoid_: admin (unqualified).

**Login session**:
The signed, cookie-based session created when a Dashboard user authenticates, with a sliding
inactivity timeout. Unrelated to **Session** above — the two are different concepts that
happen to share the English word "session"; only Login session belongs to the Admin
Dashboard.
_Avoid_: session (unqualified), auth session.

**Dashboard admin role**:
One of the Admin Dashboard's two account roles (`dev`: full read/write; `admin`: read-only).
A network-login threat model, distinct from and less privileged than Kiosk Admin despite the
shared name. See `docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md`.
_Avoid_: admin (unqualified).

**Photocopy**:
An on-kiosk transaction whose Source is `scanner` and whose destination is the print path,
as opposed to scan-to-email or scan-to-session-download. Not a separate intake path of its
own — it's the one `scanner`-sourced case the Admin Dashboard's revenue view counts.
_Avoid_: copy job, scan job (ambiguous with the non-print scan destinations).
