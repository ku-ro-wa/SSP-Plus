# managers/payment_algorithm_manager.py

from typing import Dict, List, Tuple
from database.db_manager import DatabaseManager

DEFAULT_LOW_CHANGE_THRESHOLD = 20  # ₱, fallback if 'low_change_warning_threshold' is unset


class PaymentAlgorithmManager:
    """
    Manages payment processing with intelligent change availability checking.
    Considers limited coin inventory to suggest optimal payment amounts.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        # Coin denominations available in the system
        self.COIN_DENOMINATIONS = [1, 5]  # ₱1 and ₱5 coins
        self.BILL_DENOMINATIONS = [20, 50, 100, 200, 500, 1000]  # Common Philippine bills

    def _setting_number(self, key, default):
        """A settings row as a number, read now; `default` if unset or unparseable."""
        value = self.db_manager.get_setting(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @property
    def MIN_COIN_THRESHOLDS(self) -> Dict[int, int]:
        """Reserve coins per hopper (0 = no reserve), read on every use so a saved
        setting applies without a restart."""
        return {
            1: max(0, int(self._setting_number('min_coin_threshold_1', 0))),
            5: max(0, int(self._setting_number('min_coin_threshold_5', 0))),
        }

    @property
    def MAX_CHANGE_LIMIT(self) -> float:
        """Most change handed out in one payment, read on every use."""
        return self._setting_number('max_change_limit', 50.0)

    def get_coin_inventory(self) -> Dict[int, int]:
        """Get current coin inventory from database."""
        try:
            inventory = self.db_manager.get_cash_inventory()
            coin_inventory = {}

            for item in inventory:
                if item['type'] == 'coin' and item['denomination'] in self.COIN_DENOMINATIONS:
                    coin_inventory[item['denomination']] = item['count']

            # Ensure all denominations are present
            for denom in self.COIN_DENOMINATIONS:
                if denom not in coin_inventory:
                    coin_inventory[denom] = 0

            return coin_inventory
        except Exception as e:
            print(f"Error getting coin inventory: {e}")
            return {1: 0, 5: 0}

    def get_max_dispensable_change(self) -> float:
        """Most change the hoppers can give right now: coins above the reserve thresholds,
        capped at MAX_CHANGE_LIMIT."""
        coin_inventory = self.get_coin_inventory()
        thresholds = self.MIN_COIN_THRESHOLDS
        th5 = thresholds.get(5, 0)
        th1 = thresholds.get(1, 0)
        max_change_5 = max(0, coin_inventory.get(5, 0) - (th5 if th5 > 0 else 0))
        max_change_1 = max(0, coin_inventory.get(1, 0) - (th1 if th1 > 0 else 0))
        return min((max_change_5 * 5) + max_change_1, self.MAX_CHANGE_LIMIT)

    def get_dispense_limits(self, change_amount: float) -> Dict[int, int]:
        """Coins the hoppers may pay out for this change, as `coin_limits` for the
        dispenser: what each hopper holds above its reserve, and no more than
        MAX_CHANGE_LIMIT pesos in total. Whatever the dispenser can't give within
        these limits is a predicted Shortfall, which becomes a Voucher."""
        inventory = self.get_coin_inventory()
        reserves = self.MIN_COIN_THRESHOLDS
        spare = {d: max(0, inventory.get(d, 0) - reserves.get(d, 0)) for d in (5, 1)}
        budget = min(int(round(change_amount)), max(0, int(self.MAX_CHANGE_LIMIT)))
        fives = min(spare[5], budget // 5)
        ones = min(spare[1], budget - fives * 5)
        return {5: fives, 1: ones}

    def is_change_low(self) -> bool:
        """True when max dispensable change is below 'low_change_warning_threshold'
        (read on every call, so a settings change applies without a restart)."""
        threshold = self.db_manager.get_setting('low_change_warning_threshold', DEFAULT_LOW_CHANGE_THRESHOLD)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = DEFAULT_LOW_CHANGE_THRESHOLD
        return self.get_max_dispensable_change() < threshold

    def calculate_change_breakdown(self, change_amount: float) -> Dict[int, int]:
        """
        Calculate how many coins of each denomination are needed for change.
        Returns dictionary with denomination as key and count as value.
        """
        if change_amount <= 0:
            return {1: 0, 5: 0}

        # Round to nearest peso (assuming no centavos in this system)
        change_amount = round(change_amount)

        # Calculate optimal coin distribution
        coins_5 = int(change_amount // 5)
        coins_1 = int(change_amount % 5)

        return {1: coins_1, 5: coins_5}

    def can_dispense_change(self, change_amount: float) -> Tuple[bool, str, Dict[int, int]]:
        """
        Check if the system can dispense the required change.
        Returns: (can_dispense, reason, required_coins)
        """
        if change_amount <= 0:
            return True, "No change needed", {1: 0, 5: 0}

        # No artificial cap here; feasibility is determined by inventory below

        # Get current coin inventory
        coin_inventory = self.get_coin_inventory()

        # Calculate required coins
        required_coins = self.calculate_change_breakdown(change_amount)

        # Check if we have enough coins
        for denom, required_count in required_coins.items():
            available_count = coin_inventory.get(denom, 0)
            if available_count < required_count:
                return False, f"Insufficient ₱{denom} coins. Required: {required_count}, Available: {available_count}", required_coins

        # Check minimum thresholds (reserve some coins for future transactions)
        # Only enforce when threshold > 0
        for denom, threshold in self.MIN_COIN_THRESHOLDS.items():
            if threshold and threshold > 0:
                remaining_after_change = coin_inventory.get(denom, 0) - required_coins.get(denom, 0)
                if remaining_after_change < threshold:
                    return False, (f"Dispensing change would leave insufficient ₱{denom} coins "
                                   f"(would have {remaining_after_change}, minimum required: {threshold})"), required_coins

        return True, "Change can be dispensed", required_coins

    def find_optimal_payment_amounts(self, total_cost: float) -> List[Dict]:
        """
        Find optimal payment amounts that can be processed with available change.
        Returns list of suggested payment amounts with reasons.
        """
        suggestions = []
        max_change_amount = self.get_max_dispensable_change()

        # If we can't dispense any change, suggest exact payment
        if max_change_amount <= 0:
            suggestions.append({
                'amount': total_cost,
                'change': 0,
                'reason': 'No change available - exact payment required',
                'priority': 'high'
            })
            return suggestions

        # Generate payment suggestions
        # 1. Exact payment (highest priority)
        suggestions.append({
            'amount': total_cost,
            'change': 0,
            'reason': 'Exact payment - no change needed',
            'priority': 'highest'
        })

        # 2. Payment with small change (within our capacity)
        if max_change_amount >= 1:
            # Find amounts that result in change we can dispense
            for change_amount in range(1, min(int(max_change_amount) + 1, 21)):  # Up to ₱20 change
                payment_amount = total_cost + change_amount
                can_dispense, reason, required_coins = self.can_dispense_change(change_amount)

                if can_dispense:
                    suggestions.append({
                        'amount': payment_amount,
                        'change': change_amount,
                        'reason': f'Payment with ₱{change_amount} change',
                        'priority': 'high' if change_amount <= 5 else 'medium',
                        'required_coins': required_coins
                    })

        # 3. Round up to nearest bill denomination
        for bill in self.BILL_DENOMINATIONS:
            if bill > total_cost:
                change_amount = bill - total_cost
                if change_amount <= max_change_amount:
                    can_dispense, reason, required_coins = self.can_dispense_change(change_amount)
                    if can_dispense:
                        suggestions.append({
                            'amount': bill,
                            'change': change_amount,
                            'reason': f'Pay with ₱{bill} bill',
                            'priority': 'medium',
                            'required_coins': required_coins
                        })

        # Sort by priority and amount
        priority_order = {'highest': 0, 'high': 1, 'medium': 2, 'low': 3}
        suggestions.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['amount']))

        return suggestions[:5]  # Return top 5 suggestions

    def validate_payment(self, total_cost: float, payment_amount: float) -> Tuple[bool, str, Dict]:
        """
        Validate if a payment can be processed with available change.
        Returns: (is_valid, message, payment_info)
        """
        if payment_amount < total_cost:
            return False, f"Payment amount ₱{payment_amount:.2f} is less than total cost ₱{total_cost:.2f}", {}

        change_amount = payment_amount - total_cost

        # Check if we can dispense the change
        can_dispense, reason, required_coins = self.can_dispense_change(change_amount)

        if not can_dispense:
            return False, reason, {}

        payment_info = {
            'total_cost': total_cost,
            'payment_amount': payment_amount,
            'change_amount': change_amount,
            'required_coins': required_coins,
            'can_process': True
        }

        return True, f"Payment can be processed. Change: ₱{change_amount:.2f}", payment_info

    def find_best_payment_amount(self, total_cost: float) -> Dict:
        """
        Compute the most the customer can pay in total while the machine can still give
        all the change in coins: the cost plus the greatest change it can dispense,
        given the hopper stock, the reserves and Maximum change. Anything paid beyond
        that comes back as a Voucher instead of coins.

        The customer may pay in any mix of bills and coins, so the figure is not
        rounded to a single bill denomination. With no change possible it is the
        exact cost.
        """
        # We operate in whole pesos. Same figure as the low-change warning: coins above
        # the reserves, capped at Maximum change.
        max_possible_change = int(self.get_max_dispensable_change())

        best_change = 0
        best_required = {1: 0, 5: 0}

        base = int(round(total_cost))
        for change in range(max_possible_change, -1, -1):
            can, reason, req = self.can_dispense_change(change)
            if can:
                best_change, best_required = change, req
                break

        # If no change is possible, return exact
        if best_change == 0:
            return {
                'amount': float(base),
                'change': 0.0,
                'required_coins': {1: 0, 5: 0},
                'reason': 'Exact payment'
            }

        ceiling = base + best_change
        return {
            'amount': float(ceiling),
            'change': float(best_change),
            'required_coins': best_required,
            'reason': f'Max payment we can receive: ₱{ceiling:.2f} (available ₱{best_change:.2f})'
        }

    def get_payment_status_message(self, total_cost: float) -> str:
        """
        Get a status message about payment capabilities.
        """
        max_change_amount = self.get_max_dispensable_change()

        if max_change_amount <= 0:
            return "⚠️ No change available. Exact payment required."
        elif max_change_amount < 10:
            return f"⚠️ Limited change available (₱{max_change_amount:.2f} max). Exact payment recommended."
        else:
            return f"✅ Change available up to ₱{max_change_amount:.2f}"

    def suggest_payment_prompt(self, total_cost: float) -> str:
        """
        Generate a user-friendly payment prompt with suggestions.
        """
        suggestions = self.find_optimal_payment_amounts(total_cost)
        status_message = self.get_payment_status_message(total_cost)

        prompt = f"Total Cost: ₱{total_cost:.2f}\n\n{status_message}\n\n"

        if suggestions:
            prompt += "Suggested payment amounts:\n"
            for i, suggestion in enumerate(suggestions[:3], 1):  # Show top 3
                if suggestion['change'] == 0:
                    prompt += f"{i}. ₱{suggestion['amount']:.2f} (exact payment)\n"
                else:
                    prompt += f"{i}. ₱{suggestion['amount']:.2f} (₱{suggestion['change']:.2f} change)\n"

        return prompt

    def update_coin_inventory_after_dispense(self, dispensed_coins: Dict[int, int]) -> bool:
        """
        Update coin inventory after dispensing change.
        """
        try:
            current_inventory = self.get_coin_inventory()

            for denom, dispensed_count in dispensed_coins.items():
                if dispensed_count > 0:
                    new_count = max(0, current_inventory.get(denom, 0) - dispensed_count)
                    self.db_manager.update_cash_inventory(denom, new_count, 'coin')
                    print(f"Updated ₱{denom} coins: {current_inventory.get(denom, 0)} -> {new_count}")

            return True
        except Exception as e:
            print(f"Error updating coin inventory: {e}")
            return False