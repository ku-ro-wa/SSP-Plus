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

    def test_low_coin_warning_levels_do_not_reduce_it(self):
        settings = {'min_coin_threshold_1': 2, 'min_coin_threshold_5': 1}
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=settings))
        assert pam.get_max_dispensable_change() == 13

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

    def test_warning_levels_are_read_live_but_never_limit_change(self):
        settings = {}
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=settings))
        assert pam.get_max_dispensable_change() == 13
        settings['min_coin_threshold_1'] = 2
        settings['min_coin_threshold_5'] = 1
        assert pam.MIN_COIN_THRESHOLDS == {1: 2, 5: 1}
        assert pam.get_max_dispensable_change() == 13

    def test_unparseable_values_fall_back_to_defaults(self):
        settings = {'max_change_limit': 'lots', 'min_coin_threshold_1': 'x'}
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings=settings))
        assert pam.MAX_CHANGE_LIMIT == 50.0
        assert pam.MIN_COIN_THRESHOLDS == {1: 0, 5: 0}

    def test_negative_reserve_is_treated_as_zero(self):
        pam = PaymentAlgorithmManager(_make_db(settings={'min_coin_threshold_5': -3}))
        assert pam.MIN_COIN_THRESHOLDS[5] == 0


class TestBestPaymentDisplay:
    """The 'Max payment we can receive (available ...)' line: the largest accepted
    denomination (1, 5, 10, 20, 50, 100) whose change the hoppers can cover."""

    def test_largest_denomination_whose_change_fits(self):
        # ₱13 in the hoppers, cost ₱7: ceiling ₱20, so pay ₱20 and get ₱13 back
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2))
        result = pam.find_best_payment_amount(7.0)
        assert result['amount'] == 20.0 and result['change'] == 13.0
        assert result['reason'] == 'Max payment we can receive: ₱20.00 (available ₱13.00)'

    def test_rounds_down_to_a_denomination(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100))
        result = pam.find_best_payment_amount(50.0)
        assert result['amount'] == 100.0 and result['change'] == 50.0

    def test_exact_when_nothing_fits(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=0, coins_5=0))
        result = pam.find_best_payment_amount(7.0)
        assert result['amount'] == 7.0 and result['reason'] == 'Exact payment'

    def test_follows_hopper_stock(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=0, coins_5=1))
        result = pam.find_best_payment_amount(5.0)
        assert result['amount'] == 10.0 and result['change'] == 5.0

    def test_low_coin_warning_levels_do_not_change_it(self):
        settings = {'min_coin_threshold_1': 50, 'min_coin_threshold_5': 50}
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=settings))
        assert pam.find_best_payment_amount(7.0)['amount'] == 20.0


class TestAvailableMatchesThePayout:
    """'available' on the max-payment line is the coin change actually paid; change
    owed beyond Maximum change is a Voucher."""

    def test_available_is_capped_at_max_change(self):
        # ₱3 job, plenty of coins: ₱100 is still the max payment, but only ₱50 comes
        # out in coins and the other ₱47 is a voucher
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 50}))
        result = pam.find_best_payment_amount(3.0)
        assert result['amount'] == 100.0
        assert result['change'] == 50.0 and result['voucher'] == 47.0
        assert result['required_coins'] == {1: 0, 5: 10}
        assert result['reason'] == 'Max payment we can receive: ₱100.00 (available ₱50.00)'

    def test_smaller_limit(self):
        pam = PaymentAlgorithmManager(
            _make_db(coins_1=100, coins_5=100, settings={'max_change_limit': 25}))
        result = pam.find_best_payment_amount(50.0)
        assert result['amount'] == 100.0
        assert result['change'] == 25.0 and result['voucher'] == 25.0

    def test_under_the_limit_nothing_is_vouchered(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2))
        result = pam.find_best_payment_amount(7.0)
        assert result['change'] == 13.0 and result['voucher'] == 0.0

    def test_exact_payment_has_no_voucher(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=0, coins_5=0))
        assert pam.find_best_payment_amount(7.0)['voucher'] == 0.0

    def test_follows_a_changed_limit_without_rebuilding(self):
        settings = {'max_change_limit': 50}
        pam = PaymentAlgorithmManager(_make_db(coins_1=100, coins_5=100, settings=settings))
        assert pam.find_best_payment_amount(3.0)['change'] == 50.0
        settings['max_change_limit'] = 20
        assert pam.find_best_payment_amount(3.0)['change'] == 20.0

    def test_always_equals_what_the_dispenser_would_pay(self):
        for cap in (0, 7, 25, 50, 1000):
            for ones in (0, 4, 100):
                for fives in (0, 3, 100):
                    pam = PaymentAlgorithmManager(_make_db(
                        coins_1=ones, coins_5=fives, settings={'max_change_limit': cap}))
                    for cost in (3.0, 7.0, 50.0):
                        r = pam.find_best_payment_amount(cost)
                        owed = int(r['amount'] - cost)
                        assert r['change'] + r['voucher'] == owed
                        assert r['change'] == _planned(owed, pam.get_dispense_limits(owed))
                        assert r['change'] <= cap
                        assert r['required_coins'][5] * 5 + r['required_coins'][1] == r['change']


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

    def test_low_coin_warning_levels_do_not_hold_coins_back(self):
        settings = {'max_change_limit': 1000, 'min_coin_threshold_1': 2, 'min_coin_threshold_5': 1}
        pam = PaymentAlgorithmManager(_make_db(coins_1=10, coins_5=4, settings=settings))
        assert pam.get_dispense_limits(97) == {5: 4, 1: 10}

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


class TestLowCoinWarningLevelsAreDisplayOnly:
    """'Warn when coins fall to n' only drives the low-coin display. It must not change
    what the kiosk accepts or pays out, even when a hopper is under n."""
    SETTINGS = {'min_coin_threshold_1': 50, 'min_coin_threshold_5': 50}

    def test_change_can_be_dispensed_with_hoppers_under_the_level(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=dict(self.SETTINGS)))
        can, reason, req = pam.can_dispense_change(13)
        assert can is True and req == {1: 3, 5: 2}

    def test_max_payment_ignores_the_level(self):
        with_level = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=dict(self.SETTINGS)))
        without = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2))
        assert with_level.find_best_payment_amount(7.0) == without.find_best_payment_amount(7.0)
        assert with_level.find_best_payment_amount(7.0)['amount'] == 20.0

    def test_payout_limits_ignore_the_level(self):
        with_level = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=dict(self.SETTINGS)))
        assert with_level.get_dispense_limits(13) == {5: 2, 1: 3}

    def test_validate_payment_ignores_the_level(self):
        pam = PaymentAlgorithmManager(_make_db(coins_1=3, coins_5=2, settings=dict(self.SETTINGS)))
        valid, _, info = pam.validate_payment(7.0, 20.0)
        assert valid is True and info['change_amount'] == 13.0