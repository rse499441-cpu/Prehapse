import random
import unittest

from game.crystal import CRYSTAL_EXCHANGE_COST, crystal_charm_values_text, equip_crystal_reward, exchange_crystals
from game.models import Player


class CrystalExchangeTests(unittest.TestCase):
    def test_exchange_costs_three_crystals_and_never_returns_below_s(self):
        player = Player(1, "测试者", crystals=CRYSTAL_EXCHANGE_COST)

        ok, _, rewards = exchange_crystals(player, random.Random(1))

        self.assertTrue(ok)
        self.assertEqual(player.crystals, 0)
        self.assertIn(rewards[0].rarity, {"优良", "稀有", "黄金", "传说"})

    def test_exchange_is_blocked_without_enough_crystals(self):
        player = Player(1, "测试者", crystals=2)

        ok, _, rewards = exchange_crystals(player, random.Random(1))

        self.assertFalse(ok)
        self.assertEqual(rewards, [])
        self.assertEqual(player.crystals, 2)

    def test_exchange_is_available_during_adventure_without_resetting_progress(self):
        player = Player(1, "测试者", crystals=9, in_adventure=True)
        player.floor, player.steps = 37, 8

        ok, _, rewards = exchange_crystals(player, random.Random(1))

        self.assertTrue(ok)
        self.assertEqual(player.crystals, 6)
        self.assertEqual(len(rewards), 1)
        self.assertEqual((player.floor, player.steps), (37, 8))
        self.assertTrue(player.in_adventure)

    def test_charm_reward_adds_permanent_stats(self):
        class FixedRng:
            def choices(self, *_args, **_kwargs):
                return ["传说"]

            def choice(self, items):
                return next(item for item in items if item.category == "护符")

        player = Player(1, "测试者", crystals=3)
        ok, _, rewards = exchange_crystals(player, FixedRng())

        self.assertTrue(ok)
        self.assertEqual(rewards[0].category, "护符")
        self.assertEqual(player.permanent_attack_bonus, 0)
        self.assertEqual(player.crystal_attack_bonus, 4)
        self.assertEqual(player.crystal_defense_bonus, 4)
        self.assertEqual(player.crystal_luck_bonus, 4)
        self.assertEqual(player.crystal_charm_draw_count, 1)
        self.assertEqual(
            player.crystal_charm_stat_counts,
            {"attack": 1, "defense": 1, "luck": 1},
        )
        self.assertIn("攻击 +4", crystal_charm_values_text(player))

        player.crystals = 3
        exchange_crystals(player, FixedRng())
        self.assertEqual(player.crystal_attack_bonus, 8)
        self.assertEqual(player.crystal_charm_draw_count, 2)

    def test_crystal_charms_do_not_decay(self):
        class FixedRng:
            def choices(self, *_args, **_kwargs):
                return ["传说"]

            def choice(self, items):
                return next(item for item in items if item.category == "护符")

        player = Player(
            1,
            "水晶不衰减",
            crystals=3,
            crystal_attack_bonus=80,
            crystal_defense_bonus=80,
            crystal_luck_bonus=80,
        )

        exchange_crystals(player, FixedRng())

        self.assertEqual(player.crystal_attack_bonus, 84)
        self.assertEqual(player.crystal_defense_bonus, 84)
        self.assertEqual(player.crystal_luck_bonus, 84)
        self.assertEqual(player.crystal_charm_draw_count, 1)

    def test_ten_exchange_costs_thirty_crystals_and_returns_ten_rewards(self):
        player = Player(1, "测试者", crystals=30)

        ok, result, rewards = exchange_crystals(player, random.Random(3), count=10)

        self.assertTrue(ok)
        self.assertEqual(player.crystals, 0)
        self.assertEqual(len(rewards), 10)
        self.assertIn("完成 **10 次**兑换", result)

    def test_multi_exchange_is_all_or_nothing_when_crystals_are_insufficient(self):
        player = Player(1, "测试者", crystals=14)

        ok, _, rewards = exchange_crystals(player, random.Random(3), count=5)

        self.assertFalse(ok)
        self.assertEqual(player.crystals, 14)
        self.assertEqual(rewards, [])

    def test_large_reward_pool_has_requested_rarity_counts(self):
        from game.crystal import CRYSTAL_REWARDS

        counts = {
            rarity: sum(item.rarity == rarity for item in CRYSTAL_REWARDS)
            for rarity in ("优良", "稀有", "黄金", "传说")
        }
        self.assertEqual(counts, {"优良": 60, "稀有": 47, "黄金": 23, "传说": 4})
        self.assertFalse(any(item.rarity == "普通" for item in CRYSTAL_REWARDS))
        self.assertEqual(len({item.name for item in CRYSTAL_REWARDS}), 134)
        for rarity in ("优良", "稀有", "黄金", "传说"):
            self.assertTrue(any(
                item.rarity == rarity and item.category == "护符" and item.attack > 0
                for item in CRYSTAL_REWARDS
            ))

    def test_crystal_equipment_is_stored_then_can_be_equipped(self):
        class FixedRng:
            def choices(self, *_args, **_kwargs):
                return ["黄金"]

            def choice(self, items):
                return next(item for item in items if item.category == "武器")

        player = Player(1, "测试者", crystals=3)
        _, _, rewards = exchange_crystals(player, FixedRng())
        reward = rewards[0]

        self.assertEqual(player.crystal_equipment[reward.key], 1)
        self.assertNotEqual(player.weapon, reward.name)

        ok, _ = equip_crystal_reward(player, reward.key)

        self.assertTrue(ok)
        self.assertEqual(player.weapon, reward.name)
        self.assertEqual(player.weapon_attack, reward.attack)


if __name__ == "__main__":
    unittest.main()
