from __future__ import annotations

import json
import sqlite3

from game.models import (
    MERCHANT_CHARM_STATS,
    Player,
    inferred_crystal_charm_count,
    merchant_charm_bonuses,
)


EGO_USER_ID = 1221643095586767001


def main() -> None:
    errors = []
    checked = 0
    ego = None
    with sqlite3.connect("data/dungeon.db") as connection:
        rows = connection.execute("SELECT user_id,state FROM players").fetchall()
    for raw_user_id, raw_state in rows:
        user_id = int(raw_user_id)
        state = json.loads(raw_state)
        player = Player.from_dict(state)
        checked += 1
        expected_permanent = {
            "attack": player.completion_count * 5,
            "defense": player.completion_count * 3,
            "agility": 0,
            "luck": 0,
        }
        actual_permanent = {
            stat: float(getattr(player, f"permanent_{stat}_bonus"))
            for stat in MERCHANT_CHARM_STATS
        }
        expected_merchant = merchant_charm_bonuses(player.merchant_charm_base_stats)
        actual_merchant = {
            stat: float(getattr(player, f"merchant_{stat}_bonus"))
            for stat in MERCHANT_CHARM_STATS
        }
        if int(state.get("charm_source_rules_version", 0)) != 4:
            errors.append({"user_id": user_id, "error": "source version"})
        if int(state.get("crystal_charm_archive_version", 0)) != 1:
            errors.append({"user_id": user_id, "error": "crystal archive version"})
        if "crystal_charm_counts" in state or "crystal_charms" in state:
            errors.append({"user_id": user_id, "error": "legacy crystal quantity fields"})
        if actual_permanent != expected_permanent:
            errors.append({"user_id": user_id, "error": "completion", "actual": actual_permanent, "expected": expected_permanent})
        if actual_merchant != expected_merchant:
            errors.append({"user_id": user_id, "error": "merchant", "actual": actual_merchant, "expected": expected_merchant})
        for stat in MERCHANT_CHARM_STATS:
            expected_minimum = inferred_crystal_charm_count(
                state.get(f"crystal_{stat}_bonus", 0)
            )
            actual_count = int(state.get("crystal_charm_stat_counts", {}).get(stat, 0))
            if actual_count < expected_minimum:
                errors.append({
                    "user_id": user_id,
                    "error": f"crystal {stat} count below minimum",
                    "actual": actual_count,
                    "expected_minimum": expected_minimum,
                })
        persisted_counts = state.get("crystal_charm_stat_counts", {})
        persisted_draws = int(state.get("crystal_charm_draw_count", 0))
        if persisted_draws < max(persisted_counts.values(), default=0):
            errors.append({"user_id": user_id, "error": "crystal draw count below stat count"})
        if user_id == EGO_USER_ID:
            ego = {
                "completion_count": player.completion_count,
                "merchant_counts": player.merchant_charm_base_stats,
                "merchant_bonus": expected_merchant,
                "crystal_bonus": {
                    stat: player.crystal_charm_bonus(stat)
                    for stat in MERCHANT_CHARM_STATS
                },
                "crystal_draw_count": player.crystal_charm_draw_count,
                "crystal_stat_counts": player.crystal_charm_stat_counts,
                "final": {
                    "attack_bonus": player.attack_bonus,
                    "defense": player.defense,
                    "agility": player.agility,
                    "luck": player.luck,
                },
            }
    result = {"checked_players": checked, "errors": errors, "ego": ego}
    print(json.dumps(result, ensure_ascii=False))
    if errors or ego is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
