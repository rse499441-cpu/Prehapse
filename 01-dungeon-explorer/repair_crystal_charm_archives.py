from __future__ import annotations

import json
import sqlite3

from game.models import MERCHANT_CHARM_STATS, Player, inferred_crystal_charm_count


def main() -> None:
    repaired = []
    with sqlite3.connect("data/dungeon.db") as connection:
        rows = connection.execute("SELECT user_id,state FROM players").fetchall()
        for raw_user_id, raw_state in rows:
            user_id = int(raw_user_id)
            state = json.loads(raw_state)
            before_counts = state.get("crystal_charm_stat_counts", {})
            before_draws = int(state.get("crystal_charm_draw_count", 0))
            player = Player.from_dict(state)
            expected_counts = {
                stat: max(
                    0,
                    int(before_counts.get(stat, 0)) if isinstance(before_counts, dict) else 0,
                    inferred_crystal_charm_count(state.get(f"crystal_{stat}_bonus", 0)),
                )
                for stat in MERCHANT_CHARM_STATS
            }
            expected_draws = max(before_draws, max(expected_counts.values(), default=0))
            if (
                player.crystal_charm_stat_counts != before_counts
                or player.crystal_charm_draw_count != before_draws
                or int(state.get("crystal_charm_archive_version", 0)) < 1
            ):
                connection.execute(
                    "UPDATE players SET state=? WHERE user_id=?",
                    (json.dumps(player.to_dict(), ensure_ascii=False), user_id),
                )
                repaired.append(
                    {
                        "user_id": user_id,
                        "name": player.name,
                        "before_counts": before_counts,
                        "after_counts": expected_counts,
                        "before_draws": before_draws,
                        "after_draws": expected_draws,
                    }
                )
        connection.commit()
    print(json.dumps({"checked_players": len(rows), "repaired_players": len(repaired), "repairs": repaired}, ensure_ascii=False))


if __name__ == "__main__":
    main()
