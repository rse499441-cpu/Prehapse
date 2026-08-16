from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from game.models import MERCHANT_CHARM_STATS, merchant_charm_bonuses


CURRENT_DB = Path("data/dungeon.db")
LEGACY_DB = Path("backups/20260803-000901/dungeon.db")


def states(path: Path) -> dict[int, dict]:
    with sqlite3.connect(path) as conn:
        return {
            int(user_id): json.loads(raw_state)
            for user_id, raw_state in conn.execute("SELECT user_id, state FROM players")
        }


def main() -> None:
    if not LEGACY_DB.exists():
        raise FileNotFoundError(f"缺少历史数据库：{LEGACY_DB}")
    legacy_states = states(LEGACY_DB)
    changed = 0
    ego_result = None
    with sqlite3.connect(CURRENT_DB) as conn:
        rows = conn.execute("SELECT user_id, state FROM players").fetchall()
        for user_id, raw_state in rows:
            current = json.loads(raw_state)
            legacy = legacy_states.get(int(user_id))
            if not legacy:
                continue
            clears = max(0, int(legacy.get("completion_count", 0)))
            legacy_counts = {
                "attack": max(0, int(legacy.get("permanent_attack_bonus", 0)) - clears * 5),
                "defense": max(0, int(legacy.get("permanent_defense_bonus", 0)) - clears * 3),
                "agility": max(0, int(legacy.get("permanent_agility_bonus", 0))),
                "luck": max(0, int(legacy.get("permanent_luck_bonus", 0))),
            }
            current_base = dict(current.get("merchant_charm_base_stats", {}))
            combined = {
                stat: legacy_counts[stat] + max(0, int(current_base.get(stat, 0)))
                for stat in MERCHANT_CHARM_STATS
            }
            for stat in MERCHANT_CHARM_STATS:
                permanent_key = f"permanent_{stat}_bonus"
                current[permanent_key] = max(
                    0, float(current.get(permanent_key, 0)) - legacy_counts[stat]
                )
            bonuses = merchant_charm_bonuses(combined)
            current["merchant_charm_base_stats"] = combined
            current["merchant_charm_count"] = sum(combined.values())
            for stat in MERCHANT_CHARM_STATS:
                current[f"merchant_{stat}_bonus"] = bonuses[stat]
            current["merchant_charm_rules_version"] = 6
            conn.execute(
                "UPDATE players SET state=? WHERE user_id=?",
                (json.dumps(current, ensure_ascii=False), user_id),
            )
            changed += 1
            if str(current.get("name", "")).lower() == "ego":
                ego_result = {
                    "legacy_counts": legacy_counts,
                    "combined_counts": combined,
                    "bonuses": bonuses,
                    "remaining_permanent": {
                        stat: current[f"permanent_{stat}_bonus"]
                        for stat in MERCHANT_CHARM_STATS
                    },
                }
        conn.commit()
    print(json.dumps({"changed_players": changed, "ego": ego_result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
