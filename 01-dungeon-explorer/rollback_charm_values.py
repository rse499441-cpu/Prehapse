import json
import sqlite3
from pathlib import Path

CURRENT = Path("data/dungeon.db")
SOURCE = Path("backups/20260804-224653/dungeon.db")
FIELDS = (
    "permanent_attack_bonus", "permanent_defense_bonus",
    "permanent_agility_bonus", "permanent_luck_bonus",
    "merchant_charm_count", "merchant_attack_bonus",
    "merchant_defense_bonus", "merchant_agility_bonus",
    "merchant_luck_bonus",
)

def load_states(path: Path) -> dict[int, dict]:
    with sqlite3.connect(path) as connection:
        return {
            int(user_id): json.loads(state)
            for user_id, state in connection.execute("SELECT user_id, state FROM players")
        }

def main() -> None:
    old_states = load_states(SOURCE)
    changed = 0
    with sqlite3.connect(CURRENT) as connection:
        for user_id, encoded in connection.execute("SELECT user_id, state FROM players").fetchall():
            user_id = int(user_id)
            old = old_states.get(user_id)
            if old is None:
                continue
            current = json.loads(encoded)
            for field in FIELDS:
                current[field] = old.get(field, 0)
            current["merchant_charm_base_stats"] = {}
            current["merchant_charm_rules_version"] = 2
            connection.execute(
                "UPDATE players SET state=? WHERE user_id=?",
                (json.dumps(current, ensure_ascii=False), user_id),
            )
            changed += 1
        connection.commit()
    print(json.dumps({"restored_players": changed, "source": str(SOURCE)}))

if __name__ == "__main__":
    main()
