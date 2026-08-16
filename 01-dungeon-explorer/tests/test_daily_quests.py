import unittest

from game.daily_quests import (
    QUEST_POOL,
    claim_all,
    progress,
    quests_for,
    record_action,
    sync_daily_quests,
)
from game.models import Enemy, Player


class DailyQuestTests(unittest.TestCase):
    day = "2026-07-30"

    def active_player_for(self, key: str) -> tuple[Player, object]:
        player = Player(1, "测试者")
        quest = next(item for item in QUEST_POOL if item.key == key)
        player.daily_quest_date = self.day
        # Tests can target any definition independently of the day's random sample.
        return player, quest

    def test_daily_selection_is_stable(self):
        self.assertEqual(quests_for(self.day), quests_for(self.day))
        self.assertIn(len(quests_for(self.day)), (2, 3))

    def test_new_day_clears_progress_and_claims(self):
        player = Player(
            1,
            "测试者",
            daily_quest_date="2026-07-29",
            daily_quest_progress={"gold_earned": 999},
            daily_quest_claimed=["gold_earned"],
        )
        sync_daily_quests(player, self.day)
        self.assertEqual(player.daily_quest_progress, {})
        self.assertEqual(player.daily_quest_claimed, [])

    def test_claim_rewards_once(self):
        player = Player(1, "测试者", daily_quest_date=self.day)
        active = quests_for(self.day)
        for quest in active:
            player.daily_quest_progress[quest.key] = quest.target
        claimed, _ = claim_all(player, self.day)
        balances = (player.gold, player.crystals, player.exp, player.level)
        claimed_again, _ = claim_all(player, self.day)
        self.assertEqual(len(claimed), len(active))
        self.assertEqual(claimed_again, [])
        self.assertEqual((player.gold, player.crystals, player.exp, player.level), balances)

    def test_records_victorious_boss_and_gold(self):
        player = Player(1, "测试者", daily_quest_date=self.day, gold=150)
        enemy = Enemy("守层者", 0, 10, 1, 1, boss_kind="小 Boss")
        player.enemy = None
        record_action(
            player, self.day, "attack", 5, 6, 10, 100, None, enemy, "🎉 战斗胜利"
        )
        active = {quest.key for quest in quests_for(self.day)}
        if "small_bosses" in active:
            self.assertEqual(player.daily_quest_progress["small_bosses"], 1)
        if "gold_earned" in active:
            self.assertEqual(player.daily_quest_progress["gold_earned"], 50)
        if "floors" in active:
            self.assertEqual(player.daily_quest_progress["floors"], 1)

    def test_potion_resets_potion_free_progress_when_active(self):
        player = Player(
            1, "测试者", daily_quest_date=self.day,
            daily_quest_progress={"potion_free": 12},
        )
        record_action(
            player, self.day, "use_potion", 1, 1, 50, 0, None, None, "使用药水"
        )
        if "potion_free" in {quest.key for quest in quests_for(self.day)}:
            self.assertEqual(player.daily_quest_progress["potion_free"], 0)


if __name__ == "__main__":
    unittest.main()
