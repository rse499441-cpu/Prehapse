import unittest

from game.models import Enemy, Player
import random

from game.shop import ARMORS, CONSUMABLES, WEAPONS, boss_equipment_drop, daily_stock, purchase


class GoldShopTests(unittest.TestCase):
    def test_stock_is_stable_for_the_same_day(self):
        self.assertEqual(daily_stock("2026-07-23"), daily_stock("2026-07-23"))
        self.assertEqual(len(daily_stock("2026-07-23")), 12)

    def test_consecutive_days_have_different_stock(self):
        self.assertNotEqual(daily_stock("2026-07-23"), daily_stock("2026-07-24"))

    def test_stock_contains_equipment_and_consumables(self):
        categories = {item.category for item in daily_stock("2026-07-23")}
        self.assertEqual(categories, {"武器", "护具", "道具"})

    def test_weapon_purchase_equips_and_updates_stats(self):
        player = Player(1, "测试勇者", gold=10_000)
        item = WEAPONS[-1]

        ok, _ = purchase(player, item)

        self.assertTrue(ok)
        self.assertEqual(player.weapon, item.name)
        self.assertEqual(player.weapon_attack, item.attack)
        self.assertEqual(player.agility, item.agility)
        self.assertEqual(player.luck, item.luck)
        self.assertEqual(player.gold, 10_000 - item.price)

    def test_armor_purchase_equips_and_updates_stats(self):
        player = Player(1, "测试勇者", gold=10_000)
        item = ARMORS[-1]

        ok, _ = purchase(player, item)

        self.assertTrue(ok)
        self.assertEqual(player.clothing, item.name)
        self.assertEqual(player.defense, item.defense)

    def test_consumables_can_be_bought_more_than_once(self):
        player = Player(1, "测试勇者", gold=10_000)
        item = CONSUMABLES[1]

        purchase(player, item)
        purchase(player, item)

        self.assertEqual(player.consumables[item.name], 2)
        self.assertEqual(player.gold, 10_000 - item.price * 2)

    def test_shop_is_blocked_during_an_adventure(self):
        states = [
            Player(1, "勇者", gold=10_000, in_adventure=True),
            Player(2, "旧存档勇者", gold=10_000, floor=2),
            Player(3, "战斗勇者", gold=10_000, enemy=Enemy("史莱姆", 10, 10, 1, 1)),
        ]
        for player in states:
            with self.subTest(player=player.name):
                before = player.gold
                ok, _ = purchase(player, CONSUMABLES[0])
                self.assertFalse(ok)
                self.assertEqual(player.gold, before)

    def test_shop_is_available_at_the_tavern(self):
        player = Player(1, "归来的勇者", gold=10_000)
        ok, _ = purchase(player, CONSUMABLES[0])
        self.assertTrue(ok)

    def test_boss_drop_rarity_is_limited_by_floor(self):
        low = {boss_equipment_drop(10, random.Random(seed)).rarity for seed in range(30)}
        deep = {boss_equipment_drop(100, random.Random(seed)).rarity for seed in range(30)}

        self.assertTrue(low <= {"普通", "优良"})
        self.assertTrue(deep <= {"稀有", "黄金", "传说"})

    def test_deep_boss_legendary_is_about_three_percent_after_drop(self):
        rng = random.Random(77)
        rewards = [boss_equipment_drop(100, rng) for _ in range(10_000)]
        legendary_rate = sum(item.rarity == "传说" for item in rewards) / len(rewards)

        self.assertGreater(legendary_rate, 0.02)
        self.assertLess(legendary_rate, 0.04)


if __name__ == "__main__":
    unittest.main()
