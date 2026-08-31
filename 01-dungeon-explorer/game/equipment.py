from __future__ import annotations

from .formatting import format_number

from .models import Player


EQUIPMENT_NAME_RULES_VERSION = 2

EQUIPMENT_RENAMES = {
    "铁制直尺": "铁制短剑",
    "田径接力棒": "猎风弯刀",
    "蓝晶三角尺": "蓝晶法刃",
    "黄铜教鞭": "黄金狮心剑",
    "星轨圆规": "月蚀星辉刃",
    "食堂阿姨的平底锅": "老板娘的平底锅",
    "裁纸刀": "青铜阔剑",
    "银羽钢笔": "银羽刺剑",
    "试剂搅棒": "余烬战锤",
    "音乐指挥棒": "潮音法杖",
    "发条订书机": "发条破甲枪",
    "铁制剪刀": "霜牙双刃",
    "灿金教鞭": "日轮圣剑",
    "三好学生铭牌": "虚空咏叹",
    "厚校服外套": "加厚皮甲",
    "轻羽运动服": "轻羽旅装",
    "晶纹实验服": "晶纹长袍",
    "暗纹风纪制服": "黄金守卫甲",
    "龙纹毕业礼装": "幼龙鳞披风",
    "食堂限定围裙": "小小秦的围裙",
    "轻环防护背心": "轻环锁甲",
    "苔纹园艺服": "苔纹游侠衣",
    "普通泳衣": "潮汐祭衣",
    "实验防护服": "余烬守卫甲",
    "机巧实验服": "钟摆机关甲",
    "霜冠冬季披风": "霜冠王披",
    "日耀礼仪西装": "日耀圣堂甲",
    "天文星幕礼装": "虚空星幕",
    "老式金属直尺": "旅行者铁剑",
    "美工刀": "风痕弯刀",
    "实验锤": "旅行商人·余烬战锤",
    "指挥棒": "旅行商人·潮音法杖",
    "订书机": "旅行商人·发条破甲枪",
    "剪刀": "旅行商人·霜牙双刃",
    "耐磨校服外套": "硬皮旅行甲",
    "二手校服外套": "旧符文披风",
    "园艺服": "苔纹游侠衣",
    "游泳队服": "旅行商人·潮汐祭衣",
    "化学实验服": "旅行商人·钟摆机关甲",
    "冬季加厚校服": "旅行商人·霜冠王披",
}

MERCHANT_VARIANT_RENAMES = {}


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
    """把曾被学园化的地下城一装备恢复为独立的奇幻装备名称。"""
    changed = int(getattr(player, "equipment_name_rules_version", 0)) < EQUIPMENT_NAME_RULES_VERSION
    source = player.equipment_inventory if isinstance(player.equipment_inventory, dict) else {}
    migrated: dict[str, dict[str, object]] = {}

    # 先保留已经采用新名称的物品，再补入旧名称迁移结果，避免覆盖新物品。
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
