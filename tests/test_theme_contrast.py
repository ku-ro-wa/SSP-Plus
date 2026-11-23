"""WCAG 2.x contrast of the theme's colour pairs (computed, so the claim in ui/theme.py is checked)."""

import pytest

from ui.theme import COLORS


def _lum(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    hi, lo = sorted([_lum(fg), _lum(bg)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background, minimum): 4.5 = AA for normal text (SC 1.4.3).
TEXT_PAIRS = [
    ("text", "bg", 7.0),
    ("text_secondary", "bg", 7.0),
    ("text_muted", "bg", 4.5),
    ("text_muted", "bg_subtle", 4.5),
    ("bg", "primary", 4.5),   # button / banner label
    ("bg", "danger", 4.5),    # danger button label
    ("bg", "warning", 4.5),   # file browser's Deselect All
    ("danger", "bg", 4.5),
    ("danger", "danger_bg", 4.5),
    ("warning", "bg", 4.5),
    ("warning", "warning_bg", 4.5),
    ("success", "bg", 4.5),
    ("success", "success_bg", 4.5),
    ("text_secondary", "bg_subtle", 4.5),  # info banner
    ("text", "success_bg", 4.5),           # selected table row
]


@pytest.mark.parametrize("fg,bg,minimum", TEXT_PAIRS)
def test_text_pair_meets_minimum(fg, bg, minimum):
    assert ratio(COLORS[fg], COLORS[bg]) >= minimum, f"{fg} on {bg}: {ratio(COLORS[fg], COLORS[bg]):.2f}"
