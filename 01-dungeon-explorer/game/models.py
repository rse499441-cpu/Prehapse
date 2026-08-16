from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


MERCHANT_CHARM_STATS = ("attack", "defense", "agility", "luck")


def inferred_crystal_charm_count(bonus: float) -> int:
    """历史水晶数值反推次数：有数值时至少记 1 次。"""
    value = max(0.0, float(bonus))
    return max(1, math.ceil(value / 4)) if value > 0 else 0


def merchant_charm_rate(charm_number: int) -> float:
    """旅行商人护符按累计获得数量逐档衰减。"""
    if charm_number <= 20:
        return 1.0
    if charm_number <= 40:
        return 0.8
    if charm_number <= 60:
        return 0.5
    if charm_number <= 80:
        return 0.3
    if charm_number <= 100:
        return 0.2
    return 0.1


def merchant_charm_total(charm_count: int) -> float:
    """金币渠道护符按规则表逐档累计后的总加成 m。"""
    charm_count = max(0, int(charm_count))
    tiers = ((20, 1.0), (20, 0.8), (20, 0.5), (20, 0.3), (20, 0.2))
    total = 0.0
    remaining = charm_count
    for size, rate in tiers:
        used = min(remaining, size)
        total += used * rate
        remaining -= used
        if remaining <= 0:
            return round(total, 2)
    return round(total + remaining * 0.1, 2)


def merchant_charm_bonuses(counts: dict[str, int]) -> dict[str, float]:
    """四类商人护符分别按各自历史获得数量计算永久加成。"""
    return {
        stat: merchant_charm_total(max(0, int(counts.get(stat, 0))))
        for stat in MERCHANT_CHARM_STATS
    }


def _infer_merchant_charm_counts(values: dict[str, Any]) -> dict[str, int]:
    """旧档缺少分类计数时，按现有四维加成比例分配历史总数。"""
    total_count = max(0, int(values.get("merchant_charm_count", 0)))
    weights = [max(0.0, float(values.get(f"merchant_{stat}_bonus", 0.0))) for stat in MERCHANT_CHARM_STATS]
    weight_total = sum(weights)
    if total_count <= 0 or weight_total <= 0:
        return {stat: 0 for stat in MERCHANT_CHARM_STATS}
    exact = [total_count * weight / weight_total for weight in weights]
    allocated = [int(number) for number in exact]
    for index in sorted(range(4), key=lambda i: exact[i] - allocated[i], reverse=True)[:total_count - sum(allocated)]:
        allocated[index] += 1
    return dict(zip(MERCHANT_CHARM_STATS, allocated))


@dataclass
class Enemy:
    name: str
    hp: int
    max_hp: int
    attack: int
    exp_reward: int
    boss_kind: str = "普通怪物"
    level: int = 1
    catchphrase: str = "它正不怀好意地盯着你的行囊。"
    floor: int = 1
    adventure_star: int = 0
    charged_spell: str = ""
    shield_ratio: float = 0.0
    stolen_gold: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Enemy":
        return cls(**data)


