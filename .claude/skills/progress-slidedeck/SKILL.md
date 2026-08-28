---
name: progress-slidedeck
description: Use when the user asks to "make a progress slide deck", "build a progress update", "create a slideshow/presentation of what we did", or wants a PowerPoint summarizing one or more sessions of work in this repo. Produces a progress_update_<date>.pptx in docs/progress-updates/ matching the visual style of the existing decks there (progress_update_2026-07-16.pptx, progress_update_2026-07-23.pptx).
version: 1.0.0
---

# Progress Slide Deck

Produce a `progress_update_<YYYY-MM-DD>.pptx` in `docs/progress-updates/` (under the repo root `SSP-Plus/`), styled to match the existing decks in that folder. Read `reference/style.md` (in this skill's directory) for the full palette/layout spec before writing content — don't re-derive it from scratch or improvise new colors.

## Process

1. **Gather content.** Prefer reading the relevant `*_SESSION_SUMMARY.md` file(s) in `docs/session-summaries/` as the source of truth (run the `session-summary` skill first if one doesn't exist yet for this session's work) rather than re-deriving from git. If summarizing multiple sessions, one deck can cover all of them (the July 23 example covers two).

2. **Ensure `python-pptx` is available:**
   ```bash
   .venv/bin/python -c "import pptx" 2>/dev/null || .venv/bin/pip install --quiet python-pptx
   ```
   This is a doc-authoring dependency, not a runtime dependency of the kiosk app — don't add it to `requirements.txt`.

3. **Write a short content script** that imports `scripts/deck_builder.py` (in this skill's directory — add its path with `sys.path.insert(0, ...)` or copy/run it from that directory) and calls its slide-builder functions with this session's actual content. Do not hand-build shapes/XML — every recurring slide type already has a function. See the docstring at the top of `deck_builder.py` for a full usage example.

4. **Map session-summary content onto slide types:**
   - `add_title_slide(prs, title, subtitle, meta_line)` — title from the session(s)' theme, subtitle names each session's `## What this session built` scope separated by `·`, meta is the date.
   - `add_overview_slide(...)` — only needed when covering 2+ sessions; skip straight to the flow slide for a single-session deck.
   - `add_flow_slide(prs, heading, steps, note=None)` — one per session, built from that session's ASCII flow diagram / `### N.` subsection sequence in the summary. Steps should read like an actual call chain, not generic milestones.
   - `add_built_slide(prs, heading, cards)` — one per session; each card = one `### N. <subsection>` from "What this session built", condensed to 2-4 bullets.
   - `add_stats_slide(...)` — pull the pass count straight from the summary's `## Testing guide` fenced block; "Covered Offline" = what `make test` actually exercises, "Needs the Real Thing" = the summary's manual/end-to-end steps.
   - `add_next_steps_slide(...)` — pull directly from the summary's `## Future considerations`, condensing each to a title + one sentence.

5. **Save** as `docs/progress-updates/progress_update_<YYYY-MM-DD>.pptx`, using today's date.

## Verifying the output

`python-pptx` decks can't be visually rendered from the CLI, so sanity-check structurally instead of assuming it's correct:
```bash
.venv/bin/python -c "
from pptx import Presentation
prs = Presentation('docs/progress-updates/progress_update_<date>.pptx')
for i, s in enumerate(prs.slides, 1):
    print(i, [sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()])
"
```
Confirm every slide has the text you intended and nothing is empty/truncated.
