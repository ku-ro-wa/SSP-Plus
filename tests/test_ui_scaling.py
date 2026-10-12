"""
Tests for the whole-UI scale factor (ui/scaling.py): screen height and the
UI_SCALE setting -> QT_SCALE_FACTOR. No QApplication is created.
"""
import os

import pytest

from ui import scaling
from ui.scaling import DESIGN_HEIGHT, apply_ui_scale, ui_scale_factor


@pytest.mark.parametrize("height, expected", [
    (1080, 1.35),
    (1200, 1.5),
    (DESIGN_HEIGHT, 1.0),
    (720, 1.0),   # never shrinks below 1x on small panels
    (480, 1.0),
])
def test_auto_scales_to_design_height(height, expected):
    assert ui_scale_factor(height) == expected
    assert ui_scale_factor(height, "auto") == expected
    assert ui_scale_factor(height, " AUTO ") == expected


def test_auto_keeps_every_screen_on_a_1080_panel():
    assert 1080 / ui_scale_factor(1080) >= DESIGN_HEIGHT


def test_number_overrides_screen_height():
    assert ui_scale_factor(1080, "1.5") == 1.5
    assert ui_scale_factor(480, "0.8") == 0.8


@pytest.mark.parametrize("setting", ["0", "-1", "big"])
def test_bad_setting_raises(setting):
    with pytest.raises(ValueError):
        ui_scale_factor(1080, setting)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    monkeypatch.setattr(scaling, "_primary_screen_height", lambda: 1080)
    return monkeypatch


def test_apply_sets_qt_scale_factor_from_screen(env):
    assert apply_ui_scale("") == 1.35
    assert os.environ["QT_SCALE_FACTOR"] == "1.35"


def test_apply_numeric_setting_skips_screen_probe(env):
    def no_probe():
        raise AssertionError("probed the screen")
    env.setattr(scaling, "_primary_screen_height", no_probe)
    assert apply_ui_scale("1.2") == 1.2
    assert os.environ["QT_SCALE_FACTOR"] == "1.2"


def test_apply_leaves_env_unset_at_1x(env):
    env.setattr(scaling, "_primary_screen_height", lambda: 720)
    assert apply_ui_scale("") == 1.0
    assert "QT_SCALE_FACTOR" not in os.environ


def test_apply_respects_existing_qt_scale_factor(env):
    env.setenv("QT_SCALE_FACTOR", "2")
    assert apply_ui_scale("1.2") == 2.0
