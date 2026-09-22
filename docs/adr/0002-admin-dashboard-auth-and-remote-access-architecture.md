# Admin Dashboard: auth and access architecture, with remote access deferred

`project_objectives.txt` module 9 / `roadmap-planning.txt` Phase 7 specifies a FastAPI-served
web Admin Dashboard at `/admin/accounting` (per-service revenue and transaction counts, Chart.js
bar chart, time filters). This is a **different surface** from the existing PyQt5 `admin` /
`data_viewer` screens (`screens/admin/`, `screens/data_viewer/`) reached via the touchscreen PIN
dialog — those stay as they are. "Admin Dashboard" below means the new web UI only.

A separate design discussion (not yet implemented) worked out the full architecture for making
both this dashboard and the local SQLite DB (`SSP/database/ssp_database.db`) reachable by a
trusted user *remotely*, outside the kiosk. The decision here is to build Phase 7 **locally
first**, but to build its process/auth/data-access layer exactly as that remote-access design
specifies, so remote reachability can be added later as a pure networking change with no rework
of the app itself.

## Build now (Phase 7, local-first)

- **Separate process.** The Admin Dashboard runs as its own FastAPI/Uvicorn instance, on its own
  port — a new sibling to `webapp/main.py`, not routes added to it. It must not share a process
  with the existing Wi-Fi upload portal (`managers/webapp_thread.py`, `webapp.main:app`), which is
  deliberately unauthenticated and reachable by any phone on the LAN. Keeping them separate means
  a bug in the low-trust upload portal can't become a path into the DB-write-capable dashboard.

- **Started by its own `make` target, not spawned by `main_app.py`.** `main_app.py` already owns
  the Wi-Fi portal's lifecycle via `WebAppThreadManager`, which is precisely the coupling the
  process-separation decision above exists to avoid repeating. Auto-spawning the dashboard from
  `main_app.py` (even as a subprocess rather than a thread) would reintroduce that coupling in
  spirit — a future "simplification" could fold it back into a thread-manager, since it'd already
  look just like the others — and would require health-check/restart/orphan-cleanup code that
  Phase 7's local-only scope doesn't need. A separate target (e.g. `make run-admin-dashboard`) is
  also what's trivially promotable to the systemd unit the remote-access phase eventually wants,
  with no rework.

- **Real auth, replacing the `require_admin()` stub.** `webapp/auth.py`'s current comment expects
  "PIN/session-based, mirroring `screens/dialogs/pin_dialog`" — that expectation is superseded.
  The dashboard's auth is deliberately **independent** from the touchscreen `ADMIN_PIN` system
  (different threat model: physical possession of the kiosk vs. a network login), with its own:
  - Individual accounts (small `users` table, not a shared secret) — even at one or two users —
    with passwords hashed at rest (bcrypt/argon2), not compared in plaintext.
  - Two roles: `dev` (full read/write) and `admin` (read-only). Only `dev` is needed to start;
    the schema should leave room for more roles/granularity later without a rewrite.
  - Sliding session timeout on inactivity, roughly 8–12 hours.
  - A minimal login audit log: timestamp, username, success/failure, source IP.
  - Lockout/backoff after ~5 consecutive failed login attempts.
  - Accounts created and passwords reset via a local CLI tool run by hand — no self-service
    signup or "forgot password" email flow.

- **DB access pattern.** The kiosk's SQLite file remains the single source of truth — no
  relocation, replication, or sync elsewhere. The dashboard touches it only through this FastAPI
  process's own endpoints (the aggregate-query routes Phase 7 already calls for); no raw
  SQL/DB-client access is exposed alongside it. This matches Phase 7's existing plan and needs no
  extra work, just: don't add a side channel later.

## Deferred (not part of this local-first build)

These are already decided in the remote-access design; they're future work, not open questions:

- **Tailscale** as the private mesh network that makes the dashboard's port reachable off the
  kiosk at all (nothing public-facing).
- **Tailscale Serve** for automatic HTTPS on top of that, once remote access is added — mainly so
  the login session cookie can be marked `Secure`.
- **Tailscale ACLs** were considered and explicitly rejected even for the remote phase — app-level
  login already gates access; ACLs are only worth revisiting if the tailnet grows to include
  unrelated devices/people.
- Running the dashboard's process as an independent systemd service at boot (vs. tied to the
  kiosk GUI's lifecycle) matters once it needs to be reachable remotely while the touchscreen app
  might be down; for local-only use it can start however Phase 7's own plan already has it start.

## Explicitly out of scope, now or later

- Raw SQL / DB-client (e.g. DBeaver) access to `ssp_database.db` over the network.
- Self-service account signup or password reset.
- Unifying this login with the touchscreen `ADMIN_PIN` system.
- Relocating the DB off the kiosk (it stays authoritative on-device; remote access reaches into
  it live, it doesn't replace it).
