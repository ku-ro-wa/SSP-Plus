"""
Tests for PaymentAlgorithmManager — pure logic, no hardware or DB required.
The DatabaseManager is replaced with a MagicMock that returns configurable
coin inventory and settings, so these tests run on any laptop without a DB.
"""
from unittest.mock import MagicMock
from managers.payment_algorithm_manager import PaymentAlgorithmManager


def _make_db(coins_1=10, coins_5=5, settings=None):
    """Return a mock DatabaseManager with the given coin inventory.

    `settings` is read live, so a test can change it after the manager is built.
    """
    db = MagicMock()
    settings = {} if settings is None else settings
    db.get_setting.side_effect = lambda key, default=None: settings.get(key, default)
    db.get_cash_inventory.return_value = [
        {'type': 'coin', 'denomination': 1, 'count': coins_1},
        {'type': 'coin', 'denomination': 5, 'count': coins_5},
    ]
    return db


class TestCalculateChangeBreakdown:
    def test_zero_change(self):
        pam = PaymentAlgorithmManager(_make_db())
        assert pam.calculate_change_breakdown(0) == {1: 0, 5: 0}

    def test_exact_fives(self):
        pam = PaymentAlgorithmManager(_make_db())
        assert pam.calculate_change_breakdown(10) == {1: 0, 5: 2}

    def test_mixed(self):
        pam = PaymentAlgorithmManager(_make_db())
        assert pam.calculate_change_breakdown(6) == {1: 1, 5: 1}

    def test_ones_only(self):
        pam = PaymentAlgorithmManager(_make_db())
        assert pam.calculate_change_breakdown(3) == {1: 3, 5: 0}


class TestCanDispenseChange:
    def test_no_change_needed(self):
        pam = PaymentAlgorithmManager(_make_db())
        can, reason, req = pam.can_dispense_change(0)
        assert can is True

    def test_sufficient_inventory(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=5, coins_5=3))
        can, reason, req = pam.can_dispense_change(6)
        assert can is True

    def test_insufficient_fives(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=10, coins_5=0))
        can, reason, req = pam.can_dispense_change(10)
        assert can is False
        assert '₱5' in reason

    def test_insufficient_ones(self):
        # change=6 → needs 1x₱5 + 1x₱1, but coins_1=0
        pam = PaymentAlgorithmManager(_make_db(coins_1=0, coins_5=2))
        can, reason, req = pam.can_dispense_change(6)
        assert can is False
        assert '₱1' in reason


class TestValidatePayment:
    def test_underpayment(self):
        pam = PaymentAlgorithmManager(_make_db())
        valid, msg, info = pam.validate_payment(10.0, 8.0)
        assert valid is False

    def test_exact_payment(self):
        pam = PaymentAlgorithmManager(_make_db())
        valid, msg, info = pam.validate_payment(10.0, 10.0)
        assert valid is True
        assert info['change_amount'] == 0.0

    def test_overpayment_with_available_change(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=5, coins_5=5))
        valid, msg, info = pam.validate_payment(7.0, 10.0)
        assert valid is True
        assert info['change_amount'] == 3.0

    def test_overpayment_without_change(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=0, coins_5=0))
        valid, msg, info = pam.validate_payment(7.0, 10.0)
        assert valid is False


class TestFindBestPaymentAmount:
    def test_exact_when_no_coins(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=0, coins_5=0))
        result = pam.find_best_payment_amount(7.0)
        assert result['change'] == 0.0
        assert result['amount'] == 7.0

    def test_amount_always_covers_cost(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=5, coins_5=4))
        result = pam.find_best_payment_amount(7.0)
        assert result['amount'] >= 7.0

    def test_change_is_feasible(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=5, coins_5=4))
        result = pam.find_best_payment_amount(7.0)
        can, _, _ = pam.can_dispense_change(result['change'])
        assert can is True

    def test_change_matches_difference(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=5, coins_5=4))
        result = pam.find_best_payment_amount(9.0)
        assert abs(result['amount'] - 9.0 - result['change']) < 0.01


class TestMaxDispensableChange:
    def test_sums_coins(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2))
        assert pam.get_max_dispensable_change() == 13

    def test_respects_reserve_thresholds(self):
        settings = {'min_coin_threshold_1': 2, 'min_coin_threshold_5': 1}
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=settings))
        assert pam.get_max_dispensable_change() == 6

    def test_capped_by_max_change_limit(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 50}))
        assert pam.get_max_dispensable_change() == 50


class TestIsChangeLow:
    def test_below_default_threshold(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=4, coins_5=3))  # ₱19
        assert pam.is_change_low() is True

    def test_at_default_threshold_is_not_low(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=5, coins_5=3))  # ₱20
        assert pam.is_change_low() is False

    def test_threshold_read_from_settings(self):
        settings = {'low_change_warning_threshold': 50}
        pam = PaymentAlgorithmManager(_make_db(coins_1=10, coins_5=5, settings=settings))  # ₱35
        assert pam.is_change_low() is True

    def test_unparseable_threshold_falls_back_to_default(self):
        settings = {'low_change_warning_threshold': 'lots'}
        pam = PaymentAlgorithmManager(_make_db(coins_1=4, coins_5=3, settings=settings))  # ₱19
        assert pam.is_change_low() is True


