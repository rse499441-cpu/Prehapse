import tempfile
import unittest
import json
from contextlib import closing
from datetime import date
from pathlib import Path

from game.storage import PlayerStore
from game.models import Player, merchant_charm_total


class WeeklyChallengeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PlayerStore(Path(self.temp_dir.name) / "dungeon.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_week_key_starts_on_monday(self):
        self.assertEqual(self.store.week_key(date(2026, 7, 23)), "2026-07-20")
        self.assertEqual(self.store.week_key(date(2026, 7, 25)), "2026-07-20")
        self.assertEqual(self.store.week_key(date(2026, 7, 27)), "2026-07-27")

    def test_merchant_charm_total_matches_documented_six_tiers(self):
        expected = {0: 0, 20: 20, 40: 36, 60: 46, 80: 52, 100: 56, 110: 57}
        for count, total in expected.items():
            with self.subTest(count=count):
                self.assertAlmostEqual(merchant_charm_total(count), total)

    def test_charm_counts_override_stale_cached_values_everywhere(self):
        state = Player(
            93,
            "护符统一口径",
            weapon_attack=4,
            clothing_defense=1,
            merchant_charm_base_stats={
                "attack": 25,
                "defense": 7,
                "agility": 41,
                "luck": 105,
            },
            merchant_attack_bonus=999,
            merchant_defense_bonus=999,
            merchant_agility_bonus=999,
            merchant_luck_bonus=999,
            merchant_charm_rules_version=6,
        ).to_dict()

        player = Player.from_dict(state)

        self.assertEqual(player.merchant_attack_bonus, 24)
        self.assertEqual(player.merchant_defense_bonus, 7)
        self.assertEqual(player.merchant_agility_bonus, 36.5)
        self.assertEqual(player.merchant_luck_bonus, 56.5)
        self.assertEqual(player.attack_bonus, 28)
        self.assertEqual(player.defense, 8)
        self.assertEqual(player.agility, 36.5)
        self.assertEqual(player.luck, 56.5)

    def test_hundred_floor_growth_is_not_counted_as_a_charm(self):
        player = Player(
            94,
            "分项口径",
            completion_count=2,
            permanent_attack_bonus=10,
            crystal_attack_bonus=6,
            merchant_charm_base_stats={"attack": 25},
        )

        self.assertEqual(player.completion_bonus("attack"), 10)
        self.assertEqual(player.crystal_charm_bonus("attack"), 6)
        self.assertEqual(player.merchant_charm_bonus("attack"), 24)
        self.assertEqual(player.total_charm_bonus("attack"), 30)
        self.assertEqual(
            player.weapon_attack
            + player.completion_bonus("attack")
            + player.total_charm_bonus("attack"),
            player.attack_bonus,
        )

    def test_weekly_score_only_keeps_each_players_highest_floor(self):
        moment = date(2026, 7, 23)
        self.store.record_weekly_challenge(1, "小秦", 8, moment)
        self.store.record_weekly_challenge(1, "小秦", 4, moment)
        self.store.record_weekly_challenge(1, "小秦", 15, moment)

        self.assertEqual(self.store.weekly_top(moment=moment), [(1, "小秦", 15)])

    def test_weekly_top_orders_and_limits_to_fifteen(self):
        moment = date(2026, 7, 23)
        for user_id in range(1, 21):
            self.store.record_weekly_challenge(
                user_id,
                f"冒险者{user_id}",
                user_id,
                moment,
            )

        rows = self.store.weekly_top(15, moment)

        self.assertEqual(len(rows), 15)
        self.assertEqual(rows[0], (20, "冒险者20", 20))
        self.assertEqual(rows[-1], (6, "冒险者6", 6))

    def test_clear_weekly_challenge_only_removes_selected_player(self):
        moment = date(2026, 7, 23)
        self.store.record_weekly_challenge(1, "要清零", 100, moment)
        self.store.record_weekly_challenge(2, "保留者", 20, moment)

        self.store.clear_weekly_challenge(1, moment)

        self.assertEqual(self.store.weekly_top(moment=moment), [(2, "保留者", 20)])

    def test_shared_wallet_preserves_external_rewards_during_save(self):
        player = self.store.get(88, "并发测试")
        player.gold = 100
        player.crystals = 5
        self.store.save(player)

        loaded = self.store.get(88, "并发测试")
        with closing(self.store._connect()) as conn:
            conn.execute(
                "UPDATE shared_wallets SET gold=gold+7, crystals=crystals+2 "
                "WHERE user_id=?",
                (88,),
            )
            conn.commit()

        loaded.gold -= 20
        loaded.crystals -= 1
        self.store.save(loaded)

        refreshed = self.store.get(88, "并发测试")
        self.assertEqual((refreshed.gold, refreshed.crystals), (87, 6))

    def test_stored_gold_and_access_state_survive_reload(self):
        player = self.store.get(89, "储值测试")
        player.gold = 200
        player.stored_gold = 750
        player.gold_storage_available = True
        self.store.save(player)

        refreshed = self.store.get(89, "储值测试")

        self.assertEqual((refreshed.gold, refreshed.stored_gold), (200, 750))
        self.assertTrue(refreshed.gold_storage_available)

    def test_legacy_merchant_charms_are_recalculated_across_all_four_stats(self):
        legacy_state = Player(90, "旧护符玩家").to_dict()
        legacy_state.pop("merchant_charm_rules_version")
        legacy_state["merchant_charm_count"] = 50
        legacy_state["merchant_attack_bonus"] = 20
        legacy_state["merchant_defense_bonus"] = 10
        legacy_state["merchant_agility_bonus"] = 10
        legacy_state["merchant_luck_bonus"] = 10
        legacy_state["consumables"]["幸运护符"] = 3

        migrated = Player.from_dict(legacy_state)
        reloaded = Player.from_dict(migrated.to_dict())

        self.assertEqual(migrated.consumables["幸运护符"], 3)
        self.assertEqual(migrated.merchant_charm_count, 50)
        self.assertEqual(migrated.merchant_charm_base_stats, {"attack": 20, "defense": 10, "agility": 10, "luck": 10})
        self.assertAlmostEqual(migrated.merchant_attack_bonus, 20)
        self.assertAlmostEqual(migrated.merchant_defense_bonus, 10)
        self.assertAlmostEqual(migrated.merchant_agility_bonus, 10)
        self.assertAlmostEqual(migrated.merchant_luck_bonus, 10)
        self.assertEqual(reloaded.merchant_charm_count, 50)
        self.assertAlmostEqual(reloaded.merchant_attack_bonus, 20)

    def test_store_startup_persists_legacy_charm_recalculation(self):
        legacy_state = Player(91, "离线旧玩家").to_dict()
        legacy_state.pop("merchant_charm_rules_version")
        legacy_state["merchant_charm_count"] = 40
        legacy_state["merchant_attack_bonus"] = 20
        legacy_state["merchant_defense_bonus"] = 20
        with closing(self.store._connect()) as conn:
            conn.execute(
                "INSERT INTO players(user_id, state) VALUES(?, ?)",
                (91, json.dumps(legacy_state, ensure_ascii=False)),
            )
            conn.commit()

        PlayerStore(self.store.path)

        with closing(self.store._connect()) as conn:
            persisted = json.loads(conn.execute(
                "SELECT state FROM players WHERE user_id=91"
            ).fetchone()[0])
        self.assertEqual(persisted["merchant_charm_rules_version"], 6)
        self.assertAlmostEqual(persisted["merchant_attack_bonus"], 20.0)
        self.assertAlmostEqual(persisted["merchant_defense_bonus"], 20.0)

    def test_store_startup_unlocks_storage_for_old_completed_player_in_tavern(self):
        legacy_state = Player(
            92, "已通关老玩家", completion_count=2,
            gold_storage_available=False,
        ).to_dict()
        legacy_state.pop("tavern_storage_rules_version")
        with closing(self.store._connect()) as conn:
            conn.execute(
                "INSERT INTO players(user_id, state) VALUES(?, ?)",
                (92, json.dumps(legacy_state, ensure_ascii=False)),
            )
            conn.commit()

        PlayerStore(self.store.path)
        migrated = self.store.get(92, "已通关老玩家")

        self.assertTrue(migrated.gold_storage_available)

    def test_completed_players_returns_existing_clear_counts_for_backfill(self):
        self.store.save(Player(1, "未通关", completion_count=0))
        self.store.save(Player(2, "二星老玩家", completion_count=2))
        self.store.save(Player(3, "五星老玩家", completion_count=5))

        self.assertEqual(
            self.store.completed_players(),
            [(2, 2), (3, 5)],
        )
        self.assertEqual(self.store.player_ids(), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
