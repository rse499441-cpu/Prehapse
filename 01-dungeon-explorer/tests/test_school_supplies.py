import unittest

from school_dungeon.game.engine import GameEngine
from school_dungeon.game.models import Player
from school_dungeon.game.shop import CONSUMABLES


class SchoolSupplyTests(unittest.TestCase):
    def test_old_dungeon_two_supplies_are_migrated_and_merged(self):
        player = Player.from_dict({
            "user_id": 1,
            "name": "测试者",
            "consumables": {
                "治疗药水": 2,
                "学生牛奶": 1,
                "强效治疗药水": 3,
                "魔力药水": 4,
                "强效魔力药水": 5,
                "精力药水": 6,
                "强效精力药水": 7,
                "幸运护符": 8,
            },
            "school_supply_name_rules_version": 0,
        })

        self.assertEqual(player.consumables["学生牛奶"], 3)
        self.assertEqual(player.consumables["校园营养餐"], 3)
        self.assertEqual(player.consumables["清凉油"], 4)
        self.assertEqual(player.consumables["强劲薄荷糖"], 5)
        self.assertEqual(player.consumables["运动饮料"], 6)
        self.assertEqual(player.consumables["安神补脑液"], 7)
        self.assertEqual(player.consumables["幸运护符"], 8)
        self.assertNotIn("治疗药水", player.consumables)

    def test_merchant_stock_ids_and_counts_are_preserved(self):
        stock = {
            "healing_potion": 2,
            "greater_mana_potion": 4,
            "guard_charm": 1,
        }
        player = Player.from_dict({
            "user_id": 2,
            "name": "测试者",
            "merchant_stock": stock,
        })

        self.assertEqual(player.merchant_stock, stock)
        self.assertEqual(GameEngine.MERCHANT_ITEMS["healing_potion"][0], "学生牛奶")
        self.assertEqual(GameEngine.MERCHANT_ITEMS["greater_mana_potion"][0], "强劲薄荷糖")

    def test_school_shop_uses_new_names(self):
        names = {item.name for item in CONSUMABLES}
        self.assertTrue({
            "学生牛奶", "校园营养餐", "清凉油",
            "强劲薄荷糖", "运动饮料", "安神补脑液",
        }.issubset(names))
        self.assertTrue({"治疗药水", "魔力药水", "精力药水"}.isdisjoint(names))

    def test_new_supply_actions_consume_only_dungeon_two_names(self):
        engine = GameEngine()
        player = Player(3, "测试者", hp=20, mp=0, energy=20)
        player.consumables = {"学生牛奶": 1, "清凉油": 1, "运动饮料": 1}

        heal = engine.use_potion(player)
        mana = engine.use_mana_potion(player)
        energy = engine.use_energy_potion(player)

        self.assertEqual(heal.title, "🥛 饮用学生牛奶")
        self.assertEqual(mana.title, "🧴 使用清凉油")
        self.assertEqual(energy.title, "🥤 饮用运动饮料")
        self.assertEqual(player.consumables, {"学生牛奶": 0, "清凉油": 0, "运动饮料": 0})


if __name__ == "__main__":
    unittest.main()
