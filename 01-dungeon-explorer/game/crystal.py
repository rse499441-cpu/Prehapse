from __future__ import annotations

import random
from dataclasses import dataclass

from .models import MERCHANT_CHARM_STATS, Player
from .equipment import register_equipment


CRYSTAL_EXCHANGE_COST = 3
CRYSTAL_RARITY_WEIGHTS = {
    "优良": 45,
    "稀有": 35,
    "黄金": 17,
    "传说": 3,
}
CRYSTAL_RARITY_EMOJI = {
    "优良": "🟢",
    "稀有": "🔵",
    "黄金": "🟡",
    "传说": "🟣",
}


@dataclass(frozen=True)
class CrystalReward:
    key: str
    name: str
    rarity: str
    category: str
    attack: int = 0
    defense: int = 0
    agility: int = 0
    luck: int = 0

    @property
    def stat_text(self) -> str:
        stats = []
        if self.attack:
            stats.append(f"攻击 +{self.attack}")
        if self.defense:
            stats.append(f"防御 +{self.defense}")
        if self.agility:
            stats.append(f"敏捷 +{self.agility}")
        if self.luck:
            stats.append(f"幸运 +{self.luck}")
        return "｜".join(stats)


REWARD_PREFIXES = [
    "星屑", "苍月", "夜雾", "晨曦", "霜花", "流火", "青岚", "紫电", "银羽", "绯樱",
    "幽灯", "晶歌", "潮汐", "熔心", "墨影", "齿轮", "极光", "月庭", "龙息", "天穹",
]
WEAPON_FORMS = ["短刃", "长剑", "弯刀", "法杖", "战锤", "月轮", "双剑", "魔枪"]
ARMOR_FORMS = ["旅袍", "斗篷", "轻甲", "法衣", "披风", "礼装", "战裙", "护衣"]
CHARM_FORMS = ["星石", "魔眼", "护符", "月坠", "羽印", "灵铃", "秘钥", "晶核"]


