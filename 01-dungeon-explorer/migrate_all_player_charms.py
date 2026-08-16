from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from game.models import (
    MERCHANT_CHARM_STATS,
    inferred_crystal_charm_count,
    merchant_charm_bonuses,
)


CURRENT_DB = Path("data/dungeon.db")
LEGACY_DB = Path("backups/20260803-000901/dungeon.db")
EGO_USER_ID = 1221643095586767001


def load_states(path: Path) -> dict[int, dict]:
    with sqlite3.connect(path) as connection:
        return {
            int(user_id): json.loads(raw)
            for user_id, raw in connection.execute("SELECT user_id,state FROM players")
        }


def completion_bonuses(clears: int) -> dict[str, float]:
    return {
        "attack": clears * 5,
        "defense": clears * 3,
        "agility": 0,
        "luck": 0,
    }


def legacy_merchant_values(state: dict | None) -> dict[str, float]:
    if state is None:
        return {stat: 0 for stat in MERCHANT_CHARM_STATS}
    blessing = completion_bonuses(max(0, int(state.get("completion_count", 0))))
    return {
        stat: max(
            0.0,
            float(state.get(f"permanent_{stat}_bonus", 0)) - blessing[stat],
        )
        for stat in MERCHANT_CHARM_STATS
    }


def unattenuated_crystal_bonuses(state: dict, counts: dict[str, int]) -> dict[str, float]:
    records = state.get("crystal_charms", {})
    if not isinstance(records, dict):
        records = {}
    bonuses = {}
    for stat in MERCHANT_CHARM_STATS:
        recorded_count = 0
        recorded_bonus = 0.0
        for item in records.values():
            if not isinstance(item, dict) or float(item.get(stat, 0)) <= 0:
                continue
            item_count = max(0, int(item.get("count", 0)))
            recorded_count += item_count
            recorded_bonus += float(item.get(stat, 0)) * item_count
        historical_unknown_count = max(0, counts[stat] - recorded_count)
        bonuses[stat] = round(historical_unknown_count * 4 + recorded_bonus, 2)
    return bonuses


