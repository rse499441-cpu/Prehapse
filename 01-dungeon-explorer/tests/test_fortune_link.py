import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from game.fortune_link import fortune_crystal_growth, fortune_luck_bonus, sync_daily_fortune
from game.models import Player


class FortuneLinkTests(unittest.TestCase):
    def test_fortune_growth_thresholds_are_bounded(self):
        self.assertEqual(fortune_crystal_growth(69), 0.0)
        self.assertEqual(fortune_crystal_growth(70), 0.20)
        self.assertEqual(fortune_crystal_growth(80), 0.40)
        self.assertEqual(fortune_crystal_growth(90), 0.60)
        self.assertEqual(fortune_crystal_growth(100), 0.60)
        self.assertEqual(fortune_luck_bonus(100), 0)

    def test_today_good_fortune_grows_fairy_crystal_chance_without_adding_luck(self):
        now = datetime(2026, 7, 23, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fortune_draws.json"
            path.write_text(json.dumps({
                "123:456:2026-07-23": {
                    "time": "2026-07-23T08:00:00+08:00",
                    "keyword": "云开见喜",
                    "overall_score": 88,
                }
            }), encoding="utf-8")
            player = Player(456, "冒险者", weapon_luck=2)

            bonus = sync_daily_fortune(player, 123, path, now)

            self.assertEqual(bonus, 0.40)
            self.assertEqual(player.daily_fortune_score, 88)
            self.assertEqual(player.daily_fortune_growth, 0.40)
            self.assertEqual(player.luck, 2)

    def test_other_day_or_other_user_gets_no_bonus(self):
        now = datetime(2026, 7, 24, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fortune_draws.json"
            path.write_text(json.dumps({
                "123:456:2026-07-23": {
                    "overall_score": 96,
                }
            }), encoding="utf-8")
            player = Player(999, "另一位冒险者")

            bonus = sync_daily_fortune(player, 123, path, now)

            self.assertEqual(bonus, 0)
            self.assertEqual(player.luck, 0)


if __name__ == "__main__":
    unittest.main()