@dataclass
class Player:
    user_id: int
    name: str
    level: int = 1
    exp: int = 0
    hp: int = 100
    max_hp: int = 100
    mp: int = 50
    max_mp: int = 50
    energy: int = 100
    max_energy: int = 100
    floor: int = 1
    steps: int = 0
    required_steps: int = 0
    gold: int = 0
    stored_gold: int = 0
    gold_storage_available: bool = False
    crystals: int = 0
    weapon: str = "新手短剑"
    weapon_attack: int = 4
    weapon_agility: int = 0
    weapon_luck: int = 0
    clothing: str = "布衣"
    clothing_defense: int = 1
    clothing_agility: int = 0
    clothing_luck: int = 0
    permanent_attack_bonus: int = 0
    permanent_defense_bonus: int = 0
    permanent_agility_bonus: int = 0
    permanent_luck_bonus: int = 0
    crystal_attack_bonus: float = 0.0
    crystal_defense_bonus: float = 0.0
    crystal_agility_bonus: float = 0.0
    crystal_luck_bonus: float = 0.0
    crystal_charm_draw_count: int = 0
    crystal_charm_stat_counts: dict[str, int] = field(default_factory=dict)
    crystal_charm_archive_version: int = 1
    daily_fortune_bonus: int = 0
    daily_fortune_growth: float = 0.0
    daily_fortune_date: str = ""
    daily_fortune_score: int = 0
    consumables: dict[str, int] = field(default_factory=lambda: {"治疗药水": 2})
    equipment_inventory: dict[str, dict[str, Any]] = field(default_factory=dict)
    crystal_equipment: dict[str, int] = field(default_factory=dict)
    crystal_charm_history_note: str = ""
    merchant_stock: dict[str, int] = field(default_factory=dict)
    merchant_refreshes: int = 0
    merchant_charm_count: int = 0
    merchant_attack_bonus: float = 0.0
    merchant_defense_bonus: float = 0.0
    merchant_agility_bonus: float = 0.0
    merchant_luck_bonus: float = 0.0
    merchant_charm_base_stats: dict[str, int] = field(default_factory=dict)
    merchant_charm_rules_version: int = 6
    charm_source_rules_version: int = 4
    tavern_storage_rules_version: int = 1
    enemy: Enemy | None = None
    pending_event: str | None = None
    in_adventure: bool = False
    completion_count: int = 0
    daily_quest_date: str = ""
    daily_quest_progress: dict[str, int] = field(default_factory=dict)
    daily_quest_claimed: list[str] = field(default_factory=list)

    @property
    def defense(self) -> float:
        return round(
            self.clothing_defense
            + self.permanent_defense_bonus
            + self.crystal_charm_bonus("defense")
            + self.merchant_charm_bonus("defense"),
            2,
        )

    @property
    def attack_bonus(self) -> float:
        return round(
            self.weapon_attack
            + self.permanent_attack_bonus
            + self.crystal_charm_bonus("attack")
            + self.merchant_charm_bonus("attack"),
            2,
        )

    @property
    def agility(self) -> float:
        return round((
            self.weapon_agility + self.clothing_agility
            + self.permanent_agility_bonus
            + self.crystal_charm_bonus("agility")
            + self.merchant_charm_bonus("agility")
        ), 2)

    @property
    def luck(self) -> float:
        return round((
            self.weapon_luck
            + self.clothing_luck
            + self.permanent_luck_bonus
            + self.crystal_charm_bonus("luck")
            + self.merchant_charm_bonus("luck")
        ), 2)

    def merchant_charm_bonus(self, stat: str) -> float:
        """Always derive the live bonus from the per-stat charm count."""
        if stat not in MERCHANT_CHARM_STATS:
            raise ValueError(f"unknown merchant charm stat: {stat}")
        return merchant_charm_total(self.merchant_charm_base_stats.get(stat, 0))

    def completion_bonus(self, stat: str) -> float:
        """Permanent bonus earned from clearing floor 100."""
        if stat == "attack":
            return self.completion_count * 5
        if stat == "defense":
            return self.completion_count * 3
        if stat in {"agility", "luck"}:
            return 0
        raise ValueError(f"unknown permanent stat: {stat}")

    def crystal_charm_bonus(self, stat: str) -> float:
        """Crystal charms are recorded separately and never decay."""
        if stat not in MERCHANT_CHARM_STATS:
            raise ValueError(f"unknown crystal charm stat: {stat}")
        return round(float(getattr(self, f"crystal_{stat}_bonus")), 2)

    def total_charm_bonus(self, stat: str) -> float:
        """All charms: crystal charms plus independently-decayed merchant charms."""
        return round(self.crystal_charm_bonus(stat) + self.merchant_charm_bonus(stat), 2)

    @property
    def is_adventuring(self) -> bool:
        """兼容旧存档：只要仍有探索进度或事件，就视为正在冒险。"""
        return bool(
            self.in_adventure
            or self.floor > 1
            or self.steps > 0
            or self.enemy is not None
            or self.pending_event is not None
        )

    @property
    def exp_required(self) -> int:
        return 100 + (self.level - 1) * 50

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["enemy"] = self.enemy.to_dict() if self.enemy else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Player":
        values = dict(data)
        # Version 3 stores only four crystal-charm value totals. Older count
        # and item-detail fields are intentionally discarded after migration.
        values.pop("crystal_charm_counts", None)
        values.pop("crystal_charms", None)
        enemy = values.pop("enemy", None)
        stored_crystal_counts = values.get("crystal_charm_stat_counts", {})
        if not isinstance(stored_crystal_counts, dict):
            stored_crystal_counts = {}
        crystal_counts = {
            stat: max(
                0,
                int(stored_crystal_counts.get(stat, 0)),
                inferred_crystal_charm_count(values.get(f"crystal_{stat}_bonus", 0)),
            )
            for stat in MERCHANT_CHARM_STATS
        }
        values["crystal_charm_stat_counts"] = crystal_counts
        values["crystal_charm_draw_count"] = max(
            0,
            int(values.get("crystal_charm_draw_count", 0)),
            max(crystal_counts.values(), default=0),
        )
        values["crystal_charm_archive_version"] = 1
        if int(values.get("tavern_storage_rules_version", 0)) < 1:
            is_in_tavern = not (
                bool(values.get("in_adventure", False))
                or int(values.get("floor", 1)) > 1
                or int(values.get("steps", 0)) > 0
                or enemy is not None
                or values.get("pending_event") is not None
            )
            if int(values.get("completion_count", 0)) > 0 and is_in_tavern:
                values["gold_storage_available"] = True
            values["tavern_storage_rules_version"] = 1
        if int(values.get("merchant_charm_rules_version", 0)) < 5:
            stored_counts = values.get("merchant_charm_base_stats", {})
            if isinstance(stored_counts, dict) and any(int(stored_counts.get(stat, 0)) > 0 for stat in MERCHANT_CHARM_STATS):
                counts = {stat: max(0, int(stored_counts.get(stat, 0))) for stat in MERCHANT_CHARM_STATS}
            else:
                counts = _infer_merchant_charm_counts(values)
            bonuses = merchant_charm_bonuses(counts)
            values["merchant_charm_base_stats"] = counts
            values["merchant_charm_count"] = sum(counts.values())
            for stat in MERCHANT_CHARM_STATS:
                values[f"merchant_{stat}_bonus"] = bonuses[stat]
            values["merchant_charm_rules_version"] = 6
        else:
            # Counts are the source of truth. Recompute cached fields on every
            # load so the UI, combat settlement, and the rules table cannot drift.
            stored_counts = values.get("merchant_charm_base_stats", {})
            if not isinstance(stored_counts, dict):
                stored_counts = {}
            counts = {
                stat: max(0, int(stored_counts.get(stat, 0)))
                for stat in MERCHANT_CHARM_STATS
            }
            bonuses = merchant_charm_bonuses(counts)
            values["merchant_charm_base_stats"] = counts
            values["merchant_charm_count"] = sum(counts.values())
            for stat in MERCHANT_CHARM_STATS:
                values[f"merchant_{stat}_bonus"] = bonuses[stat]
            values["merchant_charm_rules_version"] = 6
        old_stock = values.get("merchant_stock", {})
        if isinstance(old_stock, list):
            potion_keys = {
                "healing_potion", "mana_potion", "energy_potion",
                "greater_healing_potion", "greater_energy_potion",
            }
            values["merchant_stock"] = {
                key: 4 if key in potion_keys else 1
                for key in old_stock
            }
        player = cls(**values)
        player.enemy = Enemy.from_dict(enemy) if enemy else None
        return player
