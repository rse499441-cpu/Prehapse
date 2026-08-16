from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Player


class PlayerStore:
    def __init__(self, path: str | Path = "data/dungeon.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS players "
                "(user_id INTEGER PRIMARY KEY, state TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS settings "
                "(setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS shared_wallets ("
                "user_id INTEGER PRIMARY KEY, "
                "gold INTEGER NOT NULL DEFAULT 0, "
                "crystals INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS wallet_migrations ("
                "source_key TEXT PRIMARY KEY, "
                "migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS weekly_challenges ("
                "week_key TEXT NOT NULL, user_id INTEGER NOT NULL, "
                "player_name TEXT NOT NULL, max_floor INTEGER NOT NULL, "
                "updated_at TEXT NOT NULL, "
                "PRIMARY KEY (week_key, user_id))"
            )
            conn.commit()
        self._migrate_player_states()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def _migrate_player_states(self) -> None:
        """启动时把全部旧玩家状态迁移并永久写回，而不是等待逐个登录。"""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT user_id, state FROM players").fetchall()
            changed = False
            for user_id, raw_state in rows:
                try:
                    state = json.loads(raw_state)
                    if (
                        int(state.get("merchant_charm_rules_version", 0)) >= 6
                        and int(state.get("tavern_storage_rules_version", 0)) >= 1
                        and int(state.get("crystal_charm_archive_version", 0)) >= 1
                    ):
                        continue
                    migrated = Player.from_dict(state)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                conn.execute(
                    "UPDATE players SET state=? WHERE user_id=?",
                    (json.dumps(migrated.to_dict(), ensure_ascii=False), user_id),
                )
                changed = True
            if changed:
                conn.commit()

    def get(self, user_id: int, name: str) -> Player:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT state FROM players WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            player = (
                Player.from_dict(json.loads(row[0]))
                if row else Player(user_id=user_id, name=name)
            )
            wallet = conn.execute(
                "SELECT gold, crystals FROM shared_wallets WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if wallet is None:
                conn.execute(
                    "INSERT INTO shared_wallets(user_id, gold, crystals) "
                    "VALUES(?, ?, ?)",
                    (user_id, player.gold, player.crystals),
                )
                conn.commit()
                wallet = (player.gold, player.crystals)
        player.gold = int(wallet[0])
        player.crystals = int(wallet[1])
        player.name = name
        player._wallet_gold_loaded = player.gold
        player._wallet_crystals_loaded = player.crystals
        return player

    def save(self, player: Player) -> None:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            wallet = conn.execute(
                "SELECT gold, crystals FROM shared_wallets WHERE user_id = ?",
                (player.user_id,),
            ).fetchone()
            if wallet is None:
                conn.execute(
                    "INSERT INTO shared_wallets(user_id, gold, crystals) VALUES(?, ?, ?)",
                    (player.user_id, player.gold, player.crystals),
                )
                shared_gold, shared_crystals = player.gold, player.crystals
            else:
                loaded_gold = int(getattr(player, "_wallet_gold_loaded", wallet[0]))
                loaded_crystals = int(
                    getattr(player, "_wallet_crystals_loaded", wallet[1])
                )
                gold_delta = player.gold - loaded_gold
                crystal_delta = player.crystals - loaded_crystals
                conn.execute(
                    "UPDATE shared_wallets SET gold=MAX(0, gold+?), "
                    "crystals=MAX(0, crystals+?) WHERE user_id=?",
                    (gold_delta, crystal_delta, player.user_id),
                )
                shared_gold, shared_crystals = conn.execute(
                    "SELECT gold, crystals FROM shared_wallets WHERE user_id=?",
                    (player.user_id,),
                ).fetchone()
            player.gold = int(shared_gold)
            player.crystals = int(shared_crystals)
            payload = json.dumps(player.to_dict(), ensure_ascii=False)
            conn.execute(
                "INSERT INTO players(user_id, state) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET state = excluded.state",
                (player.user_id, payload),
            )
            conn.commit()
        player._wallet_gold_loaded = player.gold
        player._wallet_crystals_loaded = player.crystals

    def get_setting(self, key: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT setting_value FROM settings WHERE setting_key = ?",
                (key,),
            ).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str | int) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO settings(setting_key, setting_value) VALUES(?, ?) "
                "ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value",
                (key, str(value)),
            )
            conn.commit()

    def completed_players(self) -> list[tuple[int, int]]:
        """返回至少完成过一次百层远征的玩家及其通关次数。"""
        completed: list[tuple[int, int]] = []
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT user_id, state FROM players").fetchall()
        for user_id, state in rows:
            try:
                completion_count = int(
                    json.loads(state).get("completion_count", 0)
                )
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if completion_count > 0:
                completed.append((int(user_id), completion_count))
        return completed

    def player_ids(self) -> list[int]:
        """返回所有已经建立地下城存档的玩家 ID。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT user_id FROM players ORDER BY user_id"
            ).fetchall()
        return [int(user_id) for (user_id,) in rows]

    @staticmethod
    def week_key(moment: datetime | date | None = None) -> str:
        if moment is None:
            current = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        elif isinstance(moment, datetime):
            current = moment.astimezone(ZoneInfo("Asia/Shanghai")).date()
        else:
            current = moment
        monday = current - timedelta(days=current.weekday())
        return monday.isoformat()

    def record_weekly_challenge(
        self,
        user_id: int,
        player_name: str,
        floor: int,
        moment: datetime | date | None = None,
    ) -> None:
        key = self.week_key(moment)
        updated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO weekly_challenges("
                "week_key, user_id, player_name, max_floor, updated_at"
                ") VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(week_key, user_id) DO UPDATE SET "
                "player_name = excluded.player_name, "
                "max_floor = MAX(weekly_challenges.max_floor, excluded.max_floor), "
                "updated_at = CASE "
                "WHEN excluded.max_floor > weekly_challenges.max_floor "
                "THEN excluded.updated_at ELSE weekly_challenges.updated_at END",
                (key, user_id, player_name, max(1, min(100, floor)), updated_at),
            )
            conn.commit()

    def weekly_top(
        self,
        limit: int = 15,
        moment: datetime | date | None = None,
    ) -> list[tuple[int, str, int]]:
        key = self.week_key(moment)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT user_id, player_name, max_floor "
                "FROM weekly_challenges WHERE week_key = ? "
                "ORDER BY max_floor DESC, updated_at ASC, user_id ASC LIMIT ?",
                (key, limit),
            ).fetchall()
        return [(int(user_id), str(name), int(floor)) for user_id, name, floor in rows]

    def clear_weekly_challenge(
        self,
        user_id: int,
        moment: datetime | date | None = None,
    ) -> None:
        key = self.week_key(moment)
        with closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM weekly_challenges WHERE week_key = ? AND user_id = ?",
                (key, user_id),
            )
            conn.commit()
