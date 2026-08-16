from __future__ import annotations

import random
import math
from dataclasses import dataclass

from .formatting import format_number
from .models import Enemy, Player, merchant_charm_bonuses, merchant_charm_rate, merchant_charm_total
from .equipment import register_equipment


@dataclass
class GameResult:
    title: str
    message: str
    danger: bool = False
    death: bool = False
    completed: bool = False
    escaped: bool = False
    rescue_requested: bool = False
    role_mention: str | None = None
    awarded_title: str | None = None


class GameEngine:
    EVENTS = (["monster"] * 36 + ["chest"] * 15 + ["mimic"] * 9 +
              ["trap"] * 13 + ["recovery"] * 6 + ["shop"] * 7 +
              ["fairy"] * 5 + ["mystery"] * 6 + ["treasure_map"] * 5 +
              ["trapped_beast"] * 5 + ["wishing_well"] * 4 + ["empty"] * 8)
    MAGIC_SKILLS = {
        "minor": ("✨ 星火弹", 6, 1.20),
        "medium": ("🔷 月辉矢", 12, 1.50),
        "major": ("🌠 奥术流星", 22, 1.85),
    }
    MAJOR_BOSS_NAMES = {
        10: "黏液大公·噗叽伯爵",
        20: "晶甲女王·辉钻",
        30: "万菌之母·绵绵菇",
        40: "潮汐圣兽·波波鲁",
        50: "熔炉总管·赤锤",
        60: "禁书馆长·墨菲斯",
        70: "永动机皇·咔嗒三世",
        80: "极星冰帝·企鹅诺尔",
        90: "月庭守护者·露娜兔",
        100: "幽灯王座·小小暗王",
    }
    MERCHANT_ITEMS = {
        "healing_potion": ("治疗药水", "药剂", "恢复 35 点体力", 25, {}),
        "mana_potion": ("魔力药水", "药剂", "恢复 25 点魔力", 30, {}),
        "energy_potion": ("精力药水", "药剂", "恢复 30 点精力", 35, {}),
        "greater_energy_potion": ("强效精力药水", "药剂", "恢复 60 点精力（20层后出现）", 85, {}),
        "greater_healing_potion": ("强效治疗药水", "药剂", "恢复 60 点体力", 58, {}),
        "greater_mana_potion": ("强效魔力药水", "药剂", "恢复 50 点魔力", 72, {}),
        "guard_charm": ("石纹护符", "护符", "永久防御 +1", 115, {"defense": 1}),
        "lucky_charm": ("四叶护符", "护符", "永久幸运 +1", 135, {"luck": 1}),
        "swift_charm": ("风羽护符", "护符", "永久敏捷 +1", 125, {"agility": 1}),
        "fang_charm": ("赤牙护符", "护符", "永久攻击 +1", 155, {"attack": 1}),
        "iron_sword": ("旅行者铁剑", "武器", "攻击 +8", 210, {"attack": 8}),
        "wind_blade": ("风痕弯刀", "武器", "攻击 +11｜敏捷 +1", 390, {"attack": 11, "agility": 1}),
        "ember_hammer": ("余烬战锤", "武器", "攻击 +13｜敏捷 +1", 460, {"attack": 13, "agility": 1}),
        "tide_staff": ("潮音法杖", "武器", "攻击 +15｜幸运 +2", 590, {"attack": 15, "luck": 2}),
        "gear_spear": ("发条破甲枪", "武器", "攻击 +17｜敏捷 +2", 760, {"attack": 17, "agility": 2}),
        "frost_blades": ("霜牙双刃", "武器", "攻击 +20｜敏捷 +3", 980, {"attack": 20, "agility": 3}),
        "leather_armor": ("硬皮旅行甲", "装备", "防御 +4｜敏捷 +1", 195, {"defense": 4, "agility": 1}),
        "rune_cloak": ("旧符文披风", "装备", "防御 +6｜幸运 +1", 370, {"defense": 6, "luck": 1}),
        "moss_coat": ("苔纹游侠衣", "装备", "防御 +5｜敏捷 +3", 420, {"defense": 5, "agility": 3}),
        "tide_robe": ("潮汐祭衣", "装备", "防御 +7｜幸运 +2", 560, {"defense": 7, "luck": 2}),
        "clock_armor": ("钟摆机关甲", "装备", "防御 +10｜敏捷 +2", 760, {"defense": 10, "agility": 2}),
        "frost_cape": ("霜冠王披", "装备", "防御 +13｜幸运 +3", 990, {"defense": 13, "luck": 3}),
    }
    MERCHANT_POOLS = {
        "药剂": [
            "healing_potion", "mana_potion", "energy_potion",
            "greater_healing_potion", "greater_mana_potion", "greater_energy_potion",
        ],
        "护符": ["guard_charm", "lucky_charm", "swift_charm", "fang_charm"],
        "武器": [
            "iron_sword", "wind_blade", "ember_hammer", "tide_staff",
            "gear_spear", "frost_blades",
        ],
        "装备": [
            "leather_armor", "rune_cloak", "moss_coat", "tide_robe",
            "clock_armor", "frost_cape",
        ],
    }

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def required_steps(self, floor: int) -> int:
        bonus = min(12, (floor - 1) // 10 * 2)
        return self.rng.randint(12 + bonus, 24 + bonus)

    @staticmethod
    def event_damage(player: Player, raw_damage: int) -> int:
        """敏捷与防御共同减少探索事件造成的生命或魔力损失。"""
        return round(max(1, raw_damage - player.agility // 2 - player.defense // 3), 2)

    @staticmethod
    def physical_damage(raw_damage: int, defense: int | float) -> int | float:
        """防御只能减伤：物理攻击至少保留 15% 原始伤害。"""
        return round(max(1, math.ceil(raw_damage * 0.15), raw_damage - defense), 2)

    @staticmethod
    def star_multipliers(star: int) -> tuple[float, float, float]:
        star = max(0, star)
        return 1 + 0.50 * star, 1 + 0.30 * star, 1 + 0.15 * star

    @staticmethod
    def chest_chance(player: Player) -> float:
        """宝箱类事件成为真宝箱的概率：基础 62.5%，每点幸运 +1.5%。"""
        return min(0.90, 0.625 + player.luck * 0.015)

    @staticmethod
    def raccoon_chase_chance(player: Player) -> float:
        """发现并追上偷钱浣熊的概率：基础 20%，每点敏捷 +5%，最高 50%。"""
        return min(0.50, 0.20 + player.agility * 0.05)

    @staticmethod
    def blended_gold(floor: int, old_value: int, current_value: int) -> int:
        """旧版占比先降至 50 层的 1/3，再于 100 层降至 1/5。"""
        floor = max(1, min(100, floor))
        if floor <= 50:
            old_weight = 0.5 - ((floor - 1) / 49) * (1 / 6)
        else:
            old_weight = (1 / 3) - ((floor - 50) / 50) * (2 / 15)
        return max(0, round(old_value * old_weight + current_value * (1 - old_weight)))

    @staticmethod
    def crystal_drop_chance(
        floor: int,
        base_chance: float,
        fortune_growth: float = 0.0,
    ) -> float:
        """1—30 层提供 1.5 倍概率；精灵水晶再受当日运势比例增长。"""
        floor_multiplier = 1.5 if floor <= 30 else 1.0
        return min(1.0, base_chance * floor_multiplier * (1 + max(0.0, fortune_growth)))

    @staticmethod
    def merchant_charm_rate(charm_number: int) -> float:
        return merchant_charm_rate(charm_number)

    @classmethod
    def merchant_refresh_cost(cls, floor: int) -> int:
        """与最高阶药剂同公式：基础价 85 + 每十层 5 金币。"""
        scale = 1 + (max(1, floor) - 1) // 10
        return 85 + scale * 5

    @staticmethod
    def deposit_gold(player: Player, amount: int) -> GameResult:
        if player.is_adventuring:
            return GameResult("无法储值", "冒险途中无法使用储值商人，请先返回酒馆。")
        if amount <= 0:
            return GameResult("数量无效", "储存数量必须大于 0。")
        if player.gold < amount:
            return GameResult("金币不足", f"你身上只有 **{player.gold} 金币**。")
        player.gold -= amount
        player.stored_gold += amount
        return GameResult("🪙 储存成功", f"已存入 **{amount} 金币**。")

    @staticmethod
    def withdraw_gold(player: Player, amount: int) -> GameResult:
        if player.is_adventuring:
            return GameResult("无法取款", "冒险途中无法使用储值商人，请先返回酒馆。")
        if amount <= 0:
            return GameResult("数量无效", "取出数量必须大于 0。")
        if player.stored_gold < amount:
            return GameResult("余额不足", f"储值商人处只有 **{player.stored_gold} 金币**。")
        player.stored_gold -= amount
        player.gold += amount
        return GameResult("🪙 取出成功", f"已取出 **{amount} 金币**。")

    @staticmethod
    def mimic_avoid_chance(player: Player) -> float:
        """离开可疑宝箱时避开宝箱怪的概率：基础 70%，每点敏捷 +2%，最高 95%。"""
        return min(0.95, 0.70 + player.agility * 0.02)

    @staticmethod
    def adventurer_title(completion_count: int) -> str:
        titles = {
            1: "❄️ 一星冒险者",
            2: "❄️ 二星冒险者",
            3: "❄️ 三星冒险者",
            4: "❄️ 四星冒险者",
        }
        return titles.get(max(1, completion_count), "❄️ 初级冒险者")

    def ensure_floor(self, player: Player) -> None:
        if player.required_steps <= 0:
            player.required_steps = self.required_steps(player.floor)
        if player.enemy and player.enemy.boss_kind == "大 Boss":
            if player.enemy.name in self.MAJOR_BOSS_NAMES.values():
                return
            if player.floor % 10 != 0:
                player.enemy = self._make_boss(player.floor, player.completion_count)
            else:
                expected = self._make_boss(player.floor, player.completion_count)
                if player.enemy.name != expected.name:
                    player.enemy.name = expected.name
                    player.enemy.catchphrase = expected.catchphrase
                    player.enemy.level = expected.level

    def explore(self, player: Player) -> GameResult:
        self.ensure_floor(player)
        if player.enemy:
            return GameResult("无法继续", "必须先结束当前战斗。", True)
        if player.pending_event:
            return GameResult("等待交互", "请先处理眼前的事件。")
        if player.energy < 3:
            return GameResult("精力不足", "探索需要 3 点精力，请使用恢复道具。")
        player.energy -= 3
        player.steps += 1
        if player.steps >= player.required_steps:
            position = player.floor % 10
            if position == 0:
                player.enemy = self._make_boss(player.floor, player.completion_count)
                return GameResult("🔥 大 Boss 降临！", f"固定守层者 **{player.enemy.name}** 挡住了通往下一区域的道路！", True)
            if position in {5, 6, 7, 8} and self.rng.random() < 0.45:
                player.enemy = self._make_boss(player.floor, player.completion_count)
                return GameResult("⚠️ 小 Boss 随机出现！", f"**{player.enemy.name}** 闻讯赶来，决定亲自阻止你！", True)
            cleared = player.floor
            player.floor += 1
            player.steps = 0
            player.required_steps = self.required_steps(player.floor)
            return GameResult("🚪 找到下层入口", f"第 **{cleared} 层**探索完成，没有 Boss 出现。你进入了第 **{player.floor} 层**。")
        event = self.rng.choice(self.EVENTS)
        if event in {"chest", "mimic"}:
            event = "chest" if self.rng.random() < self.chest_chance(player) else "mimic"
        return getattr(self, f"_event_{event}")(player)

    def attack(
        self,
        player: Player,
        use_skill: bool = False,
        skill_tier: str | None = None,
    ) -> GameResult:
        enemy = player.enemy
        if not enemy:
            return GameResult("没有敌人", "当前没有可以攻击的目标。")
        if use_skill and skill_tier is None:
            skill_tier = "medium"
        skill = self.MAGIC_SKILLS.get(skill_tier) if skill_tier else None
        if skill and player.mp < skill[1]:
            return GameResult("魔力不足", f"释放 **{skill[0]}** 需要 {skill[1]} 点魔力。")
        base_min = 8 + player.level * 2
        base_max = 12 + player.level * 3
        base_damage = self.rng.randint(base_min, base_max)
        exceptional_chance = (0.08 if skill else 0.15) + min(0.15, player.luck * 0.005)
        exceptional = self.rng.random() < exceptional_chance
        if exceptional:
            base_damage = round(base_damage * 1.5)
        damage = round(base_damage + player.attack_bonus, 2)
        label = skill[0] if skill else "普通攻击"
        if skill:
            player.mp -= skill[1]
            damage = round(damage * skill[2], 2)
        shield_text = ""
        if enemy.shield_ratio > 0:
            blocked = int(damage * enemy.shield_ratio)
            damage = round(max(1, damage - blocked), 2)
            shield_text = f"，护盾抵消 **{blocked}**"
            enemy.shield_ratio = 0.0
        performance = "，触发 **超常发挥！**" if exceptional else ""
        formula = (
            f"（基础 {base_damage} + 武器 {player.weapon_attack}"
            f" + 百层祝福 {format_number(player.completion_bonus('attack'))}"
            f" + 商人护符 {format_number(player.merchant_charm_bonus('attack'))}"
            f" + 水晶护符 {format_number(player.crystal_charm_bonus('attack'))}）"
        )
        enemy.hp = max(0, enemy.hp - damage)
        if enemy.hp == 0:
            # 深层奖励线性缓升，不再直接乘楼层，避免金币失控。
            boss_bonus = 25 if enemy.boss_kind == "大 Boss" else 10 if enemy.boss_kind == "小 Boss" else 0
            current_gold = self.rng.randint(5, 10) + player.floor + boss_bonus
            old_gold = self.rng.randint(6, 12) * max(1, player.floor)
            reward_gold = self.blended_gold(player.floor, old_gold, current_gold)
            reward_gold = int(reward_gold * (1 + min(0.40, enemy.adventure_star * 0.08)))
            player.gold += reward_gold
            reclaimed_gold = max(0, enemy.stolen_gold)
            if reclaimed_gold:
                player.gold += reclaimed_gold
            bonus_drop = ""
            if self.rng.random() < min(0.35, player.luck * 0.015):
                item = self.rng.choice(("治疗药水", "魔力药水", "精力药水"))
                player.consumables[item] = player.consumables.get(item, 0) + 1
                bonus_drop = f"，幸运额外掉落 **{item} ×1**"
            equipment_drop = ""
            boss_drop_chance = (
                0.25 if enemy.boss_kind == "大 Boss"
                else 0.12 if enemy.boss_kind == "小 Boss"
                else 0.0
            )
            if self.rng.random() < boss_drop_chance:
                from .shop import boss_equipment_drop

                dropped = boss_equipment_drop(player.floor, self.rng)
                register_equipment(
                    player,
                    dropped.name,
                    dropped.category,
                    rarity=dropped.rarity,
                    attack=dropped.attack,
                    defense=dropped.defense,
                    agility=dropped.agility,
                    luck=dropped.luck,
                )
                equipment_drop = (
                    f"\n🎁 Boss 掉落：**[{dropped.rarity}] {dropped.name}**"
                    f"（{dropped.stat_text}），已放入装备库。"
                )
            exp = enemy.exp_reward
            player.enemy = None
            level_text = self._gain_exp(player, exp)
            progress = ""
            if enemy.boss_kind in {"小 Boss", "大 Boss"}:
                if player.floor < 100:
                    player.floor += 1
                    player.steps = 0
                    player.required_steps = self.required_steps(player.floor)
                    progress = f"\n通往第 {player.floor} 层的道路开启了。"
                else:
                    player.completion_count += 1
                    player.permanent_attack_bonus += 5
                    player.permanent_defense_bonus += 3
                    next_star = player.completion_count
                    player.level, player.exp = 1, 0
                    player.max_hp, player.max_mp, player.max_energy = 100, 50, 100
                    player.floor, player.steps = 1, 0
                    player.required_steps = self.required_steps(1)
                    player.hp, player.mp, player.energy = (
                        player.max_hp,
                        player.max_mp,
                        player.max_energy,
                    )
                    player.pending_event, player.in_adventure = None, False
                    player.gold_storage_available = True
                    awarded_title = self.adventurer_title(next_star)
                    return GameResult(
                        "❄️ 百层远征完成",
                        f"你以{label}造成 **{format_number(damage)}** 点伤害{performance} {formula}，"
                        f"击败 **{enemy.name}**！\n获得 {exp} 经验和 {reward_gold} 金币"
                        f"{bonus_drop}。{equipment_drop}{level_text}\n\n"
                        "你征服了幽灯岩窟第 **100 层**，获得称号身份组 "
                        f"**{awarded_title}**！\n"
                        "永久属性提升：⚔️ **攻击 +5**｜🛡️ **防御 +3**。\n"
                        f"下一轮远征提升为 **★{next_star}**；"
                        "等级和经验已重置，装备、收藏与永久属性保留。\n"
                        "风雪将你送回了冒险者酒馆。",
                        completed=True,
                        awarded_title=awarded_title,
                    )
            reclaimed_text = (
                f"\n💰 从浣熊的赃物袋中夺回了被偷走的 **{reclaimed_gold} 金币**！"
                if reclaimed_gold else ""
            )
            return GameResult("🎉 战斗胜利", f"你以{label}造成 **{format_number(damage)}** 点伤害{performance} {formula}，击败 **{enemy.name}**！"
                              f"\n获得 {exp} 经验和 {reward_gold} 金币{bonus_drop}。{reclaimed_text}"
                              f"{equipment_drop}{level_text}{progress}")
        if enemy.charged_spell:
            spell_result = self._cast_enemy_spell(player, enemy)
            if not player.is_alive:
                return self._die(player, spell_result)
            return GameResult(
                "🔮 敌方魔法发动！",
                f"你以{label}造成 **{format_number(damage)}** 点伤害{shield_text}{performance} {formula}；\n"
                f"{spell_result}",
                True,
            )

        spell_chance = (
            0.28 if enemy.boss_kind == "大 Boss"
            else 0.18 if enemy.boss_kind == "小 Boss"
            else 0.08 if enemy.floor >= 50
            else 0.0
        )
        if self.rng.random() < spell_chance:
            enemy.charged_spell = self._spell_name(enemy)
            return GameResult(
                "⚠️ 敌人正在咏唱！",
                f"你以{label}造成 **{format_number(damage)}** 点伤害{shield_text}{performance} {formula}。\n"
                f"**{enemy.name}** 正在准备 **{enemy.charged_spell}**；"
                "下一次行动将释放魔法！",
                True,
            )

        raw_incoming = self.rng.randint(max(1, enemy.attack - 3), enemy.attack + 3)
        incoming = self.physical_damage(raw_incoming, player.defense)
        crit_chance = min(
            0.25,
            (
                0.18 if enemy.boss_kind == "大 Boss"
                else 0.12 if enemy.boss_kind == "小 Boss"
                else 0.10 if enemy.boss_kind == "宝箱怪"
                else 0.05
            ) + enemy.adventure_star * 0.01,
        )
        critical = self.rng.random() < crit_chance
        if critical:
            incoming = max(1, math.ceil(incoming * 1.5))
        dodge_chance = min(0.35, player.agility * 0.015)
        if self.rng.random() < dodge_chance:
            return GameResult(
                "💨 灵巧闪避！",
                f"你以{label}造成 **{format_number(damage)}** 点伤害{performance} {formula}；"
                f"随后凭借 **{format_number(player.agility)} 点敏捷**躲开了 {enemy.name} 的反击！",
                True,
            )
        player.hp = round(max(0, player.hp - incoming), 2)
        if not player.is_alive:
            return self._die(player, f"你造成 {format_number(damage)} 点伤害，但被 **{enemy.name}** 击败。")
        return GameResult(
            "⚔️ 激烈战斗",
            f"你以{label}造成 **{format_number(damage)}** 点伤害{shield_text}{performance} {formula}；"
            f"{enemy.name} 反击造成 **{format_number(incoming)}** 点伤害"
            f"{'，触发 **暴击！**' if critical else ''}。",
            True,
        )

    @staticmethod
    def _spell_name(enemy: Enemy) -> str:
        zone = min(10, max(1, (enemy.floor + 9) // 10))
        spells = {
            1: "腐蚀酸雨",
            2: "晶甲结界",
            3: "噩梦孢子",
            4: "潮汐汲取",
            5: "熔炉灼光",
            6: "禁书封印",
            7: "永动连击",
            8: "极寒冻结",
            9: "月庭回响",
            10: "幽灯终焉",
        }
        return spells[zone]

    def _cast_enemy_spell(self, player: Player, enemy: Enemy) -> str:
        spell = enemy.charged_spell
        enemy.charged_spell = ""
        raw = max(1, enemy.attack)

        def magic_damage(multiplier: float, penetration: float = 0.65) -> int:
            base = max(1, int(raw * multiplier))
            reduced = base - int(player.defense * (1 - penetration))
            return max(math.ceil(base * 0.25), reduced)

        if spell == "晶甲结界":
            enemy.shield_ratio = 0.50
            return f"💎 **{enemy.name}** 展开晶甲结界，下一次受到的伤害减少 **50%**。"
        if spell == "潮汐汲取":
            drained = min(player.mp, 12 + enemy.adventure_star * 3)
            player.mp -= drained
            healed = min(enemy.max_hp - enemy.hp, max(1, drained * 2))
            enemy.hp += healed
            return f"🌊 **潮汐汲取**夺走 **{drained} 魔力**，并为敌人恢复 **{healed} 生命**。"
        if spell == "月庭回响":
            healed = min(enemy.max_hp - enemy.hp, max(1, enemy.max_hp // 8))
            enemy.hp += healed
            enemy.shield_ratio = 0.25
            return f"🌙 **月庭回响**恢复 **{healed} 生命**，并获得 **25% 护盾**。"
        if spell == "永动连击":
            hit = self.physical_damage(max(1, int(raw * 0.65)), player.defense)
            damage = hit * 2
            player.hp = round(max(0, player.hp - damage), 2)
            return f"⚙️ **永动连击**连续命中两次，共造成 **{damage} 点物理伤害**。"

        spell_data = {
            "腐蚀酸雨": (1.00, 0.70, 0, 0, "🧪"),
            "噩梦孢子": (0.80, 0.75, 0, 5, "🍄"),
            "熔炉灼光": (1.20, 0.80, 0, 4, "🔥"),
            "禁书封印": (0.75, 0.70, 16, 0, "📕"),
            "极寒冻结": (0.90, 0.75, 0, 10, "❄️"),
            "幽灯终焉": (1.45, 0.90, 10, 8, "👻"),
        }
        multiplier, penetration, mp_loss, energy_loss, emoji = spell_data.get(
            spell, (0.85, 0.65, 0, 0, "✨")
        )
        damage = magic_damage(multiplier, penetration)
        drained_mp = min(player.mp, mp_loss)
        drained_energy = min(player.energy, energy_loss)
        player.mp -= drained_mp
        player.energy -= drained_energy
        player.hp = round(max(0, player.hp - damage), 2)
        extras = []
        if drained_mp:
            extras.append(f"魔力 -{drained_mp}")
        if drained_energy:
            extras.append(f"精力 -{drained_energy}")
        extra_text = f"，{'、'.join(extras)}" if extras else ""
        return (
            f"{emoji} **{enemy.name}** 释放 **{spell}**，造成 **{damage} 点魔法伤害**"
            f"{extra_text}。魔法会穿透大部分防御。"
        )

    def interact_event(self, player: Player) -> GameResult:
        event = player.pending_event
        if not event:
            return GameResult("没有可交互事件", "眼前没有需要处理的物品。")
        if event == "merchant":
            return GameResult("🧳 旅行商人的菜单", "请从商品下拉菜单中选择要购买的物品。")
        if player.energy < 2:
            return GameResult("精力不足", "打开宝箱需要 2 点精力。")
        player.energy -= 2
        if event == "mimic":
            player.pending_event = None
            player.enemy = self._make_monster(
                player.floor, mimic=True, star=player.completion_count
            )
            return GameResult(
                "😈 你遇到了宝箱怪！",
                f"宝箱突然长出牙齿！**{player.enemy.name}** 扑了过来！",
                True,
            )
        if event == "fountain":
            player.pending_event = None
            hp = min(20 + player.floor // 2, player.max_hp - player.hp)
            mp = min(12 + player.floor // 4, player.max_mp - player.mp)
            energy = min(14, player.max_energy - player.energy)
            player.hp += hp
            player.mp += mp
            player.energy += energy
            return GameResult(
                "⛲ 泉水回应了你！",
                f"恢复 **{hp} 体力、{mp} 魔力、{energy} 精力**。",
            )
        if event == "fairy":
            player.pending_event = None
            item = "治疗药水"
            if player.consumables.get(item, 0) <= 0:
                return GameResult(
                    "🧚 精灵有点失望",
                    "你翻遍行囊也没有找到她需要的治疗药水。她挥挥手飞走了。",
                )
            player.consumables[item] -= 1
            reward_roll = self.rng.random()
            crystal_chance = self.crystal_drop_chance(
                player.floor, 0.08, player.daily_fortune_growth
            )
            if reward_roll < crystal_chance:
                player.crystals += 1
                reward = "极其稀有的 **魔法水晶 ×1**"
            elif reward_roll < 0.55 + crystal_chance - 0.08:
                exp = 35 + player.floor * 3
                reward = f"**{exp} 经验**"
                reward += self._gain_exp(player, exp)
            else:
                gold = self.blended_gold(
                    player.floor, 45 + player.floor * 8, 25 + player.floor * 2
                )
                player.gold += gold
                reward = f"**{gold} 金币**"
            return GameResult("🧚 精灵的谢礼", f"交出 **治疗药水 ×1**，获得{reward}。")
        if event == "mystery":
            player.pending_event = None
            outcome = self.rng.choice(("heal", "hurt", "battle", "gold"))
            if outcome == "heal":
                healed = min(30 + player.floor, player.max_hp - player.hp)
                player.hp += healed
                return GameResult("✨ 石像发出暖光", f"摸起来意外柔软，恢复 **{healed} 点体力**。")
            if outcome == "gold":
                gold = self.blended_gold(
                    player.floor, 20 + player.floor * 5, 12 + player.floor
                )
                player.gold += gold
                return GameResult("🪙 石像吐出金币", f"它打了个嗝，掉出 **{gold} 金币**。")
            if outcome == "battle":
                player.enemy = self._make_monster(
                    player.floor, star=player.completion_count
                )
                return GameResult("👾 石像叫来了守卫！", f"**{player.enemy.name}** 从暗门里冲了出来！", True)
            damage = self.event_damage(player, 12 + player.floor // 2)
            player.hp = round(max(0, player.hp - damage), 2)
            if not player.is_alive:
                return self._die(player, f"神秘石像咬了你一口，造成 {damage} 点伤害。")
            return GameResult("💥 石像咬了你一口", f"失去 **{damage} 点体力**。谁让你乱摸呢？", True)
        if event == "treasure_map":
            player.pending_event = None
            roll = self.rng.random()
            crystal_chance = self.crystal_drop_chance(
                player.floor, 0.03, player.daily_fortune_growth
            )
            if roll < crystal_chance:
                player.crystals += 1
                return GameResult("🔮 地图尽头的秘宝", "你找到了极其稀有的 **魔法水晶 ×1**！")
            if roll < 0.28 + crystal_chance - 0.03:
                player.enemy = self._make_monster(
                    player.floor, mimic=True, star=player.completion_count
                )
                return GameResult("😈 地图是宝箱怪的外卖单！", f"**{player.enemy.name}** 已经等候多时！", True)
            gold = self.blended_gold(
                player.floor,
                self.rng.randint(25, 55) * max(1, player.floor),
                self.rng.randint(20, 45) + player.floor * 3,
            )
            player.gold += gold
            return GameResult("🗺️ 找到地图宝藏！", f"绕了一点远路，最终挖出 **{gold} 金币**。")
        if event == "trapped_beast":
            player.pending_event = None
            roll = self.rng.random()
            if roll < 0.22:
                damage = self.event_damage(player, 8 + player.floor // 2)
                player.hp = round(max(0, player.hp - damage), 2)
                if not player.is_alive:
                    return self._die(player, f"受困妖兽惊慌反咬，造成 {damage} 点伤害。")
                return GameResult("🐾 妖兽受惊了！", f"它误咬了你一口，失去 **{damage} 点体力**，随后逃进黑暗。", True)
            if roll < 0.35:
                player.enemy = self._make_monster(
                    player.floor, star=player.completion_count
                )
                return GameResult("👾 捕兽夹的主人回来了！", f"**{player.enemy.name}** 把你当成了偷猎者！", True)
            item_pool = ["治疗药水", "魔力药水", "精力药水"]
            if player.floor >= 20:
                item_pool.append("强效精力药水")
            item = self.rng.choice(item_pool)
            player.consumables[item] = player.consumables.get(item, 0) + 1
            return GameResult("🐺 妖兽记住了你的气味", f"它叼来 **{item} ×1** 作为谢礼，然后摇着尾巴离开了。")
        if event == "wishing_well":
            player.pending_event = None
            cost = 15 + player.floor * 2
            if player.gold < cost:
                return GameResult("🪙 愿望没有回音", f"许愿需要投入 **{cost} 金币**，你的钱袋不够沉。")
            player.gold -= cost
            roll = self.rng.random()
            if roll < 0.12:
                player.consumables["幸运护符"] = player.consumables.get("幸运护符", 0) + 1
                return GameResult("🌟 愿望成真！", f"投入 {cost} 金币，井底浮出 **幸运护符 ×1**。")
            if roll < 0.62:
                exp = 25 + player.floor * 4
                level_text = self._gain_exp(player, exp)
                return GameResult("✨ 井水闪闪发光", f"投入 {cost} 金币，获得 **{exp} 经验**。{level_text}")
            return GameResult("🐸 井里只有青蛙", f"投入 {cost} 金币，一只青蛙认真地对你说了声“呱”。")
        player.pending_event = None
        luck_multiplier = 1 + min(0.5, player.luck * 0.03)
        old_gold = int(self.rng.randint(8, 20) * max(1, player.floor) * luck_multiplier)
        current_gold = int((self.rng.randint(6, 16) + player.floor * 2) * luck_multiplier)
        gold = self.blended_gold(player.floor, old_gold, current_gold)
        player.gold += gold
        extra = ""
        if self.rng.random() < min(0.65, 0.25 + player.luck * 0.02):
            player.consumables["治疗药水"] = player.consumables.get("治疗药水", 0) + 1
            extra = "，以及一瓶治疗药水"
        return GameResult("🎁 宝箱开启！", f"消耗 2 点精力，获得 **{gold} 金币**{extra}。")

    def decline_event(self, player: Player) -> GameResult:
        event = player.pending_event
        player.pending_event = None
        if event == "chest":
            return GameResult(
                "🚶 你离开了宝箱",
                "你压下好奇心，放弃宝箱里的奖励，安全地继续前进。",
            )
        if event == "mimic":
            avoid_chance = self.mimic_avoid_chance(player)
            if self.rng.random() < avoid_chance:
                return GameResult(
                    "🤫 你避开了宝箱怪",
                    f"你凭借 **{format_number(player.agility)} 点敏捷**悄悄后退；"
                    "那只可疑宝箱没有发现你，仍在原地耐心装死。",
                )
            player.enemy = self._make_monster(
                player.floor, mimic=True, star=player.completion_count
            )
            return GameResult(
                "😈 宝箱怪识破了你！",
                f"你刚转身，宝箱便张开大嘴扑来！"
                f"**{player.enemy.name}** 拦住了退路。",
                True,
            )
        if event == "fairy":
            return GameResult("👋 你婉拒了精灵", "精灵理解地点点头，留下几粒亮晶晶的粉末后飞走了。")
        if event == "mystery":
            return GameResult("🚶 你忍住了好奇心", "你没有乱摸来历不明的东西。今天也很稳健。")
        if event == "treasure_map":
            return GameResult("🗺️ 你收起了藏宝图", "这条岔路看起来不太可靠，你决定继续原本的路线。")
        if event == "trapped_beast":
            return GameResult("🐾 你没有靠近妖兽", "谨慎也许不够英雄，但通常比较长寿。")
        if event == "wishing_well":
            return GameResult("🪙 你保住了金币", "你没有向陌生的井投入辛苦赚来的钱。")
        if event == "merchant":
            player.merchant_stock = {}
            player.merchant_refreshes = 0
            return GameResult("🧳 离开旅行商店", "商人继续数着金币，目送你走远。")
        return GameResult("继续前进", "你没有与眼前的事物互动。")

    def _merchant_pool(self, category: str, floor: int) -> list[str]:
        pool = list(self.MERCHANT_POOLS[category])
        if category == "药剂" and floor < 20:
            pool.remove("greater_energy_potion")
        return pool

    def _merchant_restock_category(self, sold_out_category: str | None = None) -> str:
        if sold_out_category in {"武器", "装备"}:
            return self.rng.choices(
                ("药剂", "护符"), weights=(70, 30), k=1,
            )[0]
        return self.rng.choices(
            ("药剂", "护符", "装备"), weights=(60, 25, 15), k=1,
        )[0]

    def _roll_merchant_item(
        self,
        floor: int,
        category: str,
        excluded: set[str],
        opposite_of: str | None = None,
    ) -> str:
        if category == "药剂":
            pool = self._merchant_pool("药剂", floor)
        elif category == "护符":
            pool = list(self.MERCHANT_POOLS["护符"])
        elif opposite_of == "武器":
            pool = list(self.MERCHANT_POOLS["装备"])
        elif opposite_of == "装备":
            pool = list(self.MERCHANT_POOLS["武器"])
        else:
            pool = self.MERCHANT_POOLS["武器"] + self.MERCHANT_POOLS["装备"]
        choices = [key for key in pool if key not in excluded]
        return self.rng.choice(choices or pool)

    def _roll_merchant_stock(self, floor: int) -> dict[str, int]:
        """四格分别按药剂 60%、护符 25%、装备 15% 随机刷新。"""
        stock: list[str] = []
        previous_equipment_type: str | None = None
        for _ in range(4):
            category = self._merchant_restock_category()
            key = self._roll_merchant_item(
                floor,
                category,
                set(stock),
                opposite_of=previous_equipment_type if category == "装备" else None,
            )
            stock.append(key)
            previous_equipment_type = (
                self.MERCHANT_ITEMS[key][1] if category == "装备" else None
            )
        return {
            key: 4 if self.MERCHANT_ITEMS[key][1] == "药剂" else 1
            for key in stock
        }

    def _replacement_merchant_item(
        self,
        player: Player,
        category: str,
        sold_out_key: str,
    ) -> str:
        replacement_category = self._merchant_restock_category(category)
        return self._roll_merchant_item(
            player.floor,
            replacement_category,
            set(player.merchant_stock) | {sold_out_key},
        )

    def merchant_offers(self, player: Player) -> list[tuple[str, str, str, str, int]]:
        if isinstance(player.merchant_stock, list):
            player.merchant_stock = {
                key: 4 if self.MERCHANT_ITEMS[key][1] == "药剂" else 1
                for key in player.merchant_stock
            }
        if not player.merchant_stock and not (
            player.pending_event == "merchant" and player.merchant_refreshes >= 5
        ):
            player.merchant_stock = self._roll_merchant_stock(player.floor)
        floor = player.floor
        scale = 1 + (floor - 1) // 10
        offers = []
        for key in player.merchant_stock:
            name, category, effect, base_price, stats = self.MERCHANT_ITEMS[key]
            if category == "护符":
                stat_key, stat_name = next(
                    (stat, label) for stat, label in (
                        ("attack", "攻击"), ("defense", "防御"),
                        ("agility", "敏捷"), ("luck", "幸运"),
                    ) if stats.get(stat, 0)
                )
                current_count = max(0, int(player.merchant_charm_base_stats.get(stat_key, 0)))
                next_rate = (
                    merchant_charm_total(current_count + 1)
                    - merchant_charm_total(current_count)
                )
                effect = (
                    f"永久{stat_name} +{next_rate:.1f}"
                    f"（该属性累计第 {current_count + 1} 件）"
                )
            offers.append((key, name, category, effect, base_price + scale * 5))
        return offers

    def buy_merchant_item(self, player: Player, item_key: str) -> GameResult:
        offers = {
            key: (name, category, effect, price)
            for key, name, category, effect, price in self.merchant_offers(player)
        }
        if player.pending_event != "merchant":
            return GameResult("商人已经离开", "当前没有可以交易的旅行商人。")
        if item_key not in offers:
            return GameResult("商品不存在", "旅行商人翻了翻箱子，没有找到这件商品。")
        name, category, effect, price = offers[item_key]
        if player.gold < price:
            return GameResult("金币不足", f"**{name}** 需要 {price} 金币，你目前只有 {player.gold}。")
        player.gold -= price
        stats = self.MERCHANT_ITEMS[item_key][4]
        if category == "武器":
            register_equipment(
                player, name, "武器", rarity="优良",
                attack=stats.get("attack", 0),
                agility=stats.get("agility", 0),
                luck=stats.get("luck", 0),
            )
            player.weapon = name
            player.weapon_attack = stats.get("attack", 0)
            player.weapon_agility = stats.get("agility", 0)
            player.weapon_luck = stats.get("luck", 0)
        elif category == "装备":
            register_equipment(
                player, name, "护具", rarity="优良",
                defense=stats.get("defense", 0),
                agility=stats.get("agility", 0),
                luck=stats.get("luck", 0),
            )
            player.clothing = name
            player.clothing_defense = stats.get("defense", 0)
            player.clothing_agility = stats.get("agility", 0)
            player.clothing_luck = stats.get("luck", 0)
        elif category == "护符":
            stat_key = next(key for key in ("attack", "defense", "agility", "luck") if stats.get(key, 0))
            current_count = max(0, int(player.merchant_charm_base_stats.get(stat_key, 0)))
            player.merchant_charm_base_stats[stat_key] = current_count + 1
            player.merchant_charm_count = sum(
                max(0, int(player.merchant_charm_base_stats.get(key, 0)))
                for key in ("attack", "defense", "agility", "luck")
            )
            bonuses = merchant_charm_bonuses(player.merchant_charm_base_stats)
            player.merchant_attack_bonus = bonuses["attack"]
            player.merchant_defense_bonus = bonuses["defense"]
            player.merchant_agility_bonus = bonuses["agility"]
            player.merchant_luck_bonus = bonuses["luck"]
            rate = merchant_charm_total(current_count + 1) - merchant_charm_total(current_count)
        else:
            player.consumables[name] = player.consumables.get(name, 0) + 1
        player.merchant_stock[item_key] -= 1
        restocked = ""
        if player.merchant_stock[item_key] <= 0:
            del player.merchant_stock[item_key]
            if player.merchant_refreshes < 5:
                replacement = self._replacement_merchant_item(player, category, item_key)
                replacement_category = self.MERCHANT_ITEMS[replacement][1]
                player.merchant_stock[replacement] = 4 if replacement_category == "药剂" else 1
                player.merchant_refreshes += 1
                restocked = (
                    f"\n📦 **{name}** 已售罄，商人补上了一件新商品。"
                    f"本次刷新 **{player.merchant_refreshes}/5**。"
                )
            else:
                restocked = (
                    f"\n🚫 **{name}** 已售罄；本次相遇的 **5 次刷新额度已用完**，"
                    "该货位不再补货。"
                )
        applied_effect = effect
        if category == "护符":
            stat_name = next(
                label for key, label in (
                    ("attack", "攻击"), ("defense", "防御"),
                    ("agility", "敏捷"), ("luck", "幸运"),
                ) if stats.get(key, 0)
            )
            stat_count = player.merchant_charm_base_stats.get(stat_key, 0)
            applied_effect = f"永久{stat_name} +{rate:.1f}（该属性累计第 {stat_count} 件）"
        return GameResult(
            "🛍️ 购买成功",
            f"获得 **{name} ×1**（{applied_effect}），花费 **{price} 金币**。{restocked}",
        )

    def refresh_merchant_stock(self, player: Player) -> GameResult:
        if player.pending_event != "merchant":
            return GameResult("商人已经离开", "当前没有可以刷新的旅行商店。")
        if player.merchant_refreshes >= 5:
            return GameResult(
                "刷新次数已用完",
                "本次遇见旅行商人最多刷新 **5 次**；售罄补货和付费刷新共用额度。",
            )
        cost = self.merchant_refresh_cost(player.floor)
        if player.gold < cost:
            return GameResult("金币不足", f"刷新全部商品需要 **{cost} 金币**，你只有 {player.gold}。")
        player.gold -= cost
        player.merchant_stock = self._roll_merchant_stock(player.floor)
        player.merchant_refreshes += 1
        return GameResult(
            "🔄 商店刷新完成",
            f"支付 **{cost} 金币**，旅行商人换上了全新的四格商品。"
            f"本次刷新 **{player.merchant_refreshes}/5**。",
        )

    def use_potion(self, player: Player) -> GameResult:
        if player.energy < 2:
            return GameResult("精力不足", "喝治疗药水也需要 **2 点精力**；请使用精力药水或呼叫救援。")
        greater_count = player.consumables.get("强效治疗药水", 0)
        if greater_count > 0 and player.hp < player.max_hp:
            healed = min(60, player.max_hp - player.hp)
            player.hp += healed
            player.consumables["强效治疗药水"] = greater_count - 1
            player.energy -= 2
            return GameResult("🧪 使用强效治疗药水", f"消耗 **2 精力**，恢复 **{healed} 点体力**。")
        count = player.consumables.get("治疗药水", 0)
        if count <= 0:
            return GameResult("没有药水", "你的道具栏中没有治疗药水。")
        if player.hp >= player.max_hp:
            return GameResult("无需治疗", "你的体力已经全满。")
        healed = min(35, player.max_hp - player.hp)
        player.hp += healed
        player.consumables["治疗药水"] = count - 1
        player.energy -= 2
        return GameResult("使用道具", f"消耗 **2 精力**，恢复了 {healed} 点体力。")

    def use_mana_potion(self, player: Player) -> GameResult:
        if player.energy < 2:
            return GameResult("精力不足", "喝魔力药水也需要 **2 点精力**；请使用精力药水或呼叫救援。")
        greater_count = player.consumables.get("强效魔力药水", 0)
        if greater_count > 0 and player.mp < player.max_mp:
            restored = min(50, player.max_mp - player.mp)
            player.mp += restored
            player.consumables["强效魔力药水"] = greater_count - 1
            player.energy -= 2
            return GameResult(
                "💧 使用强效魔力药水",
                f"消耗 **2 精力**，恢复 **{restored} 点魔力**。",
            )
        count = player.consumables.get("魔力药水", 0)
        if count <= 0:
            return GameResult("没有魔力药水", "你的道具栏中没有魔力药水。")
        if player.mp >= player.max_mp:
            return GameResult("魔力已满", "你现在不需要使用魔力药水。")
        restored = min(25, player.max_mp - player.mp)
        player.mp += restored
        player.consumables["魔力药水"] = count - 1
        player.energy -= 2
        return GameResult("💧 使用魔力药水", f"消耗 **2 精力**，恢复 **{restored} 点魔力**。")

    def use_energy_potion(self, player: Player) -> GameResult:
        greater_count = player.consumables.get("强效精力药水", 0)
        if greater_count > 0 and player.energy < player.max_energy:
            space = player.max_energy - player.energy
            if space <= 2:
                return GameResult("精力接近全满", "至少空出 **3 点精力**再饮用，避免浪费药效。")
            restored = min(60, space)
            net = restored - 2
            player.energy += net
            player.consumables["强效精力药水"] = greater_count - 1
            return GameResult(
                "⚡ 使用强效精力药水",
                f"药效恢复 **{restored} 精力**，饮用消耗 **2 精力**，实际增加 **{net}**。",
            )
        count = player.consumables.get("精力药水", 0)
        if count <= 0:
            return GameResult("没有精力药水", "你的道具栏中没有精力药水。")
        if player.energy >= player.max_energy:
            return GameResult("精力已满", "你现在不需要使用精力药水。")
        space = player.max_energy - player.energy
        if space <= 2:
            return GameResult("精力接近全满", "至少空出 **3 点精力**再饮用，避免浪费药效。")
        restored = min(30, space)
        net = restored - 2
        player.energy += net
        player.consumables["精力药水"] = count - 1
        return GameResult(
            "⚡ 使用精力药水",
            f"药效恢复 **{restored} 精力**，饮用消耗 **2 精力**，实际增加 **{net}**。",
        )

    def request_rescue(self, player: Player) -> GameResult:
        """打开脱困选择，不在玩家确认前扣除任何东西。"""
        if player.enemy:
            return GameResult("暂时无法撤离", "怪物正拦在面前，必须先结束当前战斗。", True)
        if player.energy >= 3:
            return GameResult("还不需要救援", "你仍有足够精力继续探索。")
        if (
            player.consumables.get("精力药水", 0) > 0
            or player.consumables.get("强效精力药水", 0) > 0
        ):
            return GameResult("行囊里还有补给", "先使用一瓶精力药水就能继续前进。")
        return GameResult(
            "🛺 地下城紧急脱困",
            "远处传来车铃声，鼹鼠车夫停在了你面前；与此同时，"
            "古老的女神像也亮起了微光。请选择一种脱困方式。",
            rescue_requested=True,
        )

    def mole_rescue(self, player: Player) -> GameResult:
        """按死亡方式结算，但由车夫安全送回酒馆。"""
        if (
            player.enemy or player.energy >= 3
            or player.consumables.get("精力药水", 0) > 0
            or player.consumables.get("强效精力药水", 0) > 0
        ):
            return self.request_rescue(player)

        item_pool = [
            name
            for name, count in player.consumables.items()
            for _ in range(max(0, count))
        ]
        kept_items = self.rng.sample(item_pool, k=min(2, len(item_pool)))
        player.consumables = {}
        for name in kept_items:
            player.consumables[name] = player.consumables.get(name, 0) + 1
        original_gold = player.gold
        player.gold //= 2
        old_floor = player.floor
        player.level, player.exp = 1, 0
        player.max_hp, player.hp = 100, 100
        player.max_mp, player.mp = 50, 50
        player.max_energy, player.energy = 100, 100
        player.floor, player.steps = 1, 0
        player.required_steps = self.required_steps(1)
        player.enemy = None
        player.pending_event = None
        player.merchant_stock = {}
        player.merchant_refreshes = 0
        player.in_adventure = False
        player.gold_storage_available = True
        kept_text = "、".join(
            f"{name} ×{count}" for name, count in player.consumables.items()
        ) if player.consumables else "无"
        return GameResult(
            "🛺 鼹鼠车夫紧急救援",
            f"你在第 **{old_floor} 层**点亮求救灯。路过的鼹鼠车夫发现了你，"
            "随后把你安全送回冒险者酒馆。\n"
            f"等级、经验和层数已重置；普通道具随机只保留：**{kept_text}**。"
            f"金币由 **{original_gold}** 减少为 **{player.gold}**；"
            "装备、魔法水晶和永久加成保留。\n"
            "你已恢复为 **Lv.1**，体力、魔力和精力全部补满。",
            escaped=True,
        )

    def goddess_prayer(self, player: Player) -> GameResult:
        """放弃本次等级与经验，从地下城一层重新开始，不返回酒馆。"""
        if (
            player.enemy or player.energy >= 3
            or player.consumables.get("精力药水", 0) > 0
            or player.consumables.get("强效精力药水", 0) > 0
        ):
            return self.request_rescue(player)
        old_level, old_exp, old_floor = player.level, player.exp, player.floor
        player.level, player.exp = 1, 0
        player.max_hp, player.hp = 100, 100
        player.max_mp, player.mp = 50, 50
        player.max_energy, player.energy = 100, 100
        player.floor, player.steps = 1, 0
        player.required_steps = self.required_steps(1)
        player.enemy = None
        player.pending_event = None
        player.merchant_stock = {}
        player.merchant_refreshes = 0
        player.in_adventure = True
        return GameResult(
            "🙏 女神回应了祈祷",
            f"你放弃了 **Lv.{old_level}、{old_exp} 点当前经验**，"
            f"从第 **{old_floor} 层**被送回地下城第 **1 层**。\n"
            "你没有返回酒馆；金币、装备和道具全部保留，"
            "但等级与经验已经清零，三项资源恢复为初始值。",
        )

    def _gain_exp(self, player: Player, amount: int) -> str:
        player.exp += amount
        levels = 0
        while player.exp >= player.exp_required:
            player.exp -= player.exp_required
            player.level += 1
            player.max_hp += 8
            player.max_mp += 4
            player.max_energy += 3
            # 升级只提供一次小幅喘息，不再充当免费的全恢复药。
            player.hp = min(player.max_hp, player.hp + 24)
            player.mp = min(player.max_mp, player.mp + 10)
            player.energy = min(player.max_energy, player.energy + 12)
            levels += 1
        return (
            f"\n提升了 {levels} 级，体力 +24、魔力 +10、精力 +12！"
            if levels else ""
        )

    def _die(self, player: Player, prefix: str) -> GameResult:
        item_pool = [
            name
            for name, count in player.consumables.items()
            for _ in range(max(0, count))
        ]
        kept_items = self.rng.sample(item_pool, k=min(2, len(item_pool)))
        player.consumables = {}
        for name in kept_items:
            player.consumables[name] = player.consumables.get(name, 0) + 1
        original_gold = player.gold
        player.gold //= 2
        player.level, player.exp = 1, 0
        player.max_hp, player.hp = 100, 100
        player.max_mp, player.mp = 50, 50
        player.max_energy, player.energy = 100, 100
        player.floor, player.steps = 1, 0
        player.required_steps = self.required_steps(1)
        player.enemy, player.pending_event, player.in_adventure = None, None, False
        player.gold_storage_available = True
        kept_text = "、".join(
            f"{name} ×{count}" for name, count in player.consumables.items()
        ) if player.consumables else "无"
        return GameResult(
            "💀 你死了",
            f"{prefix}\n等级、经验和层数已重置；普通道具只保留：**{kept_text}**。"
            f"金币由 **{original_gold}** 减少为 **{player.gold}**；装备和魔法水晶保留。",
            True,
            True,
        )

    def _make_monster(
        self,
        floor: int,
        mimic: bool = False,
        star: int = 0,
    ) -> Enemy:
        # 1—9 层保留新手缓冲，10 层后成长逐渐加快。
        scale = 1 + floor * 0.11 + max(0, floor - 10) * 0.006
        zone = min(9, (floor - 1) // 10)
        zone_monsters = [
            ["洞穴史莱姆", "提灯蝙蝠", "苔藓团子"],
            ["水晶甲虫", "矿车史莱姆", "宝石蜥蜴"],
            ["蘑菇拳手", "孢子团子", "菌帽术士"],
            ["泡泡水灵", "蝾螈卫兵", "贝壳寄居蟹"],
            ["熔岩团子", "扳手魔像", "火花小鬼"],
            ["困倦书灵", "幽灵馆员", "墨水史莱姆"],
            ["发条骑士", "齿轮仓鼠", "钟摆魔偶"],
            ["企鹅卫兵", "雪绒精", "冰晶狐狸"],
            ["月兔星灵", "花园守卫", "极光飞蛾"],
            ["王座影卫", "皇冠史莱姆", "月晶魔偶"],
        ]
        name = "贪婪宝箱怪" if mimic else self.rng.choice(zone_monsters[zone])
        lines = {
            "贪婪宝箱怪": "我不是宝箱，我只是长得比较富有！",
            "洞穴史莱姆": "噗叽！这条路已经被本史莱姆承包啦！",
            "提灯蝙蝠": "吱——你的发型看起来很好抓！",
            "苔藓团子": "别踩我，我只是长得很像地毯！",
        }
        lines.setdefault(name, f"{name}摆出了自认为非常帅气的战斗姿势！")
        hp_multiplier, attack_multiplier, reward_multiplier = self.star_multipliers(star)
        hp = int((48 if mimic else 38) * scale * hp_multiplier)
        level = max(1, floor + self.rng.randint(-1, 1))
        attack = max(6, int(9 * scale * attack_multiplier))
        exp = int((18 + floor * 3) * reward_multiplier)
        return Enemy(
            name, hp, hp, attack, exp,
            "宝箱怪" if mimic else "普通怪物", level, lines[name],
            floor=floor, adventure_star=star,
        )

    def _make_boss(self, floor: int, star: int = 0) -> Enemy:
        major = floor % 10 == 0
        scale = 1 + floor * 0.13 + max(0, floor - 10) * 0.007
        hp_multiplier, attack_multiplier, reward_multiplier = self.star_multipliers(star)
        hp = int((115 if major else 78) * scale * hp_multiplier)
        zone_small_names = [
            ["提灯石像", "苔冠骑士"], ["晶矿监督", "宝石巨钳"],
            ["菌环祭司", "孢子巨人"], ["水殿门卫", "泡沫骑士"],
            ["熔炉魔像", "火花工头"], ["索引幽灵", "禁书守卫"],
            ["齿轮将军", "钟塔卫士"], ["冰门企鹅", "霜晶巨兽"],
            ["星庭园丁", "月花守卫"], ["王座近卫", "月晶执事"],
        ]
        zone = min(9, (floor - 1) // 10)
        name = self.MAJOR_BOSS_NAMES.get(floor, f"异界领主·第{floor}层") if major else self.rng.choice(zone_small_names[zone])
        lines: dict[str, str] = {}
        lines.setdefault(name, f"我是 **{name}**，这层的通行证可没那么好拿！")
        attack = int((16 if major else 12) * scale * attack_multiplier)
        exp = int((80 + floor * (10 if major else 6)) * reward_multiplier)
        return Enemy(
            name, hp, hp, attack, exp,
            "大 Boss" if major else "小 Boss",
            floor + (3 if major else 1), lines[name],
            floor=floor, adventure_star=star,
        )

    def _event_monster(self, player: Player) -> GameResult:
        player.enemy = self._make_monster(
            player.floor, star=player.completion_count
        )
        return GameResult(
            "⚠️ 你遇到了怪物！",
            f"**{player.enemy.name}** 挡住了去路！",
            True,
        )

    def _event_mimic(self, player: Player) -> GameResult:
        player.pending_event = "mimic"
        return GameResult("📦 你遇到了宝箱", "里面传来金币轻轻碰撞的声音。互动打开后，可能获得金币、药水或其他物品。")

    def _event_chest(self, player: Player) -> GameResult:
        player.pending_event = "chest"
        return GameResult("📦 你遇到了宝箱", "里面传来金币轻轻碰撞的声音。互动打开后，可能获得金币、药水或其他物品。")

    def _event_trap(self, player: Player) -> GameResult:
        raw_damage = self.rng.randint(5, 12) + player.floor // 3
        damage = self.event_damage(player, raw_damage)
        trap = self.rng.choice(("rock", "ambush", "rune", "thief", "snatcher"))
        if trap == "rock":
            player.hp = round(max(0, player.hp - damage), 2)
            if not player.is_alive:
                return self._die(player, f"你遭遇落石并失去 {damage} 点体力。")
            return GameResult("🪨 你遇到了落石！", f"巨石从头顶滚落，失去 **{damage} 点体力**。", True)
        if trap == "ambush":
            player.enemy = self._make_monster(
                player.floor, star=player.completion_count
            )
            ambush_damage = max(1, damage // 2)
            player.hp = round(max(0, player.hp - ambush_damage), 2)
            if not player.is_alive:
                return self._die(player, "你遭到藏在暗处的怪物偷袭。")
            return GameResult("⚔️ 你遭遇到了偷袭！", f"失去 **{ambush_damage} 点体力**，**{player.enemy.name}** 拦住了去路！", True)
        if trap == "rune":
            player.mp = round(max(0, player.mp - damage), 2)
            return GameResult("🔮 魔力陷阱发动！", f"符文抽走力量，失去 **{damage} 点魔力**。", True)
        if trap == "thief":
            lost = min(player.gold, self.rng.randint(8, 20) * max(1, player.floor))
            player.gold -= lost
            chase_chance = self.raccoon_chase_chance(player)
            if lost > 0 and self.rng.random() < chase_chance:
                player.enemy = self._make_monster(
                    player.floor, star=player.completion_count
                )
                player.enemy.name = "蒙面浣熊"
                player.enemy.catchphrase = "吱！追得上我，金币就还给你！"
                player.enemy.stolen_gold = lost
                return GameResult(
                    "🦝 抓住偷钱浣熊了！",
                    f"浣熊抢走了 **{lost} 金币**，但你凭借 **{format_number(player.agility)} 点敏捷**追上了它！"
                    "\n击败 **蒙面浣熊**，就能夺回全部赃款。",
                    True,
                )
            return GameResult("🦝 钱袋被偷袭了！", f"一只蒙面浣熊抢走 **{lost} 金币**，还回头对你做了个鬼脸。", True)
        available = [name for name, count in player.consumables.items() if count > 0]
        if not available:
            return GameResult("🎒 背包撕裂陷阱！", "背包被钩子划开了，好在里面没有可以掉落的道具。", True)
        lost_item = self.rng.choice(available)
        player.consumables[lost_item] -= 1
        return GameResult("🎒 背包撕裂陷阱！", f"你慌乱中遗失了 **{lost_item} ×1**。", True)

    def _event_recovery(self, player: Player) -> GameResult:
        player.pending_event = "fountain"
        return GameResult(
            "⛲ 你遇到了宁静泉水！",
            f"清澈泉水散发着柔光。互动后最多恢复 **{20 + player.floor // 2} 体力、"
            f"{12 + player.floor // 4} 魔力、14 精力**。",
        )

    def _event_shop(self, player: Player) -> GameResult:
        player.pending_event = "merchant"
        player.merchant_stock = self._roll_merchant_stock(player.floor)
        player.merchant_refreshes = 0
        return GameResult(
            "🧳 你遇到了旅行商人！",
            "推车里的货物每次相遇都会变化：药剂常见，偶尔也会出现护符、武器或装备。",
        )

    def _event_fairy(self, player: Player) -> GameResult:
        player.pending_event = "fairy"
        return GameResult(
            "🧚 你遇到了受伤的精灵！",
            "她希望得到 **治疗药水 ×1**。帮助她可能获得金币、经验，极低概率获得魔法水晶。",
        )

    def _event_mystery(self, player: Player) -> GameResult:
        player.pending_event = "mystery"
        return GameResult(
            "🗿 你遇到了柔软的神秘石像",
            "它看起来很想被摸一下。摸了以后可能恢复体力、掉落金币、受到伤害，甚至引来怪物。",
        )

    def _event_treasure_map(self, player: Player) -> GameResult:
        player.pending_event = "treasure_map"
        return GameResult(
            "🗺️ 你捡到了一张藏宝图！",
            "地图指向一条偏离当前路线的岔路。前往后可能找到大量金币或稀有水晶，也可能是陷阱。",
        )

    def _event_trapped_beast(self, player: Player) -> GameResult:
        player.pending_event = "trapped_beast"
        return GameResult(
            "🐺 你遇到了被困住的妖兽",
            "它的脚被古老捕兽夹卡住了。解救它可能获得谢礼，但惊慌的妖兽也可能反咬或引来敌人。",
        )

    def _event_wishing_well(self, player: Player) -> GameResult:
        player.pending_event = "wishing_well"
        cost = 15 + player.floor * 2
        return GameResult(
            "🪙 你遇到了地下许愿井",
            f"井壁写着模糊的古代符号。投入 **{cost} 金币**许愿，可能获得经验或幸运护符。",
        )

    def _event_empty(self, player: Player) -> GameResult:
        return GameResult("🌙 你遇到了寂静长廊", "这里暂时没有危险，你安全地向前推进。")

    def force_event(self, player: Player, event: str) -> GameResult:
        """管理员测试入口：不消耗探索步数和精力，直接生成指定事件。"""
        player.enemy = None
        player.pending_event = None
        if event == "small_boss":
            floor = player.floor if player.floor % 10 else max(1, player.floor - 1)
            player.enemy = self._make_boss(floor, player.completion_count)
            return GameResult("⚠️ 你遇到了守层者！", f"**{player.enemy.name}** 前来接受测试！", True)
        if event == "major_boss":
            floor = player.floor if player.floor % 10 == 0 else player.floor + (10 - player.floor % 10)
            player.enemy = self._make_boss(floor, player.completion_count)
            return GameResult("🔥 你遇到了大 Boss！", f"**{player.enemy.name}** 前来接受测试！", True)
        handlers = {
            "monster": self._event_monster,
            "chest": self._event_chest,
            "mimic": self._event_mimic,
            "trap": self._event_trap,
            "fountain": self._event_recovery,
            "merchant": self._event_shop,
            "fairy": self._event_fairy,
            "mystery": self._event_mystery,
            "treasure_map": self._event_treasure_map,
            "trapped_beast": self._event_trapped_beast,
            "wishing_well": self._event_wishing_well,
            "empty": self._event_empty,
        }
        return handlers[event](player)
