"""KIOSK_MODEL picks the acceptor and hopper pin set; a pin set in .env overrides it."""
import pytest

from config import KIOSK_MODEL_PINS, get_config

PIN_PROPERTIES = {
    'COIN_PIN': 'coin_pin',
    'BILL_PIN': 'bill_pin',
    'COIN_INHIBIT_PIN': 'coin_inhibit_pin',
    'BILL_INHIBIT_PIN': 'bill_inhibit_pin',
    'HOPPER_A_SIGNAL_PIN': 'hopper_a_signal_pin',
    'HOPPER_A_ENABLE_PIN': 'hopper_a_enable_pin',
    'HOPPER_B_SIGNAL_PIN': 'hopper_b_signal_pin',
    'HOPPER_B_ENABLE_PIN': 'hopper_b_enable_pin',
}


@pytest.fixture
def cfg(monkeypatch):
    """Config with no KIOSK_MODEL or pin keys, whatever the local .env holds."""
    for key in ['KIOSK_MODEL', *PIN_PROPERTIES]:
        monkeypatch.delenv(key, raising=False)
    return get_config()


def pins(cfg):
    return {key: getattr(cfg, prop) for key, prop in PIN_PROPERTIES.items()}


def test_unset_model_uses_old_wiring(cfg):
    assert cfg.kiosk_model == 'old'
    assert pins(cfg) == KIOSK_MODEL_PINS['old']


def test_blank_model_uses_old_wiring(cfg, monkeypatch):
    monkeypatch.setenv('KIOSK_MODEL', '')
    assert pins(cfg) == KIOSK_MODEL_PINS['old']


@pytest.mark.parametrize('model', ['old', 'new', 'NEW', ' new '])
def test_model_selects_its_pin_set(cfg, monkeypatch, model):
    monkeypatch.setenv('KIOSK_MODEL', model)
    assert pins(cfg) == KIOSK_MODEL_PINS[model.strip().lower()]


def test_new_model_wiring(cfg, monkeypatch):
    monkeypatch.setenv('KIOSK_MODEL', 'new')
    assert (cfg.coin_pin, cfg.hopper_a_signal_pin, cfg.hopper_b_signal_pin) == (17, 26, 9)


def test_pin_in_env_overrides_model(cfg, monkeypatch):
    monkeypatch.setenv('KIOSK_MODEL', 'new')
    monkeypatch.setenv('COIN_PIN', '12')
    assert cfg.coin_pin == 12
    assert cfg.hopper_a_signal_pin == 26


def test_unknown_model_fails_loudly(cfg, monkeypatch):
    monkeypatch.setenv('KIOSK_MODEL', 'v3')
    with pytest.raises(ValueError, match='KIOSK_MODEL'):
        cfg.coin_pin


def test_every_model_sets_every_pin_without_clashes():
    for model, pin_set in KIOSK_MODEL_PINS.items():
        assert set(pin_set) == set(PIN_PROPERTIES), model
        assert len(set(pin_set.values())) == len(pin_set), f"{model} reuses a GPIO"