class TestSettingsReadLive:
    """A saved setting applies to an already-built manager (the payment screen keeps one)."""

    def test_max_change_limit_applies_without_rebuilding(self):
        settings = {'max_change_limit': 50}
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings=settings))
        assert pam.get_max_dispensable_change() == 50
        settings['max_change_limit'] = 20
        assert pam.get_max_dispensable_change() == 20

    def test_reserves_apply_without_rebuilding(self):
        settings = {}
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=settings))
        assert pam.get_max_dispensable_change() == 13
        settings['min_coin_threshold_1'] = 2
        settings['min_coin_threshold_5'] = 1
        assert pam.get_max_dispensable_change() == 6

    def test_unparseable_values_fall_back_to_defaults(self):
        settings = {'max_change_limit': 'lots', 'min_coin_threshold_1': 'x'}
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings=settings))
        assert pam.MAX_CHANGE_LIMIT == 50.0
        assert pam.MIN_COIN_THRESHOLDS == {1: 0, 5: 0}

    def test_negative_reserve_is_treated_as_zero(self):
        pam = PaymentAlgorithmManager(_make_db(settings={'min_coin_threshold_5': -3}))
        assert pam.MIN_COIN_THRESHOLDS[5] == 0


class TestBestPaymentRespectsMaxChange:
    def test_max_payment_is_cost_plus_max_change(self):
        # cost ₱50, Maximum change ₱25: the customer can pay up to ₱75 in any mix of
        # bills and coins (₱20 bills: 20+20+20 = ₱60 still gets ₱10 back as coins)
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 25}))
        result = pam.find_best_payment_amount(50.0)
        assert result['amount'] == 75.0
        assert result['change'] == 25.0
        assert '₱75.00' in result['reason']

    def test_not_rounded_down_to_a_bill(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 10}))
        result = pam.find_best_payment_amount(7.0)
        assert result['amount'] == 17.0 and result['change'] == 10.0

    def test_zero_limit_means_exact_payment(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 0}))
        result = pam.find_best_payment_amount(7.0)
        assert result['amount'] == 7.0 and result['change'] == 0.0

    def test_limited_by_stock_when_below_the_cap(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=3, coins_5=0, settings={'max_change_limit': 50}))
        result = pam.find_best_payment_amount(7.0)
        assert result['amount'] == 10.0 and result['change'] == 3.0

    def test_suggestion_follows_a_changed_limit(self):
        settings = {'max_change_limit': 100}
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings=settings))
        assert pam.find_best_payment_amount(7.0)['amount'] == 107.0
        settings['max_change_limit'] = 10
        assert pam.find_best_payment_amount(7.0)['amount'] == 17.0

    def test_required_coins_match_the_change(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 25}))
        result = pam.find_best_payment_amount(50.0)
        assert result['required_coins'] == {1: 0, 5: 5}


def _planned(owed, limits):
    """What ChangeDispenser plans to pay out for `owed` under `limits` (its own formula)."""
    fives = min(owed // 5, limits[5])
    return fives * 5 + min(owed - fives * 5, limits[1])


class TestDispenseLimits:
    def test_big_overpayment_is_capped_at_max_change(self):
        # ₱100 bill on a ₱3 job: ₱97 owed, but only ₱50 is paid in coins
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 50}))
        limits = pam.get_dispense_limits(97)
        assert limits == {5: 10, 1: 0}
        assert _planned(97, limits) == 50

    def test_cap_is_topped_up_with_ones_when_fives_run_short(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=3, settings={'max_change_limit': 50}))
        limits = pam.get_dispense_limits(97)
        assert limits == {5: 3, 1: 35}
        assert _planned(97, limits) == 50

    def test_reserves_are_held_back(self):
        settings = {'max_change_limit': 1000, 'min_coin_threshold_1': 2, 'min_coin_threshold_5': 1}
        pam = PaymentAlgorithmManager(_make_db(coins_1=10, coins_5=4, settings=settings))
        assert pam.get_dispense_limits(97) == {5: 3, 1: 8}

    def test_small_change_under_the_cap_is_untouched(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=10, coins_5=5))
        limits = pam.get_dispense_limits(3)
        assert limits == {5: 0, 1: 3}
        assert _planned(3, limits) == 3

    def test_zero_limit_pays_nothing_in_coins(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 0}))
        assert pam.get_dispense_limits(97) == {5: 0, 1: 0}

    def test_follows_a_changed_limit_without_rebuilding(self):
        settings = {'max_change_limit': 50}
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings=settings))
        assert _planned(97, pam.get_dispense_limits(97)) == 50
        settings['max_change_limit'] = 20
        assert _planned(97, pam.get_dispense_limits(97)) == 20

    def test_never_plans_more_than_the_cap_or_the_stock(self):
        for cap in (0, 7, 50):
            for ones in (0, 4, 100):
                for fives in (0, 3, 100):
                    pam = PaymentAlgorithmManager(_make_db(
                        coins_1=ones, coins_5=fives, settings={'max_change_limit': cap}))
                    for owed in range(0, 120):
                        limits = pam.get_dispense_limits(owed)
                        planned = _planned(owed, limits)
                        assert planned <= min(cap, owed)
                        assert limits[5] <= fives and limits[1] <= ones