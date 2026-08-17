"""Regression tests for liar's dice bid resolution."""
from __future__ import annotations

import unittest

from gamble_games import dice_bid_holds


class DiceBidHoldsTests(unittest.TestCase):
    def test_exact_quantity_holds(self) -> None:
        self.assertTrue(dice_bid_holds(actual=5, quantity=5))

    def test_more_than_quantity_holds(self) -> None:
        self.assertTrue(dice_bid_holds(actual=7, quantity=5))

    def test_fewer_than_quantity_fails(self) -> None:
        self.assertFalse(dice_bid_holds(actual=4, quantity=5))


if __name__ == "__main__":
    unittest.main()
