---
name: changelog-commit
description: Use when the user asks to "write the commit message", "draft a changelog", "prepare COMMIT_MESSAGE.txt", or wants a commit-message-formatted summary of recent work. Derives a commit message from the session's SESSION_SUMMARY.md and writes it to COMMIT_MESSAGE.txt at the repo root, matching this project's existing convention. Does not run `git commit`.
version: 1.0.0
---

# Changelog / Commit Message

`COMMIT_MESSAGE.txt` is a tracked scratch file at the repo root (`SSP-Plus/`) used to stage the next commit's message before running `git commit -F COMMIT_MESSAGE.txt` (or copy/pasting it) — confirmed via `git ls-files`. This skill drafts that file. **It never runs `git commit` itself** — preparing the message and creating the commit are separate actions, and committing must only happen when the user explicitly asks.

## Source of truth

Derive the message **from the session's `*_SESSION_SUMMARY.md`** in `docs/session-summaries/` — don't re-research the change independently. If the summary doesn't exist yet, run the `session-summary` skill first (or ask the user which existing summary to use, if more than one is in play and it's ambiguous).

## Template

Matches the current `COMMIT_MESSAGE.txt` and this repo's `git log` style:

```
<Title — short imperative summary, e.g. "Add intake pipeline: SessionManager, Wi-Fi upload, email adapter">

<1-2 sentence paragraph giving roadmap/phase context — reference docs/roadmap-planning.txt
phases by name/number when the change maps to one.>

- <Component 1> (`path/to/file.py`, `path/to/other.py`): dense technical description
  of what changed and, briefly, why — pull the rationale straight out of that
  component's "### N." subsection in the session summary, don't just restate the
  file list.
- <Component 2> (`path/to/file.py`): ...
- <Component N> (`path/to/file.py`): ...

<Closing paragraph: test count/status (pulled from the summary's Testing guide),
plus a pointer — "See docs/session-summaries/<FILE>_SESSION_SUMMARY.md for full details, a testing guide,
and follow-up work.">

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

Mapping from the session summary:
- Title ← distilled from the summary's `# Session Summary — <Title>` line, reworded as an imperative commit title.
- Context paragraph ← the summary's `**Scope:**` line, expanded slightly if needed.
- Bullet list ← one bullet per `### N. <subsection>` in "What this session built", each bullet naming the file(s) from that subsection's heading/the "Files touched" table and compressing the paragraph's design rationale into 1-3 sentences.
- Closing paragraph ← the pass count from "## Testing guide" + a pointer to the summary's path (`docs/session-summaries/<FILE>_SESSION_SUMMARY.md`).

## Output

- Overwrite `COMMIT_MESSAGE.txt` at the repo root (`SSP-Plus/`) — it's meant to hold only the *next* commit's message, not accumulate history.
- After writing, tell the user the file is ready and that committing is a separate, explicit step (e.g. `git commit -F COMMIT_MESSAGE.txt`) — do not stage or commit anything yourself unless separately asked.
