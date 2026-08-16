from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Player
from .equipment import register_equipment


@dataclass(frozen=True)
class ShopItem:
    key: str
    name: str
    category: str
    rarity: str
    price: int
    attack: int = 0
    defense: int = 0
    agility: int = 0
    luck: int = 0
    effect: str = ""

    @property
    def stat_text(self) -> str:
        if self.category == "武器":
            return f"攻击 +{self.attack}｜敏捷 +{self.agility}｜幸运 +{self.luck}"
        if self.category == "护具":
            return f"防御 +{self.defense}｜敏捷 +{self.agility}｜幸运 +{self.luck}"
        return self.effect


RARITY_EMOJI = {
    "普通": "⚪",
    "优良": "🟢",
    "稀有": "🔵",
    "黄金": "🟡",
    "传说": "🟣",
}


WEAPONS = [
    ShopItem("w_iron", "铁制短剑", "武器", "普通", 180, attack=7),
    ShopItem("w_hunter", "猎风弯刀", "武器", "优良", 420, attack=10, agility=2),
    ShopItem("w_crystal", "蓝晶法刃", "武器", "稀有", 850, attack=15, luck=2),
    ShopItem("w_gold", "黄金狮心剑", "武器", "黄金", 1650, attack=21, agility=2, luck=3),
    ShopItem("w_moon", "月蚀星辉刃", "武器", "传说", 3600, attack=30, agility=4, luck=5),
    ShopItem("w_pan", "老板娘的平底锅", "武器", "稀有", 980, attack=17, agility=1, luck=4),
    ShopItem("w_bronze", "青铜阔剑", "武器", "普通", 230, attack=8),
    ShopItem("w_rapier", "银羽刺剑", "武器", "优良", 510, attack=11, agility=3),
    ShopItem("w_ember", "余烬战锤", "武器", "优良", 560, attack=13, agility=1),
    ShopItem("w_tide", "潮音法杖", "武器", "稀有", 920, attack=16, luck=4),
    ShopItem("w_gear", "发条破甲枪", "武器", "稀有", 1080, attack=18, agility=3),
    ShopItem("w_frost", "霜牙双刃", "武器", "黄金", 1780, attack=23, agility=4, luck=2),
    ShopItem("w_sun", "日轮圣剑", "武器", "黄金", 1950, attack=25, agility=2, luck=4),
    ShopItem("w_void", "虚空咏叹", "武器", "传说", 4200, attack=34, agility=5, luck=6),
]

ARMORS = [
    ShopItem("a_leather", "加厚皮甲", "护具", "普通", 160, defense=3, agility=1),
    ShopItem("a_scout", "轻羽旅装", "护具", "优良", 390, defense=4, agility=4),
    ShopItem("a_crystal", "晶纹长袍", "护具", "稀有", 820, defense=7, luck=3),
    ShopItem("a_gold", "黄金守卫甲", "护具", "黄金", 1550, defense=12, agility=1, luck=2),
    ShopItem("a_dragon", "幼龙鳞披风", "护具", "传说", 3400, defense=17, agility=4, luck=4),
    ShopItem("a_apron", "小小秦的围裙", "护具", "稀有", 920, defense=8, agility=2, luck=5),
    ShopItem("a_chain", "轻环锁甲", "护具", "普通", 240, defense=4),
    ShopItem("a_moss", "苔纹游侠衣", "护具", "优良", 480, defense=5, agility=3),
    ShopItem("a_wave", "潮汐祭衣", "护具", "优良", 540, defense=6, luck=3),
    ShopItem("a_ember", "余烬守卫甲", "护具", "稀有", 960, defense=9, agility=1, luck=2),
    ShopItem("a_clock", "钟摆机关甲", "护具", "稀有", 1120, defense=10, agility=3),
    ShopItem("a_frost", "霜冠王披", "护具", "黄金", 1820, defense=14, agility=3, luck=3),
    ShopItem("a_sun", "日耀圣堂甲", "护具", "黄金", 2050, defense=15, agility=2, luck=4),
    ShopItem("a_void", "虚空星幕", "护具", "传说", 4100, defense=21, agility=5, luck=6),
]

CONSUMABLES = [
    ShopItem("c_heal", "治疗药水", "道具", "普通", 45, effect="恢复 35 点体力"),
    ShopItem("c_mana", "魔力药水", "道具", "普通", 55, effect="恢复 25 点魔力"),
    ShopItem("c_energy", "精力药水", "道具", "优良", 70, effect="恢复 30 点精力"),
    ShopItem("c_charm", "幸运护符", "道具", "稀有", 180, effect="用于稀有事件与委托"),
    ShopItem("c_map", "空白藏宝图", "道具", "优良", 130, effect="可供部分随机事件使用"),
    ShopItem("c_greater_heal", "强效治疗药水", "道具", "优良", 110, effect="恢复 60 点体力"),
    ShopItem("c_greater_mana", "强效魔力药水", "道具", "优良", 125, effect="恢复 50 点魔力"),
    ShopItem("c_greater_energy", "强效精力药水", "道具", "稀有", 150, effect="恢复 60 点精力"),
]


def daily_stock(date_key: str) -> list[ShopItem]:
    rng = random.Random(f"dungeon-gold-shop:{date_key}:v2-expanded")
    return rng.sample(WEAPONS, 4) + rng.sample(ARMORS, 4) + rng.sample(CONSUMABLES, 4)


def boss_equipment_drop(
    floor: int,
    rng: random.Random,
) -> ShopItem:
    rarity_weights = (
        {"普通": 60, "优良": 40} if floor <= 20
        else {"普通": 35, "优良": 45, "稀有": 20} if floor <= 50
        else {"优良": 50, "稀有": 40, "黄金": 10} if floor <= 80
        else {"稀有": 65, "黄金": 32, "传说": 3}
    )
    rarity = rng.choices(
        list(rarity_weights),
        weights=list(rarity_weights.values()),
        k=1,
    )[0]
    pool = [item for item in WEAPONS + ARMORS if item.rarity == rarity]
    return rng.choice(pool)


def purchase(player: Player, item: ShopItem) -> tuple[bool, str]:
    if player.is_adventuring:
        return False, "冒险途中无法使用金币商城。请先结束本次冒险。"
    if player.gold < item.price:
        return False, f"金币不足：**{item.name}** 需要 {item.price} 金币，你只有 {player.gold}。"
    player.gold -= item.price
    if item.category == "武器":
        register_equipment(
            player, item.name, "武器", rarity=item.rarity,
            attack=item.attack, agility=item.agility, luck=item.luck,
        )
        player.weapon = item.name
        player.weapon_attack = item.attack
        player.weapon_agility = item.agility
        player.weapon_luck = item.luck
        return True, f"购买并装备 **{item.name}**！{item.stat_text}"
    if item.category == "护具":
        register_equipment(
            player, item.name, "护具", rarity=item.rarity,
            defense=item.defense, agility=item.agility, luck=item.luck,
        )
        player.clothing = item.name
        player.clothing_defense = item.defense
        player.clothing_agility = item.agility
        player.clothing_luck = item.luck
        return True, f"购买并穿上 **{item.name}**！{item.stat_text}"
    player.consumables[item.name] = player.consumables.get(item.name, 0) + 1
    return True, f"购买 **{item.name} ×1**！{item.effect}"