def normalise_stat_counts(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        raw = {}
    return {
        stat: max(0, int(raw.get(stat, 0)))
        for stat in MERCHANT_CHARM_STATS
    }


def inferred_draw_count(counts: dict[str, int]) -> int:
    return max(counts.values(), default=0)


def inferred_stat_counts(bonuses: dict[str, float]) -> dict[str, int]:
    return {
        stat: inferred_crystal_charm_count(bonuses.get(stat, 0))
        for stat in MERCHANT_CHARM_STATS
    }


def migrate_state(
    user_id: int,
    state: dict,
    legacy: dict | None,
) -> tuple[dict, dict]:
    source_version = int(state.get("charm_source_rules_version", 0))
    if source_version >= 4:
        return state, {"status": "skipped"}

    if source_version == 3:
        crystal_bonus = {
            stat: round(float(state.get(f"crystal_{stat}_bonus", 0)), 2)
            for stat in MERCHANT_CHARM_STATS
        }
        crystal_stat_counts = inferred_stat_counts(crystal_bonus)
        crystal_draw_count = inferred_draw_count(crystal_stat_counts)
        state["crystal_charm_stat_counts"] = crystal_stat_counts
        state["crystal_charm_draw_count"] = crystal_draw_count
        state["charm_source_rules_version"] = 4
        state["crystal_charm_history_note"] = (
            "历史属性次数按当前累计数值除以4并向上取整；历史总次数取四项最大值，后续为精确记录。"
        )
        return state, {
            "status": "updated",
            "name": state.get("name"),
            "crystal_draw_count": crystal_draw_count,
            "crystal_stat_counts": crystal_stat_counts,
            "crystal_bonus": {
                stat: state.get(f"crystal_{stat}_bonus", 0)
                for stat in MERCHANT_CHARM_STATS
            },
        }

    if source_version in {1, 2}:
        crystal_counts = normalise_stat_counts(state.get("crystal_charm_counts", {}))
        if any(crystal_counts.values()):
            crystal_bonus = unattenuated_crystal_bonuses(state, crystal_counts)
        else:
            crystal_bonus = {
                stat: round(float(state.get(f"crystal_{stat}_bonus", 0)), 2)
                for stat in MERCHANT_CHARM_STATS
            }
        for stat in MERCHANT_CHARM_STATS:
            state[f"crystal_{stat}_bonus"] = crystal_bonus[stat]
        state.pop("crystal_charm_counts", None)
        state.pop("crystal_charms", None)
        crystal_counts = inferred_stat_counts(crystal_bonus)
        state["crystal_charm_stat_counts"] = crystal_counts
        state["crystal_charm_draw_count"] = inferred_draw_count(crystal_counts)
        state["charm_source_rules_version"] = 4
        state["crystal_charm_history_note"] = str(
            state.get("crystal_charm_history_note", "")
        ).replace("水晶池独立衰减", "水晶护符仅记录累计数值，不衰减")
        return state, {
            "status": "updated",
            "name": state.get("name"),
            "crystal_draw_count": state["crystal_charm_draw_count"],
            "crystal_stat_counts": crystal_counts,
            "crystal_bonus": crystal_bonus,
        }

    clears = max(0, int(state.get("completion_count", 0)))
    blessing = completion_bonuses(clears)
    old_merchant = legacy_merchant_values(legacy)
    historical_crystal_scores = {
        stat: max(
            0.0,
            round(
                float(state.get(f"permanent_{stat}_bonus", 0))
                - old_merchant[stat]
                - blessing[stat],
                2,
            ),
        )
        for stat in MERCHANT_CHARM_STATS
    }

    if any(historical_crystal_scores.values()):
        state["crystal_charm_history_note"] = (
            "历史属性次数按当前累计数值除以4并向上取整；历史总次数取四项最大值。"
        )
    else:
        state["crystal_charm_history_note"] = "未发现可确认的历史水晶护符属性。"

    crystal_bonus = historical_crystal_scores
    crystal_stat_counts = inferred_stat_counts(crystal_bonus)

    counts = state.get("merchant_charm_base_stats", {})
    if not isinstance(counts, dict):
        counts = {}
    counts = {
        stat: max(0, int(counts.get(stat, 0)))
        for stat in MERCHANT_CHARM_STATS
    }
    merchant = merchant_charm_bonuses(counts)
    for stat in MERCHANT_CHARM_STATS:
        state[f"permanent_{stat}_bonus"] = blessing[stat]
        state[f"crystal_{stat}_bonus"] = crystal_bonus[stat]
        state[f"merchant_{stat}_bonus"] = merchant[stat]
    state["merchant_charm_base_stats"] = counts
    state.pop("crystal_charm_counts", None)
    state.pop("crystal_charms", None)
    state["crystal_charm_stat_counts"] = crystal_stat_counts
    state["crystal_charm_draw_count"] = inferred_draw_count(crystal_stat_counts)
    state["merchant_charm_count"] = sum(counts.values())
    state["merchant_charm_rules_version"] = 6
    state["charm_source_rules_version"] = 4
    return state, {
        "status": "updated",
        "name": state.get("name"),
        "completion": blessing,
        "merchant_counts": counts,
        "merchant_bonus": merchant,
        "crystal_draw_count": state["crystal_charm_draw_count"],
        "crystal_stat_counts": crystal_stat_counts,
        "crystal_bonus": crystal_bonus,
    }


def main() -> None:
    if not LEGACY_DB.exists():
        raise FileNotFoundError(f"missing legacy database: {LEGACY_DB}")
    legacy_states = load_states(LEGACY_DB)
    report = []
    with sqlite3.connect(CURRENT_DB) as connection:
        rows = connection.execute("SELECT user_id,state FROM players").fetchall()
        for raw_user_id, raw_state in rows:
            user_id = int(raw_user_id)
            state = json.loads(raw_state)
            migrated, result = migrate_state(
                user_id,
                state,
                legacy_states.get(user_id),
            )
            report.append({"user_id": user_id, **result})
            if result["status"] == "updated":
                connection.execute(
                    "UPDATE players SET state=? WHERE user_id=?",
                    (json.dumps(migrated, ensure_ascii=False), user_id),
                )
        connection.commit()
    updated = sum(item["status"] == "updated" for item in report)
    ego = next((item for item in report if item["user_id"] == EGO_USER_ID), None)
    print(json.dumps({"updated_players": updated, "ego": ego}, ensure_ascii=False))


if __name__ == "__main__":
    main()
