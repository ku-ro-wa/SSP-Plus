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
QPushButton#PrimaryButton:disabled {{
    background-color: {COLORS["border_strong"]};
    color: {COLORS["text_muted"]};
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


DANGER_BUTTON_QSS = f"""
QPushButton#DangerButton {{
    background-color: {COLORS["danger"]};
    color: {COLORS["bg"]};
    font-size: {FONT["size_md"]}px;
    font-weight: 600;
    border: none;
    border-radius: {RADIUS["md"]}px;
    padding: {SPACING["sm"]}px {SPACING["lg"]}px;
}}
QPushButton#DangerButton:hover {{
    background-color: #C94141;
}}
QPushButton#DangerButton:pressed {{
    background-color: #B23A3A;
}}
QPushButton#DangerButton:disabled {{
    background-color: {COLORS["border_strong"]};
    color: {COLORS["text_muted"]};
}}
"""

HEADER_QSS = f"""
QFrame#Header {{
    background-color: {COLORS["text"]};
    border: none;
    border-bottom: 1px solid {COLORS["primary"]};
}}
QFrame#Header QLabel {{
    background: transparent;
    border: none;
    color: {COLORS["bg"]};
}}
"""


# Operator-panel building blocks (admin / data_viewer). Scoped by tag/objectName
# so they only bite where the screen opts in by calling setStyleSheet with them.
GROUPBOX_QSS = f"""
QGroupBox {{
    color: {COLORS["text_secondary"]};
    font-size: {FONT["size_sm"]}px;
    font-weight: 600;
    border: 1px solid {COLORS["border_strong"]};
    border-radius: {RADIUS["md"]}px;
    margin-top: 12px;
    padding-top: 14px;
    background-color: {COLORS["bg"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QGroupBox QLabel {{
    background: transparent;
    border: none;
}}
"""

INPUT_QSS = f"""
QLineEdit {{
    background-color: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-size: {FONT["size_md"]}px;
    border: 1px solid {COLORS["border_strong"]};
    border-radius: {RADIUS["sm"]}px;
    padding: {SPACING["xs"]}px {SPACING["md"]}px;
    min-height: 44px;
}}
QLineEdit:focus {{
    border: 1px solid {COLORS["primary"]};
}}
"""

TABLE_QSS = f"""
QTableWidget {{
    background-color: {COLORS["bg"]};
    alternate-background-color: {COLORS["bg_subtle"]};
    color: {COLORS["text"]};
    gridline-color: {COLORS["border"]};
    border: 1px solid {COLORS["border"]};
    border-radius: {RADIUS["sm"]}px;
    font-size: {FONT["size_sm"]}px;
}}
QHeaderView::section {{
    background-color: {COLORS["bg_subtle"]};
    color: {COLORS["text_secondary"]};
    font-weight: 600;
    padding: 8px;
    border: none;
    border-bottom: 1px solid {COLORS["border_strong"]};
}}
QTableWidget::item {{
    padding: 6px;
    border-bottom: 1px solid {COLORS["border"]};
}}
QTableWidget::item:selected {{
    background-color: {COLORS["success_bg"]};
    color: {COLORS["text"]};
}}
"""

TAB_QSS = f"""
QTabWidget::pane {{
    border: 1px solid {COLORS["border"]};
    border-radius: {RADIUS["sm"]}px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {COLORS["bg_subtle"]};
    color: {COLORS["text_secondary"]};
    font-size: {FONT["size_sm"]}px;
    font-weight: 600;
    padding: 10px 20px;
    margin-right: 2px;
    border: 1px solid {COLORS["border"]};
    border-bottom: none;
    border-top-left-radius: {RADIUS["sm"]}px;
    border-top-right-radius: {RADIUS["sm"]}px;
    min-height: 40px;
    min-width: 140px;
}}
QTabBar::tab:selected {{
    background-color: {COLORS["bg"]};
    color: {COLORS["primary"]};
    border-bottom: 2px solid {COLORS["primary"]};
}}
QTabBar::tab:hover:!selected {{
    color: {COLORS["text"]};
}}
"""


def severity_color(value: float, warn_at: float, crit_at: float) -> str:
    """Theme colour for a supply level: danger at/below crit_at, warning at/below
    warn_at, success above. Used for admin paper/coin/ink readouts."""
    if value <= crit_at:
        return COLORS["danger"]
    if value <= warn_at:
        return COLORS["warning"]
    return COLORS["success"]


_STATUS_BANNER_VARIANTS = {
    "success": (COLORS["success"], COLORS["success_bg"]),
    "warning": (COLORS["warning"], COLORS["warning_bg"]),
    "error": (COLORS["danger"], COLORS["danger_bg"]),
    "info": (COLORS["text_secondary"], COLORS["bg_subtle"]),
}


def status_banner_qss(variant: str) -> str:
    """QSS for StatusBanner in a given state: 'success' | 'warning' | 'error' | 'info'."""
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
