# Progress deck style spec

Reverse-engineered from `progress_update_2026-07-16.pptx` and
`progress_update_2026-07-23.pptx` (both generated with `python-pptx` — confirmed
via `docProps/core.xml`'s `<dc:description>`). Unzip either file and grep
`ppt/slides/slide*.xml` for `srgbClr`/`typeface` to re-derive if this drifts.

## Canvas

- Widescreen: 13.333in × 7.5in
- Font: **Calibri** everywhere (titles, body, labels)

## Palette

| Role | Hex | Notes |
|---|---|---|
| Background (dark slides) | `#1A1A2E` | navy, used for title slide + section dividers |
| Panel / deep blue | `#1E2761` | card backgrounds, headers on light slides |
| Mid blue | `#2A3570` | secondary panel fill, arrow chain boxes |
| Secondary text | `#6B7280` | gray, captions/meta text |
| Light blue tint | `#E8EEFB` / `#CADCFC` | light-slide backgrounds, "before" state boxes |
| Amber accent | `#F2A93B` | headings on dark bg, big-number callouts, arrows |
| Amber tint | `#FCEBD0` | "after"/highlight state boxes on light slides |
| White | `#FFFFFF` | text on dark/blue backgrounds |

Two-tone contrast is the operating principle: dark navy/blue slides get white
and amber text; light slides (`#E8EEFB` family) get navy/deep-blue text with
amber as the only accent color. Don't introduce new hues.

## Slide catalog

Decks follow this shape, in order. Not every deck needs every slide type more
than once — repeat types 3 and 4 once per session/topic being reported on.

1. **Title** — big title (2 lines max), one subtitle line naming the session
   scope(s) separated by `·`, and a date line. Dark navy background.
2. **Overview** — a short "from X to Y" narrative sentence, then a 3-stage
   arrow chain (e.g. `Connect → Verify → Scale`) with a one-line label under
   each stage. Used to frame multiple sessions being reported together.
3. **How it works** (one per session) — a vertical step chain: boxes
   connected by downward arrows, each box a short label plus one line of
   detail. Mirrors an actual code/data flow (see the GUI-wiring example:
   OTP screen → verify_otp_for_source() → SessionManager → file_browser).
4. **What was built** (one per session) — stacked cards, each with a bold
   sub-heading and 2-4 bullets. One card per major component built that
   session.
5. **Tested and working** — one big number + label callout (e.g. "75
   automated tests / all passing offline"), plus two side-by-side bulleted
   columns: "Covered Offline" vs "Needs the Real Thing".
6. **What's next** — a grid or stack of titled action items, each with one
   sentence of description. Pull directly from the session summary's
   "Future considerations" section.

## Implementation

Use `scripts/deck_builder.py` in this skill directory — it exposes one
Python function per slide type above, plus the palette as constants, so a
new deck is a short content script, not hand-built XML/shapes.
