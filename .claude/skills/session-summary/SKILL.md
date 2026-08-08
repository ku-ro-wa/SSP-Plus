---
name: session-summary
description: Use when the user asks to "write a session summary", "summarize this session", "document what we built", or at the natural end of a substantial work session in this repo. Produces a SESSION_SUMMARY.md at the repo root matching this project's established format (see SESSION_MANAGER_SESSION_SUMMARY.md, GUI_BACKEND_WIRING_SESSION_SUMMARY.md, MULTI_FILE_WIFI_UPLOAD_SESSION_SUMMARY.md for reference).
version: 1.0.0
---

# Session Summary

Produce a `<TOPIC>_SESSION_SUMMARY.md` file at the repo root (`SSP-Plus/`) documenting the work done this session, in the exact format this project already uses. Read one of the existing `*_SESSION_SUMMARY.md` files first if you haven't seen this repo's summaries before — the format below is compressed from them, but the real documents show the tone and level of detail expected.

## What makes these docs distinctive

These are **design narratives**, not changelogs. Every existing example spends most of its words on *why* — the problem that forced a decision, the alternative that was rejected, the tradeoff that was accepted. A bullet list of "added X, changed Y" is not sufficient; write prose paragraphs that a teammate with zero session context could read and understand the reasoning, not just the diff.

## Gathering material

1. Determine what actually changed: `git diff`/`git log` against the relevant base (last commit, or where the branch diverged).
2. Recall the *design discussion* from this conversation — the rejected approaches, the constraints that shaped the final design, any tradeoffs explicitly accepted. This is the part git history can't give you; don't skip it by only reading the diff.
3. Check whether this session continues or closes a gap left open in a prior `*_SESSION_SUMMARY.md`'s "Future considerations" — if so, say so explicitly (the existing docs cross-reference each other this way).

## Template

```markdown
# Session Summary — <Title>

**Date:** YYYY-MM-DD (commit `<short-hash>`, if applicable)
**Scope:** One sentence framing what this session covers and, if relevant,
which prior *_SESSION_SUMMARY.md it continues or closes a gap from.

<Optional: fenced ASCII flow/sequence diagram if the change is pipeline-shaped —
see the existing docs for the style (boxes, arrows, short inline annotations).>

## What this session built

<Intro paragraph — one or two sentences of orientation.>

### 1. <Subsection title — `path/to/file.py`>

<Prose. State the design problem, the resolution, and any tradeoff or rationale.
Name rejected alternatives when there were any. This is the section that
actually gets read later — invest in it.>

### 2. <Next subsection...>

### Bugs fixed along the way (not new work, but worth recording)

<Only include this subsection if applicable.>

## Files touched

| File | Status | Purpose |
|---|---|---|
| `path/to/file.py` | modified (+N/-M) | one-line purpose |

## Testing guide

\`\`\`bash
make test    # N passed (M existing + K new)
make lint    # no new violations
\`\`\`

Also verified live, not just via unit tests:
- <Manual checks actually performed this session — be specific and honest;
  don't list a check that wasn't actually run.>

Manual, end-to-end (needs the real thing running):
1. <Steps for anything that couldn't be automated/verified this session.>

## Future considerations

1. **<Bold lead-in>** — <description>. <Flag explicitly if this carries over
   from a prior summary's Future considerations list.>
```

## Output

- Filename: `<TOPIC>_SESSION_SUMMARY.md` in `SCREAMING_SNAKE_CASE`, matching the existing naming convention, written to the repo root (`SSP-Plus/`, the directory containing `CLAUDE.md` and `Makefile` — not the outer container folder if one exists above it).
- If the topic isn't obvious from the session, ask the user for a short slug rather than guessing.
- Only include sections that apply (e.g. skip "Bugs fixed along the way" if there weren't any) — don't pad the template with empty sections.
