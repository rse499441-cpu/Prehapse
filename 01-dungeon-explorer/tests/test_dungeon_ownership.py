import tempfile
import unittest
from pathlib import Path

from game.crystal import (
    CRYSTAL_REWARDS as DUNGEON_ONE_CRYSTAL_REWARDS,
    CRYSTAL_POOL_NAME as DUNGEON_ONE_POOL,
    EQUIPMENT_ORIGIN as DUNGEON_ONE_ORIGIN,
)
from game.equipment import migrate_equipment_names as migrate_dungeon_one_equipment
from game.models import Player as DungeonOnePlayer
from game.shop import ARMORS as DUNGEON_ONE_ARMORS
from game.shop import WEAPONS as DUNGEON_ONE_WEAPONS
from game.shop import daily_stock as dungeon_one_daily_stock
from game.storage import PlayerStore as DungeonOneStore
from school_dungeon.game.crystal import (
    CRYSTAL_REWARDS as DUNGEON_TWO_CRYSTAL_REWARDS,
    CRYSTAL_POOL_NAME as DUNGEON_TWO_POOL,
    EQUIPMENT_ORIGIN as DUNGEON_TWO_ORIGIN,
    migrate_crystal_reward_names,
)
from school_dungeon.game.models import Player as DungeonTwoPlayer
from school_dungeon.game.equipment import (
    migrate_equipment_names as migrate_dungeon_two_equipment,
)
from school_dungeon.game.engine import GameEngine as DungeonTwoEngine
from school_dungeon.game.shop import ARMORS as DUNGEON_TWO_ARMORS
from school_dungeon.game.shop import WEAPONS as DUNGEON_TWO_WEAPONS
from school_dungeon.game.shop import daily_stock as dungeon_two_daily_stock
from school_dungeon.game.storage import PlayerStore as DungeonTwoStore