def _build_rarity_pool(
    rarity: str,
    count: int,
    attack_base: int,
    defense_base: int,
    agility_base: int,
    luck_base: int,
) -> list[CrystalReward]:
    rewards = []
    forms = {"武器": WEAPON_FORMS, "护具": ARMOR_FORMS, "护符": CHARM_FORMS}
    categories = ("武器", "护具", "护符")
    rarity_titles = {"优良": "", "稀有": "秘银·", "黄金": "辉耀·"}
    for index in range(count):
        category = categories[index % len(categories)]
        form_pool = forms[category]
        prefix = REWARD_PREFIXES[index % len(REWARD_PREFIXES)]
        form = form_pool[(index // len(REWARD_PREFIXES) + index) % len(form_pool)]
        name = f"{rarity_titles[rarity]}{prefix}{form}·{index + 1:02d}"
        if category == "武器":
            reward = CrystalReward(
                f"{rarity.lower()}_{index:02d}", name, rarity, category,
                attack=attack_base + index % 4,
                agility=agility_base + index % 2,
                luck=luck_base + (index // 2) % 2,
            )
        elif category == "护具":
            reward = CrystalReward(
                f"{rarity.lower()}_{index:02d}", name, rarity, category,
                defense=defense_base + index % 4,
                agility=agility_base + index % 2,
                luck=luck_base + (index // 2) % 2,
            )
        else:
            # 水晶护符不受数量衰减，按稀有度提供更高的永久属性。
            stat = index % 4
            charm_value = {"优良": 2, "稀有": 3, "黄金": 4}[rarity]
            reward = CrystalReward(
                f"{rarity.lower()}_{index:02d}", name, rarity, category,
                attack=charm_value if stat == 0 else 0,
                defense=charm_value if stat == 1 else 0,
                agility=charm_value if stat == 2 else 0,
                luck=charm_value if stat == 3 else 0,
            )
        rewards.append(reward)
    return rewards


CRYSTAL_REWARDS = (
    _build_rarity_pool("优良", 60, 17, 8, 2, 1)
    + _build_rarity_pool("稀有", 47, 22, 12, 3, 2)
    + _build_rarity_pool("黄金", 23, 28, 17, 4, 4)
    + [
    CrystalReward("legend_blade", "永夜星穹", "传说", "武器", attack=36, agility=6, luck=6),
    CrystalReward("legend_robe", "创世星海圣衣", "传说", "护具", defense=23, agility=6, luck=7),
    CrystalReward("legend_charm", "女神的第三颗星", "传说", "护符", attack=4, defense=4, luck=4),
    CrystalReward("legend_staff", "时空女巫权杖", "传说", "武器", attack=35, agility=5, luck=8),
    ]
)


def crystal_charm_values_text(player: Player) -> str:
    return (
        f"攻击 +{player.crystal_charm_bonus('attack')}｜"
        f"防御 +{player.crystal_charm_bonus('defense')}｜"
        f"敏捷 +{player.crystal_charm_bonus('agility')}｜"
        f"幸运 +{player.crystal_charm_bonus('luck')}"
    )


def exchange_crystals(
    player: Player,
    rng: random.Random | None = None,
    count: int = 1,
) -> tuple[bool, str, list[CrystalReward]]:
    if count not in {1, 5, 10}:
        return False, "每次只能选择砸 1 次、5 次或 10 次。", []
    total_cost = CRYSTAL_EXCHANGE_COST * count
    if player.crystals < total_cost:
        return (
            False,
            f"水晶不足：砸 **{count} 次**需要 **{total_cost} 枚**，"
            f"你目前只有 **{player.crystals} 枚**。",
            [],
        )
    roller = rng or random.SystemRandom()
    rewards = []
    result_lines = []
    player.crystals -= total_cost
    for index in range(1, count + 1):
        rarity = roller.choices(
            list(CRYSTAL_RARITY_WEIGHTS),
            weights=list(CRYSTAL_RARITY_WEIGHTS.values()),
            k=1,
        )[0]
        reward = roller.choice([item for item in CRYSTAL_REWARDS if item.rarity == rarity])
        rewards.append(reward)
        if reward.category in {"武器", "护具"}:
            player.crystal_equipment[reward.key] = (
                player.crystal_equipment.get(reward.key, 0) + 1
            )
            register_equipment(
                player,
                reward.name,
                reward.category,
                rarity=reward.rarity,
                attack=reward.attack,
                defense=reward.defense,
                agility=reward.agility,
                luck=reward.luck,
            )
        else:
            player.crystal_charm_draw_count = max(
                0, int(player.crystal_charm_draw_count)
            ) + 1
            for stat in MERCHANT_CHARM_STATS:
                base_value = int(getattr(reward, stat))
                if base_value <= 0:
                    continue
                player.crystal_charm_stat_counts[stat] = max(
                    0, int(player.crystal_charm_stat_counts.get(stat, 0))
                ) + 1
                bonus_key = f"crystal_{stat}_bonus"
                setattr(
                    player,
                    bonus_key,
                    round(
                        float(getattr(player, bonus_key))
                        + base_value,
                        2,
                    ),
                )
        emoji = CRYSTAL_RARITY_EMOJI[rarity]
        result_lines.append(
            f"`{index:02d}` {emoji} **[{rarity}] {reward.name}**"
            f"｜{reward.category}｜{reward.stat_text}"
        )
    return (
        True,
        "\n".join(result_lines)
        + f"\n\n已消耗 **{total_cost} 枚魔法水晶**，完成 **{count} 次**兑换。",
        rewards,
    )


def equip_crystal_reward(player: Player, reward_key: str) -> tuple[bool, str]:
    reward = next((item for item in CRYSTAL_REWARDS if item.key == reward_key), None)
    if not reward or reward.category not in {"武器", "护具"}:
        return False, "没有找到这件秘藏装备。"
    if player.crystal_equipment.get(reward_key, 0) <= 0:
        return False, "这件装备不在你的秘藏装备栏中。"
    if reward.category == "武器":
        player.weapon = reward.name
        player.weapon_attack = reward.attack
        player.weapon_agility = reward.agility
        player.weapon_luck = reward.luck
        return True, f"已装备 **[{reward.rarity}] {reward.name}**｜{reward.stat_text}"
    player.clothing = reward.name
    player.clothing_defense = reward.defense
    player.clothing_agility = reward.agility
    player.clothing_luck = reward.luck
    return True, f"已穿戴 **[{reward.rarity}] {reward.name}**｜{reward.stat_text}"
