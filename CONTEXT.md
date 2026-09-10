# SSP-Plus / AIO SPARK

The self-service printing kiosk and the backend services that feed documents into it.
This glossary covers the vocabulary of the **intake** side — how a document gets from a
user's phone or inbox onto the kiosk and into the print path.

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
the document prints.
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
