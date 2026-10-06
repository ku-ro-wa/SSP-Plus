# One remote admin surface: Kiosk Admin moves into the Admin Dashboard, served by Tailscale Serve

ADR-0002 deferred remote access to the web **Admin Dashboard** (`SSP/admin_dashboard`, port
8100) and chose Tailscale + Tailscale Serve for it. When we came back to that work, the goal
grew: the touchscreen **Kiosk Admin** screen (`screens/admin/`, `screens/data_viewer/`) should
be reachable remotely too, at the same address as the accounting analytics.

The two surfaces aren't two web apps. The dashboard is a web app, but Kiosk Admin is a PyQt
screen with no URL. Putting both "at one address" therefore means putting both in one web app,
not adding network routing.

The kiosk may be replicated across sites (see ADR-0006's context), so every decision here
works per kiosk without hand configuration, but nothing here builds features that span
several kiosks.

## Decisions

### What the dashboard gains

- **Kiosk Admin's functions get web pages inside the Admin Dashboard.** They are new routers in
  `admin_dashboard` next to `accounting`, in the same process and behind the same login.
  They ship in two releases, because almost every remote need is seeing, not changing:
  - **Release 1, view only:**
    - `/kiosk`: paper count, ₱1/₱5 coin counts, CMYK levels, QR reader status, recent
      unresolved errors, and **kiosk last seen**.
    - `/logs`: transactions, cash inventory, and the error log (the `data_viewer` tables).
    - `/accounting` as today.
  - **Release 2, edits for the `admin` role only:**
    - The same count edits the touchscreen offers: set, increment/decrement, reset/refill.
    - Marking errors resolved.
  Refilling is physical work, so remote edits exist for corrections: a refill nobody recorded,
  a count that drifted, or a malfunction fixed on site but never marked resolved.

- **Roles map on directly** (renamed 2026-10-06, see ADR-0002): `admin` can edit, `operator` can
  view only. Writes go through `DatabaseManager`, the same as `/paper-reset` does today. Raw SQL
  access is still out of scope (ADR-0002).

- **"Kiosk last seen" heartbeat.** The dashboard keeps running when the kiosk app is down, so
  without this it would show numbers that stopped updating hours ago as if they were current.
  `main_app.py` writes a timestamp to `settings` about once a minute. `/kiosk` shows "online,
  30 s ago" or "offline since 09:12".

- **"Resolved" gets a definition.** `error_log.resolved` exists but nothing sets it, and the
  touchscreen's PIN admin override on the thank-you screen clears an error on screen without
  touching the log. In Release 2, both paths mark it: the override marks the related error
  resolved, and `admin` can mark errors resolved from `/logs` for ones fixed on site but never
  marked. Automatically resolving an error after a later success is rejected for now: guessing
  which error a success clears is error-prone.

- **Every remote write is logged.** A new `admin_actions` table records time, username, action,
  old value, new value, and source IP. Every Release 2 write and the existing `/paper-reset`
  record to it, and `/logs` shows it. Login logging (`dashboard_login_log`) doesn't answer "who
  set paper to 100" after a dispute about a refill.

- **Phone-first pages with stable anchors.** The `operator` will mostly check from a phone
  after an alert. Sections get stable URLs (`/kiosk#paper`, …) so a future alert can link
  straight to them. Replacing or extending the SMS alerts is out of scope here; they stay as
  they are.

- **The touchscreen Kiosk Admin stays.** ADR-0002 keeps the PyQt screens for on-site use behind
  `ADMIN_PIN`, and this ADR doesn't change that. The two front ends share the SQLite DB and
  nothing else. Login systems stay separate, as ADR-0002 requires.
  - If the touchscreen admin screen is open while a remote edit lands, it shows the old value
    until it's reopened. This is accepted. It's rare, and the write itself is safe (see the
    prerequisite below).

### How it's reached

- **Tailscale Serve provides the one address.** `tailscale serve --bg 8100` publishes the
  dashboard at `https://<kiosk-hostname>.<tailnet>.ts.net/`. There's one origin, one TLS
  certificate, and one session cookie. Tailscale runs on the Pi itself, not on the router: it
  works the same with any router, cellular or not (behind carrier NAT it relays through
  Tailscale's servers), and Serve has to sit on the same machine as a dashboard that only
  listens on loopback.

- **A dedicated tailnet, owned by the project account.** The tailnet is separate from anyone's
  personal devices. Signing in uses the dedicated project account (see `docs/SETUP.md`,
  "External accounts"), not a personal Gmail. Members:
  - the developer (`admin` dashboard account), invited as a tailnet user;
  - the kiosk owner/operator (`operator` dashboard account), invited as a user. If they
    already run their own tailnet, the kiosk device is shared into it instead.
  Each person's dashboard password is created with the CLI and given in person, never over
  SMS or chat. The tailnet only gets you to the login page; the dashboard login is a separate
  second gate.

- **Devices are tagged now; ACLs switch on with the second site.** ADR-0002 rejected Tailscale
  ACLs only while the tailnet held nothing unrelated. With several sites, site B's operator
  could reach site A's dashboard: the login stops them, but the network doesn't. Kiosks get
  `tag:kiosk` and `tag:site-<KIOSK_ID>` from day one. That costs nothing and changes nothing
  today. ACLs that limit each operator to their own site switch on the day an operator from a
  second site joins.

- **Uvicorn binds to `127.0.0.1`, not `0.0.0.0`.** Today any phone on the kiosk's Wi-Fi hotspot
  can reach port 8100 over plain HTTP. Once Serve sits in front, nothing needs to reach that
  port directly. The hotspot firewall (ADR-0007) closes it too, as a second barrier.

- **The session cookie is marked `Secure`.** HTTPS from Serve makes this possible. It was
  ADR-0002's main reason for choosing Serve.

- **The dashboard runs as its own systemd service.** It starts at boot, independent of the
  kiosk GUI, so remote admin keeps working while `main_app.py` is down, which is often exactly
  when remote access is needed. `make run-admin-dashboard` remains the development entry point.

### Hard limits

- **The dashboard is never exposed publicly.** It's reachable only over the tailnet. It never
  shares a public hostname, tunnel, or Tailscale Funnel with the customer upload portal
  (ADR-0006).
- **The dashboard can't touch OS services.** It reads and writes a handful of DB values and
  nothing else. Settings that change the machine, such as the hotspot switch (ADR-0007), are
  changed only on the Pi itself, in `.env` plus the setup script.
- **Multi-kiosk features wait.** Each kiosk keeps its own dashboard, accounts, and DB. A central
  view or central accounts would need a central service and data off the kiosk, which ADR-0002
  ruled out. Revisit only once there's a second kiosk. Creating accounts per kiosk with the CLI
  is the first thing likely to become tedious.

## Prerequisite: the kiosk reads the DB fresh before each write

Remote edits only work if the kiosk never writes a value it cached earlier back to the DB.
Paper count had this bug: `AdminModel.decrement_paper_count` (`screens/admin/model.py`, called
from `main_app.py` on every print) started from the in-memory `self.paper_count` instead of the
DB value. So a refill from the dashboard, including today's `/paper-reset`, was undone by the
kiosk's next print. The touchscreen's +/- steppers and typed-in value had the same problem.
**Fixed** alongside this ADR: every paper write now rereads the DB first
(`_refresh_paper_count`), covered by `tests/test_admin_model_paper_count.py`. Coin decrements
and CMYK updates already read the DB fresh.

## Rejected alternatives

- **Two processes behind one hostname** (`tailscale serve --set-path`). This works for two web
  apps, but Kiosk Admin isn't one. It would also mean two logins and two cookies on one origin.
- **Screen sharing the touchscreen (VNC/noVNC over Tailscale).** It takes over the live kiosk
  display while a customer may be using it, and it skips the dashboard's accounts, roles, and
  audit logging.
- **A separate remote-only admin app.** A third surface with its own auth to maintain, for no
  gain over the dashboard, which already has auth.
- **A dashboard toggle for OS-level settings** (e.g. the hotspot). It would give a web process
  root-level reach, a large step up in what a dashboard bug could do, for settings that change
  rarely.
