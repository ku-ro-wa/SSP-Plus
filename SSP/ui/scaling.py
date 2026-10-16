# ui/scaling.py
"""Whole-UI scale factor, so the kiosk looks the same size on any panel resolution.

Every screen is laid out in fixed pixels (QSS font sizes, setFixedSize, padding).
Rather than scale each of those, Qt scales the whole UI through QT_SCALE_FACTOR,
which must be set before the QApplication is created.

The same goes for the rest of the Qt environment: a desktop terminal and an SSH
shell on the kiosk export different Qt variables, and each one changed how the UI
rendered. pin_render_environment() makes every launch use the same values.
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


# Variables a desktop session sets (and an SSH shell doesn't) that change the
# style, palette, fonts or DPI scaling Qt renders with.
_SESSION_RENDER_VARS = (
    "QT_QPA_PLATFORMTHEME",
    "QT_STYLE_OVERRIDE",
    "QT_AUTO_SCREEN_SCALE_FACTOR",
    "QT_ENABLE_HIGHDPI_SCALING",
    "QT_SCREEN_SCALE_FACTORS",
    "QT_FONT_DPI",
)

# Platforms that draw nowhere (tests, headless runs over SSH); left as they are.
_HEADLESS_PLATFORMS = ("offscreen", "minimal")


def pin_render_environment(environ=os.environ, platform: str = sys.platform) -> None:
    """Make the UI render the same however the app was launched. Call before any
    QApplication exists (including apply_ui_scale's probe).

    On Linux the GUI always goes through X11 (xcb; Xwayland under the kiosk's labwc
    desktop) rather than whichever of X11/Wayland the launching shell picked, and
    the desktop's Qt theme and DPI variables are dropped. QT_SCALE_FACTOR is kept:
    apply_ui_scale treats it as a deliberate override.
    """
    for name in _SESSION_RENDER_VARS:
        environ.pop(name, None)
    if platform.startswith("linux") and environ.get("QT_QPA_PLATFORM") not in _HEADLESS_PLATFORMS:
        environ["QT_QPA_PLATFORM"] = "xcb"


def _primary_screen_height() -> int:
    """Height of the primary screen, read with a throwaway QApplication.

    On Linux this is the full screen: the kiosk window is fullscreen, and the space
    a taskbar reserves is reported differently by X11 and Wayland. Elsewhere (a dev
    laptop) the window is sized to the space left by the menu bar and Dock, as
    _setup_display does, so that's what has to fit.
    """
    probe = QApplication(sys.argv)
    screen = probe.primaryScreen()
    geometry = screen.geometry() if sys.platform.startswith("linux") else screen.availableGeometry()
    height = geometry.height()
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
