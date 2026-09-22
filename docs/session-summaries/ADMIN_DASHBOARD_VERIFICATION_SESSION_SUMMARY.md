# Session Summary — Admin Dashboard (Issue #11) Verification & Transaction-Source Fix

**Date:** 2026-09-22
**Scope:** Verifies that parent issue #11 (Admin Dashboard for kiosk analytics, Phase 7) is
actually satisfied now that all 7 of its child issues (#12-#18) are closed with passing tests.
It is not a feature-building session — no new endpoints, screens, or schema were added. It
closes one real gap that "all children closed" hid: the `source` column #12 added to
`transactions` was never written by the real print/payment flow, so the accounting page's
per-Source revenue view — the entire point of #11 — would have shown zero for every source in
real operation despite every dashboard-side test passing.

```
 print_options/controller.py        payment/model.py              database/db_manager.py
   self.source (usb/wifi/            transaction_data = {            log_transaction(data):
   email/scanner, set by each          ...,                            INSERT INTO transactions
   intake screen's set_pdf_data)       'source': ???  <-- gap            (..., source) <-- gap
        |                                    |                               |
        v                                    v                               v
   payment_data['source']  ---->   self.payment_data.get('source')  ---->  data.get('source')
     (this session: added)           (this session: added)            (this session: added)
                                                                              |
                                                                              v
                                                          get_accounting_summary()
                                                          WHERE source IS NOT NULL
                                                          (pre-existing — was silently
                                                           dropping every real row)
```

## What this session found and fixed

### 1. The gap: `log_transaction` silently dropped `source` — `SSP/database/db_manager.py`

Issue #12's acceptance criteria was schema-only ("a fresh database... has a `source` column...
accepting the existing Source values") and its tests (`tests/test_database_models.py`) only
ever inserted rows directly via raw SQL to prove the column exists — never through
`DatabaseManager.log_transaction`, which is what the real kiosk print flow actually calls.
`log_transaction`'s `INSERT` statement never named the `source` column at all. No child issue's
acceptance criteria asked for wiring it, either — #15's aggregate-endpoint tests seed known rows
directly into a temp DB, and `admin_dashboard/seed_demo_data.py`'s `seed_transaction()`
deliberately bypasses `log_transaction` (it targets a separate `SIM_MODE`-gated demo DB). The
result: every real transaction had `source = NULL`, and `get_accounting_summary`'s
`WHERE source IS NOT NULL` filter (a correct, intentional design per CONTEXT.md's Photocopy
term) excluded all of them — invisibly, since nothing exercising the real write path existed to
catch it.

Traced every producer of a `source` value across the four intake paths to confirm the fix
closes the loop completely, not just for one path:
- `usb`/`wifi`/`email` controllers call `file_browser_screen.set_source(...)`, which
  `file_browser/controller.py` forwards into `print_options.set_pdf_data(..., self.source)`.
- `scanner` → print (a **Photocopy**, issue #11 user story 8) has two sub-paths — immediate
  "Print Now" (`scan_destination/controller.py`) and resumed pending-print after a Wi-Fi pickup
  (`scan_result/controller.py`) — both call `set_pdf_data(pdf_data, selected_pages, "scanner")`.
- scan-to-email / scan-to-session-download (user story 9, must be **excluded**) never call
  `set_pdf_data` at all in either screen's other branch, so they never reach `log_transaction` —
  confirmed this was already correct and needed no change.

Fix: `payment_data['source'] = self.source` added in
`print_options/controller.py::_continue_to_payment` (the controller already tracked `self.source`
per intake screen — it was just never forwarded); `payment/model.py` carries
`self.payment_data.get('source')` into both `transaction_data` dicts (the successful-print path
and `_log_partial_payment`'s cancelled-transaction path); `log_transaction` now includes
`source` in its `INSERT`.

### 2. A latent footgun found in review — `SSP/screens/print_options/controller.py`

`set_pdf_data`'s `source` parameter defaulted to the *string* `"None"`, not Python `None`. All
three current call sites pass `source` explicitly so this was dead before this session — but
now that `source` is actually load-bearing, a future caller relying on the default would insert
a bogus `"None"` string that `get_accounting_summary`'s source-vocabulary filter would silently
drop, reintroducing the exact same invisible-revenue bug this session just fixed. Changed the
default to `None`.

### 3. Stale comment — `SSP/admin_dashboard/seed_demo_data.py`

`seed_transaction()`'s docstring claimed `log_transaction` "doesn't populate `source`" as a
justification for bypassing it — no longer true after this session's fix. Reworded to state the
actual reason it still bypasses `log_transaction`: it targets the separate `ssp_database.sim.db`
file, never the real DB, regardless of what `log_transaction` does.

### 4. Doc gap — `CLAUDE.md`

`CLAUDE.md` had no mention of `SSP/admin_dashboard/` at all despite it being a fully built,
tested subsystem (issues #12-#18) — a real gap for any future session using it as the map of the
repo. Added an "Admin Dashboard" section (process/port, auth model, roles, endpoints, the
source-wiring path this session fixed, demo-data isolation, test seam) plus `make
run-admin-dashboard` to the Commands block. Also corrected two other stale lines found in
passing: the `make test` comment said "16 tests" (now 177), and the Database section's table
list predated `sessions`, `email_intake_log`, `users`, and `dashboard_login_log`.

## Files touched

| File | Status | Purpose |
|---|---|---|
| `SSP/database/db_manager.py` | modified | `log_transaction` now writes `source` to the INSERT |
| `SSP/screens/print_options/controller.py` | modified | forwards `self.source` into `payment_data`; fixed `source="None"` string default → `None` |
| `SSP/screens/payment/model.py` | modified | carries `payment_data['source']` into both `transaction_data` dicts |
| `SSP/admin_dashboard/seed_demo_data.py` | modified | corrected now-stale docstring comment |
| `tests/test_transaction_source_logging.py` | added | `log_transaction` persists `source`; missing key doesn't raise; a logged row is counted by `get_accounting_summary` |
| `CLAUDE.md` | modified | new Admin Dashboard section; corrected stale test count and table list |

## Testing guide

```bash
make test    # 177 passed (174 existing + 3 new: source persisted, missing-key safety,
             # accounting-summary integration)
```

Verified this session:
- `tests/test_transaction_source_logging.py` fails against the pre-fix code (confirmed the gap
  was real, not theoretical) and passes after the `log_transaction` fix.
- Two-axis `/code-review` (Standards + Spec, run as parallel sub-agents against `git diff HEAD`)
  came back clean on Spec (no missing/wrong requirements after tracing every `log_transaction`
  call site) and with only judgment-call smells on Standards (some pre-existing dict-literal
  duplication in `payment/model.py` extended by one line each; no defensive validation against
  `ACCOUNTING_SOURCES` at the write side) — no hard violations, left as-is per this project's
  "don't validate what can't happen" convention since `source` here is internally generated,
  never user input.

No end-to-end manual run against real hardware or `make run-sim` this session — the fix is pure
data-plumbing through code paths already covered by the modules above; nothing in the on-screen
UI or hardware interaction changed.

## Future considerations

1. **No automated test exists for `screens/payment/model.py` or `screens/print_options/controller.py`
   directly** (PyQt5 UI-layer code, same gap as the rest of the screens/ tree per `CLAUDE.md`'s
   note that `payment_algorithm_manager` is "the only manager with dedicated unit tests"). This
   session's regression coverage lives entirely at the `DatabaseManager` layer
   (`tests/test_transaction_source_logging.py`); a `source` regression reintroduced purely in the
   PyQt controller/model glue (e.g. the `_continue_to_payment` one-liner being reverted) would not
   be caught by `make test` — only by exercising the actual kiosk flow.
2. **Issue #11 was commented with this session's finding and fix, then deliberately left open**
   on GitHub per this repo's established convention (see `docs/agents/issue-tracker.md` and this
   session's own `project_roadmap` memory) — closing an issue requires the user to say so for
   that specific issue number, even when "verify #11" surfaces real, fixed work.
3. **Remote access (Tailscale) is next per the current roadmap priority order** — the
   auth/process/data-access layer this session's fix completes is exactly what
   `docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md` says should be built
   local-first so remote reachability can be added later as a pure networking change.
