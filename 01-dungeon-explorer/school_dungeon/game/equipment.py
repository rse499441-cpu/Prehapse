from __future__ import annotations

from .formatting import format_number

from .models import Player


EQUIPMENT_NAME_RULES_VERSION = 1

EQUIPMENT_RENAMES = {
    "铁制短剑": "铁制直尺",
    "猎风弯刀": "田径接力棒",
    "蓝晶法刃": "蓝晶三角尺",
    "黄金狮心剑": "黄铜教鞭",
    "月蚀星辉刃": "星轨圆规",
    "老板娘的平底锅": "食堂阿姨的平底锅",
    "青铜阔剑": "裁纸刀",
    "银羽刺剑": "银羽钢笔",
    "余烬战锤": "试剂搅棒",
    "潮音法杖": "音乐指挥棒",
    "发条破甲枪": "发条订书机",
    "霜牙双刃": "铁制剪刀",
    "日轮圣剑": "灿金教鞭",
    "虚空咏叹": "三好学生铭牌",
    "加厚皮甲": "厚校服外套",
    "轻羽旅装": "轻羽运动服",
    "晶纹长袍": "晶纹实验服",
    "黄金守卫甲": "暗纹风纪制服",
    "幼龙鳞披风": "龙纹毕业礼装",
    "小小秦的围裙": "食堂限定围裙",
    "轻环锁甲": "轻环防护背心",
    "苔纹游侠衣": "苔纹园艺服",
    "潮汐祭衣": "普通泳衣",
    "余烬守卫甲": "实验防护服",
    "钟摆机关甲": "机巧实验服",
    "霜冠王披": "霜冠冬季披风",
    "日耀圣堂甲": "日耀礼仪西装",
    "虚空星幕": "天文星幕礼装",
    "旅行者铁剑": "老式金属直尺",
    "风痕弯刀": "美工刀",
    "硬皮旅行甲": "耐磨校服外套",
    "旧符文披风": "二手校服外套",
}

MERCHANT_VARIANT_RENAMES = {
    ("潮音法杖", 15, 0, 0, 2): "指挥棒",
    ("发条破甲枪", 17, 0, 2, 0): "订书机",
    ("霜牙双刃", 20, 0, 3, 0): "剪刀",
    ("潮汐祭衣", 0, 7, 0, 2): "游泳队服",
    ("钟摆机关甲", 0, 10, 2, 0): "化学实验服",
    ("霜冠王披", 0, 13, 0, 3): "冬季加厚校服",
}


def _renamed_equipment(name: str, item: dict[str, object]) -> str:
    stats_key = (
        name,
        int(item.get("attack", 0)),
        int(item.get("defense", 0)),
        int(item.get("agility", 0)),
        int(item.get("luck", 0)),
    )
    return MERCHANT_VARIANT_RENAMES.get(stats_key, EQUIPMENT_RENAMES.get(name, name))


def migrate_equipment_names(player: Player) -> bool:
    """永久迁移旧装备名；属性相同的历史重名装备归入金币商店版本。"""
    changed = int(getattr(player, "equipment_name_rules_version", 0)) < EQUIPMENT_NAME_RULES_VERSION
    source = player.equipment_inventory if isinstance(player.equipment_inventory, dict) else {}
    migrated: dict[str, dict[str, object]] = {}
    for name, raw_item in source.items():
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        new_name = _renamed_equipment(str(name), item)
        if new_name == name:
            item["name"] = new_name
            migrated[new_name] = item
    for name, raw_item in source.items():
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        new_name = _renamed_equipment(str(name), item)
        item["name"] = new_name
        migrated.setdefault(new_name, item)
        changed = changed or new_name != name or item.get("name") != raw_item.get("name")

    weapon_item = {
        "attack": player.weapon_attack,
        "defense": 0,
        "agility": player.weapon_agility,
        "luck": player.weapon_luck,
    }
    clothing_item = {
        "attack": 0,
        "defense": player.clothing_defense,
        "agility": player.clothing_agility,
        "luck": player.clothing_luck,
    }
    new_weapon = _renamed_equipment(player.weapon, weapon_item)
    new_clothing = _renamed_equipment(player.clothing, clothing_item)
    changed = changed or new_weapon != player.weapon or new_clothing != player.clothing
    player.weapon = new_weapon
    player.clothing = new_clothing
    player.equipment_inventory = migrated
    player.equipment_name_rules_version = EQUIPMENT_NAME_RULES_VERSION
    return changed


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
    migrate_equipment_names(player)
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