class DungeonOwnershipTests(unittest.TestCase):
    def test_only_gold_and_crystals_are_shared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dungeon_one_path = Path(temp_dir) / "dungeon-one.db"
            dungeon_two_path = Path(temp_dir) / "dungeon-two.db"
            dungeon_one_store = DungeonOneStore(dungeon_one_path)

            dungeon_one = dungeon_one_store.get(1, "测试者")
            dungeon_one.gold = 500
            dungeon_one.crystals = 9
            dungeon_one.weapon = "地下城一测试剑"
            dungeon_one.weapon_attack = 99
            dungeon_one.equipment_inventory = {
                "地下城一测试剑": {
                    "name": "地下城一测试剑",
                    "category": "武器",
                    "rarity": "传说",
                    "attack": 99,
                    "defense": 0,
                    "agility": 0,
                    "luck": 0,
                }
            }
            dungeon_one.crystal_equipment = {"d1_reward": 1}
            dungeon_one_store.save(dungeon_one)

            dungeon_two_store = DungeonTwoStore(
                dungeon_two_path,
                shared_path=dungeon_one_path,
            )
            dungeon_two = dungeon_two_store.get(1, "测试者")
            self.assertEqual((dungeon_two.gold, dungeon_two.crystals), (500, 9))
            self.assertNotEqual(dungeon_two.weapon, "地下城一测试剑")
            self.assertNotIn("地下城一测试剑", dungeon_two.equipment_inventory)
            self.assertNotIn("d1_reward", dungeon_two.crystal_equipment)

            dungeon_two.weapon = "地下城二测试尺"
            dungeon_two.weapon_attack = 77
            dungeon_two.equipment_inventory = {
                "地下城二测试尺": {
                    "name": "地下城二测试尺",
                    "category": "武器",
                    "rarity": "黄金",
                    "attack": 77,
                    "defense": 0,
                    "agility": 0,
                    "luck": 0,
                }
            }
            dungeon_two.crystal_equipment = {"d2_reward": 1}
            dungeon_two.gold += 25
            dungeon_two.crystals -= 3
            dungeon_two_store.save(dungeon_two)

            reloaded_one = dungeon_one_store.get(1, "测试者")
            reloaded_two = dungeon_two_store.get(1, "测试者")
            self.assertEqual((reloaded_one.gold, reloaded_one.crystals), (525, 6))
            self.assertEqual((reloaded_two.gold, reloaded_two.crystals), (525, 6))
            self.assertEqual(reloaded_one.weapon, "地下城一测试剑")
            self.assertIn("地下城一测试剑", reloaded_one.equipment_inventory)
            self.assertNotIn("地下城二测试尺", reloaded_one.equipment_inventory)
            self.assertEqual(reloaded_one.crystal_equipment, {"d1_reward": 1})
            self.assertEqual(reloaded_two.weapon, "地下城二测试尺")
            self.assertIn("地下城二测试尺", reloaded_two.equipment_inventory)
            self.assertNotIn("地下城一测试剑", reloaded_two.equipment_inventory)
            self.assertEqual(reloaded_two.crystal_equipment, {"d2_reward": 1})

    def test_crystal_pool_names_and_origins_are_distinct(self):
        self.assertEqual(DUNGEON_ONE_POOL, "女巫的水晶秘藏")
        self.assertEqual(DUNGEON_TWO_POOL, "神秘研究社库藏")
        self.assertEqual(DUNGEON_ONE_ORIGIN, "地下城一")
        self.assertEqual(DUNGEON_TWO_ORIGIN, "地下城二")

    def test_gold_shop_equipment_pools_and_daily_stock_are_independent(self):
        dungeon_one_names = {
            item.name for item in DUNGEON_ONE_WEAPONS + DUNGEON_ONE_ARMORS
        }
        dungeon_two_names = {
            item.name for item in DUNGEON_TWO_WEAPONS + DUNGEON_TWO_ARMORS
        }
        self.assertTrue(dungeon_one_names.isdisjoint(dungeon_two_names))

        date_key = "2026-08-31"
        dungeon_one_stock = [item.name for item in dungeon_one_daily_stock(date_key)]
        dungeon_two_stock = [item.name for item in dungeon_two_daily_stock(date_key)]
        self.assertNotEqual(dungeon_one_stock, dungeon_two_stock)
        dungeon_one_daily_equipment = {
            item.name for item in dungeon_one_daily_stock(date_key)
            if item.category in {"武器", "护具"}
        }
        dungeon_two_daily_equipment = {
            item.name for item in dungeon_two_daily_stock(date_key)
            if item.category in {"武器", "护具"}
        }
        self.assertTrue(dungeon_one_daily_equipment.isdisjoint(dungeon_two_daily_equipment))

    def test_dungeon_one_school_names_are_restored_to_fantasy_names(self):
        player = DungeonOnePlayer(3, "测试者")
        player.weapon = "铁制直尺"
        player.weapon_attack = 7
        player.equipment_inventory = {
            "铁制直尺": {
                "name": "铁制直尺", "category": "武器", "rarity": "普通",
                "attack": 7, "defense": 0, "agility": 0, "luck": 0,
            }
        }
        player.equipment_name_rules_version = 1

        migrate_dungeon_one_equipment(player)

        self.assertEqual(player.weapon, "铁制短剑")
        self.assertIn("铁制短剑", player.equipment_inventory)
        self.assertNotIn("铁制直尺", player.equipment_inventory)

    def test_dungeon_two_starter_equipment_is_school_themed_and_migrated(self):
        new_player = DungeonTwoPlayer(5, "新生")
        self.assertEqual(new_player.weapon, "木制直尺")
        self.assertEqual(new_player.clothing, "普通校服")

        old_player = DungeonTwoPlayer(6, "老玩家")
        old_player.weapon = "新手短剑"
        old_player.clothing = "布衣"
        old_player.equipment_inventory = {
            "新手短剑": {
                "name": "新手短剑", "category": "武器", "rarity": "普通",
                "attack": 4, "defense": 0, "agility": 0, "luck": 0,
            },
            "布衣": {
                "name": "布衣", "category": "护具", "rarity": "普通",
                "attack": 0, "defense": 1, "agility": 0, "luck": 0,
            },
        }
        old_player.equipment_name_rules_version = 1

        migrate_dungeon_two_equipment(old_player)

        self.assertEqual(old_player.weapon, "木制直尺")
        self.assertEqual(old_player.clothing, "普通校服")
        self.assertIn("木制直尺", old_player.equipment_inventory)
        self.assertIn("普通校服", old_player.equipment_inventory)
        self.assertNotIn("新手短剑", old_player.equipment_inventory)
        self.assertNotIn("布衣", old_player.equipment_inventory)

    def test_dungeon_two_student_adventurer_skills_use_school_names(self):
        self.assertEqual(
            [skill[0] for skill in DungeonTwoEngine.MAGIC_SKILLS.values()],
            ["✨ 学识火花", "🔷 灵感光矢", "🌠 真理星雨"],
        )

    def test_dungeon_two_crystal_pool_names_and_legacy_items_are_migrated(self):
        dungeon_one_names = {item.name for item in DUNGEON_ONE_CRYSTAL_REWARDS}
        dungeon_two_names = {item.name for item in DUNGEON_TWO_CRYSTAL_REWARDS}
        self.assertTrue(dungeon_one_names.isdisjoint(dungeon_two_names))
        legendary = {
            item.key: item.name
            for item in DUNGEON_TWO_CRYSTAL_REWARDS
            if item.rarity == "传说"
        }
        self.assertEqual(legendary, {
            "legend_blade": "光荣榜榜首·相片",
            "legend_robe": "光荣榜授勋礼装",
            "legend_charm": "光荣榜榜首·徽章",
            "legend_staff": "光荣榜榜首·宣言",
        })

        player = DungeonTwoPlayer(4, "测试者")
        player.weapon = "永夜星穹"
        player.weapon_attack = 36
        player.equipment_inventory = {
            "永夜星穹": {
                "name": "永夜星穹", "category": "武器", "rarity": "传说",
                "attack": 36, "defense": 0, "agility": 6, "luck": 6,
            }
        }
        player.crystal_equipment = {"legend_blade": 1}
        player.crystal_pool_name_rules_version = 0

        migrate_crystal_reward_names(player)

        self.assertEqual(player.weapon, "光荣榜榜首·相片")
        self.assertIn("光荣榜榜首·相片", player.equipment_inventory)
        self.assertNotIn("永夜星穹", player.equipment_inventory)
        self.assertEqual(player.crystal_equipment, {"legend_blade": 1})


if __name__ == "__main__":
    unittest.main()
