# ui/scaling.py
"""Whole-UI scale factor, so the kiosk looks the same size on any panel resolution.

Every screen is laid out in fixed pixels (QSS font sizes, setFixedSize, padding).
Rather than scale each of those, Qt scales the whole UI through QT_SCALE_FACTOR,
which must be set before the QApplication is created.
"""

import os
import sys

from PyQt5.QtWidgets import QApplication

# Logical height every screen must fit in. The tallest screens need ~790px at
# 1x (scan_destination; scanner, admin and payment-with-keypad are ~730-740),
# so the auto scale keeps the logical height at or above this.
DESIGN_HEIGHT = 800


def ui_scale_factor(screen_height: int, setting: str = "") -> float:
    """Scale for a screen `screen_height` physical pixels tall.

    `setting` is the UI_SCALE value: a number forces that scale; blank or "auto"
    scales so the screen is DESIGN_HEIGHT logical pixels tall, never below 1.
    """
    setting = setting.strip().lower()
    if setting and setting != "auto":
        scale = float(setting)
        if scale <= 0:
            raise ValueError(f"UI_SCALE must be positive, got {setting!r}")
        return scale
    return max(1.0, round(screen_height / DESIGN_HEIGHT, 2))


def _primary_screen_height() -> int:
    """Height of the primary screen (as _setup_display sizes the window), read with
    a throwaway QApplication."""
    probe = QApplication(sys.argv)
    height = probe.primaryScreen().availableGeometry().height()
    del probe
    return height


def apply_ui_scale(setting: str) -> float:
    """Set QT_SCALE_FACTOR from UI_SCALE. Call before creating the real QApplication.

    A QT_SCALE_FACTOR already in the environment wins, and a numeric UI_SCALE skips
    probing the screen.
    """
    if "QT_SCALE_FACTOR" in os.environ:
        return float(os.environ["QT_SCALE_FACTOR"])
    setting = setting.strip().lower()
    height = 0 if setting and setting != "auto" else _primary_screen_height()
    scale = ui_scale_factor(height, setting)
    if scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(scale)
    return scale
