"""
ChangeDispenser.dispense_change in simulated mode (no pigpio): how it reports
what physically came out when a hopper stops early, and how it plans around
the coins actually in the hoppers. _dispense_coin is the per-coin hardware
seam; tests replace it to make a hopper fail after N coins.
"""
import pytest

import managers.hopper_manager as hm
from managers.hopper_manager import ChangeDispenser


@pytest.fixture
def dispenser(monkeypatch):
    monkeypatch.setattr(hm, 'SIM_COIN_SECONDS', 0)
    d = ChangeDispenser()
    d.simulated = True
    return d


def fail_after(dispenser, monkeypatch, denomination, n):
    """Make the `denomination` hopper fail on its (n+1)th coin."""
    real = dispenser._dispense_coin
    count = {'n': 0}

    def coin(denom):
        if denom == denomination:
            count['n'] += 1
            if count['n'] > n:
                return False
        return real(denom)
    monkeypatch.setattr(dispenser, '_dispense_coin', coin)


class TestFullDispense:
    def test_reports_everything_dispensed(self, dispenser):
        result = dispenser.dispense_change(13)
        assert result['success'] is True
        assert (result['coins_5'], result['coins_1']) == (2, 3)
        assert (result['actual_change'], result['expected_change']) == (13, 13)
        assert result['stopped_early'] is False


class TestHopperStopsEarly:
    def test_one_peso_hopper_failure_is_not_success(self, dispenser, monkeypatch):
        fail_after(dispenser, monkeypatch, 1, 1)
        result = dispenser.dispense_change(8)
        assert result['success'] is False
        assert result['stopped_early'] is True
        assert result['error'] == 'hopper_stopped_early'
        assert (result['actual_change'], result['expected_change']) == (6, 8)

    def test_five_peso_failure_is_topped_up_with_ones(self, dispenser, monkeypatch):
        fail_after(dispenser, monkeypatch, 5, 1)
        result = dispenser.dispense_change(15)
        assert (result['coins_5'], result['coins_1']) == (1, 10)
        assert result['actual_change'] == 15
        assert result['stopped_early'] is True


class TestCoinLimits:
    def test_plan_is_capped_by_coin_limits(self, dispenser):
        result = dispenser.dispense_change(13, coin_limits={5: 1, 1: 2})
        assert (result['coins_5'], result['coins_1']) == (1, 2)
        assert (result['actual_change'], result['planned_change'], result['expected_change']) == (7, 7, 13)
        assert result['success'] is True
        assert result['stopped_early'] is False

    def test_top_up_after_a_five_failure_respects_the_ones_limit(self, dispenser, monkeypatch):
        fail_after(dispenser, monkeypatch, 5, 0)
        result = dispenser.dispense_change(10, coin_limits={5: 2, 1: 3})
        assert (result['coins_5'], result['coins_1']) == (0, 3)
        assert result['planned_change'] == 10
