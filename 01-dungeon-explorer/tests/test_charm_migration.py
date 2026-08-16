import unittest

from game.models import Player
from migrate_all_player_charms import EGO_USER_ID, migrate_state


class CharmSourceMigrationTests(unittest.TestCase):
    def test_positive_historical_value_always_has_at_least_one_count(self):
        current = Player(
            6,
            "历史小数值",
            crystal_attack_bonus=0.2,
            crystal_charm_draw_count=0,
            crystal_charm_stat_counts={"attack": 0},
            charm_source_rules_version=4,
        ).to_dict()
        current.pop("crystal_charm_archive_version")

        player = Player.from_dict(current)

        self.assertEqual(player.crystal_charm_stat_counts["attack"], 1)
        self.assertEqual(player.crystal_charm_draw_count, 1)

    def test_version_three_infers_historical_counts_from_current_values(self):
        current = Player(
            7,
            "恢复次数",
            crystal_attack_bonus=32,
            crystal_defense_bonus=8,
            charm_source_rules_version=3,
        ).to_dict()
        migrated, result = migrate_state(7, current, None)

        self.assertEqual(result["status"], "updated")
        self.assertEqual(migrated["crystal_charm_draw_count"], 8)
        self.assertEqual(
            migrated["crystal_charm_stat_counts"],
            {"attack": 8, "defense": 2, "agility": 0, "luck": 0},
        )
        self.assertEqual(migrated["crystal_attack_bonus"], 32)
        self.assertEqual(migrated["charm_source_rules_version"], 4)

    def test_version_one_crystal_counts_are_restored_without_decay(self):
        current = Player(
            8,
            "水晶取消衰减",
            crystal_attack_bonus=96,
            charm_source_rules_version=1,
        ).to_dict()
        current["crystal_charm_counts"] = {"attack": 25}

        migrated, result = migrate_state(8, current, None)

        self.assertEqual(result["status"], "updated")
        self.assertEqual(migrated["crystal_attack_bonus"], 100)
        self.assertEqual(migrated["charm_source_rules_version"], 4)
        self.assertNotIn("crystal_charm_counts", migrated)
        self.assertEqual(migrated["crystal_charm_draw_count"], 25)
        self.assertEqual(migrated["crystal_charm_stat_counts"]["attack"], 25)

    def test_player_without_unexplained_old_stats_gets_no_crystal_bundle(self):
        legacy = Player(
            9,
            "无历史水晶",
            completion_count=1,
            permanent_attack_bonus=5,
            permanent_defense_bonus=3,
        ).to_dict()
        current = Player(
            9,
            "无历史水晶",
            completion_count=2,
            permanent_attack_bonus=10,
            permanent_defense_bonus=6,
        ).to_dict()
        current.pop("charm_source_rules_version")

        migrated, _ = migrate_state(9, current, legacy)
        player = Player.from_dict(migrated)

        self.assertEqual(player.crystal_attack_bonus, 0)
        self.assertEqual(player.crystal_defense_bonus, 0)
        self.assertEqual(player.crystal_agility_bonus, 0)
        self.assertEqual(player.crystal_luck_bonus, 0)
        self.assertEqual(player.crystal_charm_draw_count, 0)

    def test_migration_separates_blessing_crystal_and_merchant_values(self):
        legacy = Player(
            10,
            "历史玩家",
            completion_count=1,
            permanent_attack_bonus=25,
            permanent_defense_bonus=13,
        ).to_dict()
        current = Player(
            10,
            "历史玩家",
            completion_count=2,
            permanent_attack_bonus=38,
            permanent_defense_bonus=24,
            permanent_agility_bonus=3,
            permanent_luck_bonus=2,
            merchant_charm_base_stats={"attack": 25, "defense": 7},
        ).to_dict()
        current.pop("charm_source_rules_version")

        migrated, result = migrate_state(10, current, legacy)
        player = Player.from_dict(migrated)

        self.assertEqual(result["status"], "updated")
        self.assertEqual(player.permanent_attack_bonus, 10)
        self.assertEqual(player.permanent_defense_bonus, 6)
        self.assertEqual(player.crystal_attack_bonus, 8)
        self.assertEqual(player.crystal_defense_bonus, 8)
        self.assertEqual(player.crystal_agility_bonus, 3)
        self.assertEqual(player.crystal_luck_bonus, 2)
        self.assertEqual(player.crystal_charm_draw_count, 2)
        self.assertEqual(
            player.crystal_charm_stat_counts,
            {"attack": 2, "defense": 2, "agility": 1, "luck": 1},
        )
        self.assertEqual(player.merchant_charm_base_stats["attack"], 25)
        self.assertEqual(player.merchant_attack_bonus, 24)

    def test_ego_uses_the_same_inference_rule_as_everyone(self):
        current = Player(
            EGO_USER_ID,
            "ego",
            completion_count=3,
            weapon_attack=34,
            clothing_defense=17,
            weapon_agility=5,
            clothing_agility=4,
            weapon_luck=6,
            clothing_luck=4,
            permanent_attack_bonus=15,
            permanent_defense_bonus=9,
            crystal_attack_bonus=4,
            crystal_defense_bonus=4,
            crystal_agility_bonus=4,
            crystal_luck_bonus=4,
            merchant_charm_base_stats={
                "attack": 113,
                "defense": 94,
                "agility": 111,
                "luck": 113,
            },
            charm_source_rules_version=3,
        ).to_dict()

        migrated, _ = migrate_state(EGO_USER_ID, current, None)
        player = Player.from_dict(migrated)

        self.assertEqual(player.permanent_attack_bonus, 15)
        self.assertEqual(player.permanent_defense_bonus, 9)
        self.assertEqual(player.crystal_attack_bonus, 4)
        self.assertEqual(player.crystal_defense_bonus, 4)
        self.assertEqual(player.crystal_agility_bonus, 4)
        self.assertEqual(player.crystal_luck_bonus, 4)
        self.assertEqual(player.crystal_charm_draw_count, 1)
        self.assertEqual(
            player.crystal_charm_stat_counts,
            {"attack": 1, "defense": 1, "agility": 1, "luck": 1},
        )
        self.assertEqual(player.attack_bonus, 110.3)
        self.assertEqual(player.defense, 84.8)
        self.assertEqual(player.agility, 70.1)
        self.assertEqual(player.luck, 71.3)


if __name__ == "__main__":
    unittest.main()
