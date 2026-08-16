from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Enemy, Player


@dataclass(frozen=True)
class DailyQuest:
    key: str
    emoji: str
    name: str
    description: str
    target: int
    reward_kind: str
    reward_amount: int

    @property
    def reward_text(self) -> str:
        labels = {"gold": "金币", "exp": "经验", "crystals": "魔法水晶"}
        return f"{labels[self.reward_kind]} ×{self.reward_amount}"


QUEST_POOL = (
    DailyQuest("slimes", "🟢", "黏液灾害清扫令", "击杀 35 只史莱姆", 35, "exp", 150),
    DailyQuest("floors", "🏰", "深入幽灯岩窟", "单日向下推进 10 层", 10, "gold", 180),
    DailyQuest("chests", "📦", "资深宝箱观察员", "开启 12 个真正的宝箱", 12, "gold", 160),
    DailyQuest("small_bosses", "👾", "守层者连战", "击败 5 只小 Boss", 5, "exp", 150),
    DailyQuest("potion_free", "🧪", "无伤补给挑战", "不使用药水连续完成 20 次探索", 20, "gold", 200),
    DailyQuest("gold_earned", "🪙", "地下淘金者", "单日获得 1,000 金币", 1000, "gold", 120),
    DailyQuest("major_bosses", "🔮", "稀有水晶委托", "击败 3 只大 Boss", 3, "crystals", 1),
    DailyQuest("reach_floor", "💯", "远征记录", "单次冒险抵达第 50 层", 50, "crystals", 1),
)


def quests_for(day: str) -> list[DailyQuest]:
    rng = random.Random(f"dungeon-daily-quests:{day}:v1")
    return rng.sample(list(QUEST_POOL), k=rng.randint(2, 3))


def sync_daily_quests(player: Player, day: str) -> None:
    if player.daily_quest_date != day:
        player.daily_quest_date = day
        player.daily_quest_progress = {}
        player.daily_quest_claimed = []


def progress(player: Player, quest: DailyQuest) -> int:
    return min(quest.target, max(0, int(player.daily_quest_progress.get(quest.key, 0))))


def completed_unclaimed(player: Player, day: str) -> list[DailyQuest]:
    sync_daily_quests(player, day)
    return [
        quest for quest in quests_for(day)
        if progress(player, quest) >= quest.target
        and quest.key not in player.daily_quest_claimed
    ]


def record_action(
    player: Player,
    day: str,
    action: str,
    before_floor: int,
    achieved_floor: int,
    before_energy: int,
    before_gold: int,
    before_event: str | None,
    before_enemy: Enemy | None,
    result_title: str,
) -> list[DailyQuest]:
    sync_daily_quests(player, day)
    active_keys = {quest.key for quest in quests_for(day)}
    values = player.daily_quest_progress
    was_complete = {
        quest.key for quest in quests_for(day) if progress(player, quest) >= quest.target
    }

    def add(key: str, amount: int = 1) -> None:
        if key in active_keys and amount > 0:
            values[key] = max(0, int(values.get(key, 0))) + amount

    if action == "explore" and player.energy == before_energy - 3:
        add("potion_free")
    elif action in {"use_potion", "use_mana_potion", "use_energy_potion"}:
        if "potion_free" in active_keys:
            values["potion_free"] = 0

    add("floors", max(0, achieved_floor - before_floor))
    if "reach_floor" in active_keys:
        values["reach_floor"] = max(int(values.get("reach_floor", 0)), achieved_floor)
    if action == "interact_event" and before_event == "chest" and player.pending_event is None:
        add("chests")

    victory = (
        before_enemy is not None
        and player.enemy is None
        and ("战斗胜利" in result_title or "百层远征完成" in result_title)
    )
    if victory:
        if "史莱姆" in before_enemy.name:
            add("slimes")
        if before_enemy.boss_kind == "小 Boss":
            add("small_bosses")
        elif before_enemy.boss_kind == "大 Boss":
            add("major_bosses")

    add("gold_earned", max(0, player.gold - before_gold))
    return [
        quest for quest in quests_for(day)
        if quest.key not in was_complete and progress(player, quest) >= quest.target
    ]


def claim_all(player: Player, day: str) -> tuple[list[DailyQuest], str]:
    ready = completed_unclaimed(player, day)
    if not ready:
        return [], "目前没有已完成且待领取的委托奖励。"
    rewards: list[str] = []
    for quest in ready:
        if quest.reward_kind == "gold":
            player.gold += quest.reward_amount
        elif quest.reward_kind == "crystals":
            player.crystals += quest.reward_amount
        else:
            player.exp += quest.reward_amount
            while player.exp >= player.exp_required:
                player.exp -= player.exp_required
                player.level += 1
                player.max_hp += 8
                player.max_mp += 4
                player.max_energy += 3
                player.hp = min(player.max_hp, player.hp + 24)
                player.mp = min(player.max_mp, player.mp + 10)
                player.energy = min(player.max_energy, player.energy + 12)
        player.daily_quest_claimed.append(quest.key)
        rewards.append(f"{quest.emoji} **{quest.name}**：{quest.reward_text}")
    return ready, "领取成功！\n" + "\n".join(rewards)
