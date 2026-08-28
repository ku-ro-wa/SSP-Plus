---
name: test-and-verify
description: Use after making major or multi-file changes in this repo, or when the user asks to "run the tests", "verify this works", "check nothing broke", or "run make test/lint". Runs this project's test suite and linter (and, when relevant, a boot smoke check) and reports pass/fail — does not attempt to fix failures itself.
version: 1.0.0
---

# Test and Verify

Run this project's verification suite from the repo root (`SSP-Plus/`, the directory containing `Makefile`/`CLAUDE.md`) and report results. This is an action skill — it produces a chat report, not a file.

## Steps

1. **Tests:**
   ```bash
   make test    # pytest tests/ -v
   ```
   Report the pass/fail count. On any failure, show the failing test name(s) and the relevant traceback/assertion, and **stop here** — don't proceed to lint or declare success. Do not attempt to fix the failure yourself unless separately asked; surface it for a decision.

2. **Lint:**
   ```bash
   make lint    # flake8 SSP/ --max-line-length=120
   ```
   Report any violations (file:line + rule). A clean run is "no new violations" per this repo's existing convention in its session summaries.

3. **Conditional smoke check** — only when this session's changes touched boot/thread/webapp code (`SSP/main_app.py`, anything under `SSP/managers/*thread*`, or `SSP/webapp/`). Skip entirely for changes confined to pure logic/algorithm files (e.g. `payment_algorithm_manager.py`) — it adds no signal there.
   - GUI/thread boot: `SIM_MODE=true timeout 8 .venv/bin/python SSP/main_app.py`, confirm it starts without a traceback and exits cleanly on the timeout (not a crash).
   - Webapp: start it under `SIM_MODE`, then `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/` and `.../docs`, confirm both return 200. Kill the process afterward.

4. **Report.** End with a short summary: test count, lint status, smoke-check result (if run). Match the tone of the "Testing guide" section in this repo's `*_SESSION_SUMMARY.md` files (in `docs/session-summaries/`) — factual, specific counts, no padding.

## What this skill does not do

- Does not modify code to fix a failing test or lint violation — that's a separate, deliberate step.
- Does not run the hardware-dependent manual checks (GPIO, printer, SMS, real greenmail/Gmail) — those need actual hardware/services per `CLAUDE.md` and stay manual.
- Does not write to any file — findings go in the chat response.
