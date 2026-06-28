"""
Tests for PaymentAlgorithmManager — pure logic, no hardware or DB required.
The DatabaseManager is replaced with a MagicMock that returns configurable
coin inventory and settings, so these tests run on any laptop without a DB.
"""
from unittest.mock import MagicMock
from managers.payment_algorithm_manager import PaymentAlgorithmManager


def _make_db(coins_1=10, coins_5=5, settings=None):
    """Return a mock DatabaseManager with the given coin inventory."""
    db = MagicMock()
    settings = settings or {}
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
