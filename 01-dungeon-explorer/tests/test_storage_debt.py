"""Regression test for persistent shared-wallet debt."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from game.storage import PlayerStore


class PlayerStoreDebtTests(unittest.TestCase):
    def test_negative_gold_survives_save_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PlayerStore(Path(directory) / "dungeon.db")
            player = store.get(1001, "负债测试")
            player.gold = -125
            store.save(player)
            self.assertEqual(store.get(1001, "负债测试").gold, -125)


if __name__ == "__main__":
    unittest.main()
