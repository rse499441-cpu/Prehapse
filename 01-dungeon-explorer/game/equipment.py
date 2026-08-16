from __future__ import annotations

from .formatting import format_number

from .models import Player


def register_equipment(
    player: Player,
    name: str,
    category: str,
    *,
    rarity: str = "普通",
    attack: int = 0,
    defense: int = 0,
    agility: int = 0,
    luck: int = 0,
) -> None:
    """装备按名称去重；重复取得同名装备不会产生重复选项。"""
    player.equipment_inventory[name] = {
        "name": name,
        "category": category,
        "rarity": rarity,
        "attack": int(attack),
        "defense": int(defense),
        "agility": int(agility),
        "luck": int(luck),
    }


def ensure_equipment_inventory(player: Player) -> None:
    # 只迁移尚未入库的旧装备，避免把已收藏装备的原稀有度覆盖成“普通”。
    if player.weapon not in player.equipment_inventory:
        register_equipment(
            player,
            player.weapon,
            "武器",
            attack=player.weapon_attack,
            agility=player.weapon_agility,
            luck=player.weapon_luck,
        )
    if player.clothing not in player.equipment_inventory:
        register_equipment(
            player,
            player.clothing,
            "护具",
            defense=player.clothing_defense,
            agility=player.clothing_agility,
            luck=player.clothing_luck,
        )


def equip_from_inventory(player: Player, name: str) -> tuple[bool, str]:
    item = player.equipment_inventory.get(name)
    if not item:
        return False, "装备库里没有找到这件装备。"
    if item["category"] == "武器":
        player.weapon = name
        player.weapon_attack = item["attack"]
        player.weapon_agility = item["agility"]
        player.weapon_luck = item["luck"]
        return True, (
            f"已装备 **[{item['rarity']}] {name}**｜攻击 +{format_number(item['attack'])}｜"
            f"敏捷 +{format_number(item['agility'])}｜幸运 +{format_number(item['luck'])}"
        )
    player.clothing = name
    player.clothing_defense = item["defense"]
    player.clothing_agility = item["agility"]
    player.clothing_luck = item["luck"]
    return True, (
        f"已穿戴 **[{item['rarity']}] {name}**｜防御 +{format_number(item['defense'])}｜"
        f"敏捷 +{format_number(item['agility'])}｜幸运 +{format_number(item['luck'])}"
    )
