# ui/icons.py
"""Loader helpers for the app's SVG icon set (SSP/assets/icons/*.svg)."""

import os

from PyQt5.QtGui import QIcon
from PyQt5.QtSvg import QSvgWidget


def _icons_dir() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(current_dir, '..', 'assets', 'icons'))


def _icon_path(name: str) -> str:
    return os.path.join(_icons_dir(), f'{name}.svg')


def icon_path(name: str) -> str:
    """Public accessor for a named icon's file path (e.g. for QSvgWidget.load())."""
    return _icon_path(name)


def icon(name: str) -> QIcon:
    """For QPushButton.setIcon() / QAction contexts."""
    path = _icon_path(name)
    if not os.path.exists(path):
        print(f"WARNING: Icon not found at '{path}'.")
        return QIcon()
    return QIcon(path)


def svg_widget(name: str, size=(24, 24)) -> QSvgWidget:
    """For placing an SVG as a layout child (e.g. inside a Card)."""
    path = _icon_path(name)
    if not os.path.exists(path):
        print(f"WARNING: Icon not found at '{path}'.")
    widget = QSvgWidget(path)
    widget.setFixedSize(*size)
    return widget
