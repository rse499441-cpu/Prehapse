import unittest

from game.equipment import (
    ensure_equipment_inventory,
    equip_from_inventory,
    register_equipment,
)
from game.models import Player


class EquipmentInventoryTests(unittest.TestCase):
    def test_same_name_is_deduplicated(self):
        player = Player(1, "收藏家")

        register_equipment(player, "月光剑", "武器", rarity="稀有", attack=20)
        register_equipment(player, "月光剑", "武器", rarity="稀有", attack=20)

        self.assertEqual(list(player.equipment_inventory), ["月光剑"])

    def test_player_can_choose_collected_equipment(self):
        player = Player(1, "收藏家")
        register_equipment(
            player, "月光剑", "武器", rarity="稀有",
            attack=20, agility=3, luck=2,
        )

        ok, _ = equip_from_inventory(player, "月光剑")

        self.assertTrue(ok)
        self.assertEqual(player.weapon, "月光剑")
        self.assertEqual((player.weapon_attack, player.weapon_agility, player.weapon_luck), (20, 3, 2))

    def test_inventory_migration_does_not_overwrite_rarity(self):
        player = Player(1, "收藏家", weapon="月光剑", weapon_attack=20)
        register_equipment(player, "月光剑", "武器", rarity="传说", attack=20)

        ensure_equipment_inventory(player)

        self.assertEqual(player.equipment_inventory["月光剑"]["rarity"], "传说")


if __name__ == "__main__":
    unittest.main()
