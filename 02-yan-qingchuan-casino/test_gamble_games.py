"""Regression tests for casino streak and debt settlement."""
from __future__ import annotations

import unittest

from gamble_games import (
    apply_loss_collection,
    dice_bid_holds,
    loss_penalty,
    scaled_win_profit,
    streak_bonus_rate,
)


class DiceBidHoldsTests(unittest.TestCase):
    def test_exact_quantity_holds(self) -> None:
        self.assertTrue(dice_bid_holds(actual=5, quantity=5))

    def test_more_than_quantity_holds(self) -> None:
        self.assertTrue(dice_bid_holds(actual=7, quantity=5))

    def test_fewer_than_quantity_fails(self) -> None:
        self.assertFalse(dice_bid_holds(actual=4, quantity=5))


class StreakSettlementTests(unittest.TestCase):
    def test_bonus_tiers(self) -> None:
        self.assertEqual(streak_bonus_rate(2), 0)
        self.assertEqual(streak_bonus_rate(3), 30)
        self.assertEqual(streak_bonus_rate(5), 80)
        self.assertEqual(streak_bonus_rate(7), 100)

    def test_no_streak_halves_original_profit(self) -> None:
        self.assertEqual(scaled_win_profit(1000, 1000, 0), 500)
        self.assertEqual(scaled_win_profit(1000, 1000, 2), 500)

    def test_streak_bonus_is_added_to_full_profit(self) -> None:
        self.assertEqual(scaled_win_profit(1000, 1000, 3), 1300)
        self.assertEqual(scaled_win_profit(1000, 1000, 5), 1800)
        self.assertEqual(scaled_win_profit(1000, 1000, 7), 2000)

    def test_streak_tier_preserves_original_game_odds(self) -> None:
        self.assertEqual(scaled_win_profit(1000, 2000, 3), 2300)

    def test_loss_penalty_uses_streak_tier(self) -> None:
        self.assertEqual(loss_penalty(1000, 2), 0)
        self.assertEqual(loss_penalty(1000, 3), 300)
        self.assertEqual(loss_penalty(1000, 5), 800)
        self.assertEqual(loss_penalty(1000, 7), 1000)

    def test_loss_uses_wallet_then_savings_then_debt(self) -> None:
        self.assertEqual(
            apply_loss_collection(gold=200, stored_gold=500, amount=800),
            (-100, 0, 200, 500, 100),
        )

    def test_savings_can_clear_remaining_loss(self) -> None:
        self.assertEqual(
            apply_loss_collection(gold=200, stored_gold=500, amount=300),
            (0, 400, 200, 100, 0),
        )


if __name__ == "__main__":
    unittest.main()

