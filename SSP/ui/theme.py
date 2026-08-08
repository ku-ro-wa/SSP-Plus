# ui/theme.py
"""Design tokens and QSS for the app's shared visual theme (single light theme)."""

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

COLORS = {
    "bg": "#FFFFFF",
    "bg_subtle": "#F7F7F5",
    "border": "#E9E9E7",
    "border_strong": "#DFDFDD",
    "text": "#37352F",
    "text_secondary": "#787774",
    "text_muted": "#9B9A97",
    "primary": "#2F7D5C",
    "primary_hover": "#256B4D",
    "primary_pressed": "#1E5A40",
    "danger": "#EB5757",
    "danger_bg": "#FDEDED",
    "success": "#2F7D5C",
    "success_bg": "#EAF5EF",
    "warning": "#B8720A",
    "warning_bg": "#FDF3E2",
}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 40}

RADIUS = {"sm": 6, "md": 10, "lg": 14}

FONT = {
    "family": '"Segoe UI", "Helvetica Neue", Arial, sans-serif',
    "size_sm": 13,
    "size_md": 15,
    "size_lg": 18,
    "size_xl": 24,
    "size_display": 40,
}

# Scoped via setObjectName so these never leak onto unrelated widgets.
CARD_QSS = f"""
QFrame#Card {{
    background-color: {COLORS["bg"]};
    border: 1px solid {COLORS["border"]};
    border-radius: {RADIUS["lg"]}px;
}}
QFrame#Card:hover {{
    background-color: {COLORS["bg_subtle"]};
    border: 1px solid {COLORS["primary"]};
}}
QFrame#Card:disabled {{
    background-color: {COLORS["bg_subtle"]};
    border: 1px solid {COLORS["border"]};
}}
QFrame#Card QLabel {{
    background: transparent;
    border: none;
}}
QFrame#Card:disabled QLabel {{
    color: {COLORS["text_muted"]};
}}
"""

PRIMARY_BUTTON_QSS = f"""
QPushButton#PrimaryButton {{
    background-color: {COLORS["primary"]};
    color: {COLORS["bg"]};
    font-size: {FONT["size_md"]}px;
    font-weight: 600;
    border: none;
    border-radius: {RADIUS["md"]}px;
    padding: {SPACING["sm"]}px {SPACING["lg"]}px;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {COLORS["primary_hover"]};
}}
QPushButton#PrimaryButton:pressed {{
    background-color: {COLORS["primary_pressed"]};
}}
"""

SECONDARY_BUTTON_QSS = f"""
QPushButton#SecondaryButton {{
    background-color: {COLORS["bg"]};
    color: {COLORS["text_secondary"]};
    font-size: {FONT["size_sm"]}px;
    border: 1px solid {COLORS["border_strong"]};
    border-radius: {RADIUS["sm"]}px;
    padding: {SPACING["xs"]}px {SPACING["md"]}px;
}}
QPushButton#SecondaryButton:hover {{
    background-color: {COLORS["bg_subtle"]};
    color: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
}}
QPushButton#SecondaryButton:pressed {{
    background-color: {COLORS["border"]};
}}
"""


HEADER_QSS = f"""
QFrame#Header {{
    background-color: {COLORS["bg"]};
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
}}
QFrame#Header QLabel {{
    background: transparent;
    border: none;
}}
"""


_STATUS_BANNER_VARIANTS = {
    "success": (COLORS["success"], COLORS["success_bg"]),
    "warning": (COLORS["warning"], COLORS["warning_bg"]),
    "error": (COLORS["danger"], COLORS["danger_bg"]),
}


def status_banner_qss(variant: str) -> str:
    """QSS for StatusBanner in a given state: 'success' | 'warning' | 'error'."""
    color, bg = _STATUS_BANNER_VARIANTS[variant]
    return f"""
    QFrame#StatusBanner {{
        background-color: {bg};
        border: 1px solid {color};
        border-radius: {RADIUS["md"]}px;
    }}
    QFrame#StatusBanner QLabel {{
        color: {color};
        font-size: {FONT["size_sm"]}px;
        font-weight: 600;
        background: transparent;
        border: none;
    }}
    """


def build_stylesheet() -> str:
    """Base app-wide QSS: generic tag selectors only, no widget-specific rules."""
    return f"""
    QWidget {{
        font-family: {FONT["family"]};
        color: {COLORS["text"]};
    }}
    QLabel {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {COLORS["bg_subtle"]};
        width: 10px;
        border-radius: {RADIUS["sm"]}px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLORS["border_strong"]};
        border-radius: {RADIUS["sm"]}px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """


def apply_theme(app: QApplication) -> None:
    app.setFont(QFont("Segoe UI", FONT["size_md"]))
    app.setStyleSheet(build_stylesheet())
