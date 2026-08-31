from __future__ import annotations

import random
import math
import time
from dataclasses import dataclass

from .formatting import format_number
from .models import Enemy, Player, merchant_charm_bonuses, merchant_charm_rate, merchant_charm_total
from .equipment import register_equipment
from .questions import draw_question
from .school_content import (
    FINAL_BOSS_ALIAS,
    MAJOR_BOSS_NAMES,
    MERCHANT_NAME,
    monster_names_for_floor,
    small_boss_name_for_floor,
    topic_for_floor,
    zone_for_floor,
)


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
        "minor": ("✨ 学识火花", 6, 1.20),
        "medium": ("🔷 灵感光矢", 12, 1.50),
        "major": ("🌠 真理星雨", 22, 1.85),
    }
    MAJOR_BOSS_NAMES = MAJOR_BOSS_NAMES
    MERCHANT_ITEMS = {
        "healing_potion": ("学生牛奶", "药剂", "恢复 35 点体力", 25, {}),
        "mana_potion": ("清凉油", "药剂", "恢复 25 点精神力", 30, {}),
        "energy_potion": ("运动饮料", "药剂", "恢复 30 点精力", 35, {}),
        "greater_energy_potion": ("安神补脑液", "药剂", "恢复 60 点精力（20层后出现）", 85, {}),
        "greater_healing_potion": ("校园营养餐", "药剂", "恢复 60 点体力", 58, {}),
        "greater_mana_potion": ("强劲薄荷糖", "药剂", "恢复 50 点精神力", 72, {}),
        "guard_charm": ("科创竞赛加分", "护符", "永久防御 +1", 115, {"defense": 1}),
        "lucky_charm": ("人文竞赛加分", "护符", "永久幸运 +1", 135, {"luck": 1}),
        "swift_charm": ("体育竞赛加分", "护符", "永久敏捷 +1", 125, {"agility": 1}),
        "fang_charm": ("学科竞赛加分", "护符", "永久攻击 +1", 155, {"attack": 1}),
        "iron_sword": ("老式金属直尺", "武器", "攻击 +8", 210, {"attack": 8}),
        "wind_blade": ("美工刀", "武器", "攻击 +11｜敏捷 +1", 390, {"attack": 11, "agility": 1}),
        "ember_hammer": ("实验锤", "武器", "攻击 +13｜敏捷 +1", 460, {"attack": 13, "agility": 1}),
        "tide_staff": ("指挥棒", "武器", "攻击 +15｜幸运 +2", 590, {"attack": 15, "luck": 2}),
        "gear_spear": ("订书机", "武器", "攻击 +17｜敏捷 +2", 760, {"attack": 17, "agility": 2}),
        "frost_blades": ("剪刀", "武器", "攻击 +20｜敏捷 +3", 980, {"attack": 20, "agility": 3}),
        "leather_armor": ("耐磨校服外套", "装备", "防御 +4｜敏捷 +1", 195, {"defense": 4, "agility": 1}),
        "rune_cloak": ("二手校服外套", "装备", "防御 +6｜幸运 +1", 370, {"defense": 6, "luck": 1}),
        "moss_coat": ("园艺服", "装备", "防御 +5｜敏捷 +3", 420, {"defense": 5, "agility": 3}),
        "tide_robe": ("游泳队服", "装备", "防御 +7｜幸运 +2", 560, {"defense": 7, "luck": 2}),
        "clock_armor": ("化学实验服", "装备", "防御 +10｜敏捷 +2", 760, {"defense": 10, "agility": 2}),
        "frost_cape": ("冬季加厚校服", "装备", "防御 +13｜幸运 +3", 990, {"defense": 13, "luck": 3}),
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
        """敏捷与防御共同减少探索事件造成的生命或精神力损失。"""
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
        """1—30 层提供 1.5 倍概率；新生谢礼水晶再受当日运势比例增长。"""
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
            1: "❄️ 一星学生",
            2: "❄️ 二星学生",
            3: "❄️ 三星学生",
            4: "❄️ 四星学生",
        }
        return titles.get(max(1, completion_count), "❄️ 优秀学生")

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
        if player.pending_quiz:
            return GameResult("限时答题中", "请先回答 Boss 的随堂抽测。", True)
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
        if player.pending_quiz:
            return GameResult("限时答题中", "请先选择随堂抽测的答案。", True)
        if use_skill and skill_tier is None:
            skill_tier = "medium"
        skill = self.MAGIC_SKILLS.get(skill_tier) if skill_tier else None
        if skill and player.mp < skill[1]:
            return GameResult("精神力不足", f"使用 **{skill[0]}** 需要 {skill[1]} 点精神力。")
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
            f" + 竞赛加分 {format_number(player.merchant_charm_bonus('attack'))}"
            f" + 水晶护符 {format_number(player.crystal_charm_bonus('attack'))}）"
        )
        previous_hp = enemy.hp
        enemy.hp = max(0, enemy.hp - damage)
        next_quiz_threshold = next(
            (
                value for value in self._quiz_thresholds(enemy)
                if value not in enemy.quiz_triggers_done
            ),
            None,
        )
        if next_quiz_threshold is not None:
            gate_hp = round(enemy.max_hp * next_quiz_threshold / 100, 2)
            if previous_hp > gate_hp and enemy.hp <= gate_hp:
                enemy.hp = max(1, gate_hp)
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
                item = self.rng.choice(("学生牛奶", "清凉油", "运动饮料"))
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
                    player.pending_event, player.pending_quiz, player.in_adventure = None, None, False
                    player.gold_storage_available = True
                    awarded_title = self.adventurer_title(next_star)
                    return GameResult(
                        "❄️ 百层学园探索完成",
                        f"你以{label}造成 **{format_number(damage)}** 点伤害{performance} {formula}，"
                        f"击败 **{enemy.name}**！\n获得 {exp} 经验和 {reward_gold} 金币"
                        f"{bonus_drop}。{equipment_drop}{level_text}\n\n"
                        "你通过了永不下课学园第 **100 层**，获得称号身份组 "
                        f"**{awarded_title}**！\n"
                        "永久属性提升：⚔️ **攻击 +5**｜🛡️ **防御 +3**。\n"
                        f"下一轮探索提升为 **★{next_star}**；"
                        "等级和经验已重置，装备、收藏与永久属性保留。\n"
                        "校钟将你送回了酒馆。",
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
        quiz_result = self._maybe_start_boss_quiz(player)
        if quiz_result:
            quiz_result.message = (
                f"你以{label}造成 **{format_number(damage)}** 点伤害{shield_text}{performance} {formula}。\n\n"
                f"{quiz_result.message}"
            )
            return quiz_result
        if enemy.charged_spell:
            spell_result = self._cast_enemy_spell(player, enemy)
            if not player.is_alive:
                return self._die(player, spell_result)
            return GameResult(
                "🔮 敌方招式发动！",
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
                "⚠️ 敌人正在准备招式！",
                f"你以{label}造成 **{format_number(damage)}** 点伤害{shield_text}{performance} {formula}。\n"
                f"**{enemy.name}** 正在准备 **{enemy.charged_spell}**；"
                "下一次行动将发动招式！",
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
    def _quiz_thresholds(enemy: Enemy) -> tuple[int, ...]:
        if not enemy.quiz_subject:
            return ()
        if enemy.boss_kind == "小 Boss":
            return (50,)
        if enemy.boss_kind == "大 Boss" and enemy.floor == 100:
            return (75, 50, 25)
        if enemy.boss_kind == "大 Boss":
            return (70, 35)
        return ()

    @staticmethod
    def _quiz_subject(enemy: Enemy, threshold: int) -> str:
        if enemy.floor == 100:
            return {75: "英语", 50: "语文", 25: "数学"}[threshold]
        return enemy.quiz_subject or zone_for_floor(enemy.floor).subject

    def _maybe_start_boss_quiz(self, player: Player) -> GameResult | None:
        enemy = player.enemy
        if not enemy or enemy.boss_kind not in {"小 Boss", "大 Boss"}:
            return None
        hp_percent = enemy.hp / max(1, enemy.max_hp) * 100
        threshold = next(
            (
                value for value in self._quiz_thresholds(enemy)
                if hp_percent <= value and value not in enemy.quiz_triggers_done
            ),
            None,
        )
        if threshold is None:
            return None
        enemy.quiz_triggers_done.append(threshold)
        subject = self._quiz_subject(enemy, threshold)
        question = draw_question(subject, player.recent_question_keys, self.rng)
        player.recent_question_keys.append(str(question["key"]))
        player.recent_question_keys = player.recent_question_keys[-100:]
        deadline = time.time() + 10
        player.pending_quiz = {
            **question,
            "deadline": deadline,
            "token": f"{player.user_id}:{enemy.floor}:{question['key']}:{int(deadline * 1000)}",
        }
        alias = f"（别名：{enemy.alias}）" if enemy.alias else ""
        return GameResult(
            "⏱️ Boss发动随堂抽测！",
            f"**{enemy.name}**{alias}打断了战斗。\n"
            f"科目：**{subject}**｜请在 **10秒内**选择答案。",
            True,
        )

    def answer_quiz(
        self,
        player: Player,
        answer_index: int | None,
        *,
        now: float | None = None,
    ) -> GameResult:
        quiz = player.pending_quiz
        enemy = player.enemy
        if not quiz or not enemy:
            player.pending_quiz = None
            return GameResult("题目已经结束", "当前没有需要回答的Boss题目。")
        current_time = time.time() if now is None else now
        timed_out = answer_index is None or current_time > float(quiz["deadline"])
        correct = not timed_out and answer_index == int(quiz["correct_index"])
        player.pending_quiz = None
        if correct:
            damage = max(1, round(enemy.max_hp * 0.12, 2))
            # 答题伤害不会直接击杀Boss，最终一击仍由玩家亲手完成。
            enemy.hp = max(1, round(enemy.hp - damage, 2))
            return GameResult(
                "✅ 回答正确！",
                f"正确答案：**{quiz['answer']}**\n{quiz['explanation']}\n\n"
                f"红色批注贯穿试卷，**{enemy.name}** 受到 **{format_number(damage)} 点知识伤害**，"
                "并失去本次攻击机会！",
                True,
            )

        raw = self.rng.randint(max(1, enemy.attack - 3), enemy.attack + 3)
        incoming = self.physical_damage(raw, player.defense)
        player.hp = round(max(0, player.hp - incoming), 2)
        lead = "答题超时" if timed_out else "回答错误"
        detail = (
            f"正确答案：**{quiz['answer']}**\n{quiz['explanation']}\n\n"
            f"{enemy.name} 获得一次追加攻击，造成 **{format_number(incoming)} 点伤害**。"
        )
        if not player.is_alive:
            return self._die(player, f"{lead}！\n{detail}")
        return GameResult(f"❌ {lead}！", detail, True)

    @staticmethod
    def _spell_name(enemy: Enemy) -> str:
        zone = min(10, max(1, (enemy.floor + 9) // 10))
        spells = {
            1: "哨声催跑",
            2: "石膏定格",
            3: "细胞增殖",
            4: "板块震荡",
            5: "年代篡改",
            6: "酸碱爆发",
            7: "惯性连击",
            8: "语法封锁",
            9: "标准答案",
            10: "期末压轴",
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

        if spell == "石膏定格":
            enemy.shield_ratio = 0.50
            return f"🗿 **{enemy.name}** 凝成石膏姿态，下一次受到的伤害减少 **50%**。"
        if spell == "板块震荡":
            drained = min(player.mp, 12 + enemy.adventure_star * 3)
            player.mp -= drained
            healed = min(enemy.max_hp - enemy.hp, max(1, drained * 2))
            enemy.hp += healed
            return f"🌍 **板块震荡**夺走 **{drained} 精神力**，并为敌人恢复 **{healed} 生命**。"
        if spell == "标准答案":
            healed = min(enemy.max_hp - enemy.hp, max(1, enemy.max_hp // 8))
            enemy.hp += healed
            enemy.shield_ratio = 0.25
            return f"📕 **标准答案**订正了伤口，恢复 **{healed} 生命**并获得 **25% 护盾**。"
        if spell == "惯性连击":
            hit = self.physical_damage(max(1, int(raw * 0.65)), player.defense)
            damage = hit * 2
            player.hp = round(max(0, player.hp - damage), 2)
            return f"🧲 **惯性连击**连续命中两次，共造成 **{damage} 点物理伤害**。"

        spell_data = {
            "哨声催跑": (1.00, 0.70, 0, 5, "🏃"),
            "细胞增殖": (0.80, 0.75, 0, 5, "🧬"),
            "年代篡改": (1.20, 0.80, 0, 4, "📜"),
            "酸碱爆发": (1.10, 0.80, 8, 0, "🧪"),
            "语法封锁": (0.75, 0.70, 16, 0, "🔤"),
            "期末压轴": (1.45, 0.90, 10, 8, "📝"),
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
            extras.append(f"精神力 -{drained_mp}")
        if drained_energy:
            extras.append(f"精力 -{drained_energy}")
        extra_text = f"，{'、'.join(extras)}" if extras else ""
        return (
            f"{emoji} **{enemy.name}** 发动 **{spell}**，造成 **{damage} 点招式伤害**"
            f"{extra_text}。招式会穿透大部分防御。"
        )

    def interact_event(self, player: Player) -> GameResult:
        event = player.pending_event
        if not event:
            return GameResult("没有可交互事件", "眼前没有需要处理的物品。")
        if event == "merchant":
            return GameResult(f"🧳 {MERCHANT_NAME}的小卖部", "请从商品下拉菜单中选择要购买的物品。")
        if player.energy < 2:
            return GameResult("精力不足", "打开宝箱需要 2 点精力。")
        player.energy -= 2
        if event == "mimic":
            player.pending_event = None
            player.enemy = self._make_monster(
                player.floor, mimic=True, star=player.completion_count
            )
            return GameResult(
                "😈 书包突然张嘴了！",
                f"书包拉链变成了牙齿！**{player.enemy.name}** 扑了过来！",
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
                "🏥 校医室让你恢复了精神！",
                f"恢复 **{hp} 体力、{mp} 精神力、{energy} 精力**。",
            )
        if event == "fairy":
            player.pending_event = None
            item = "学生牛奶"
            if player.consumables.get(item, 0) <= 0:
                return GameResult(
                    "🧑‍🎓 新生有点失望",
                    "你翻遍行囊也没有找到学生牛奶。她抱着空白作业本离开了。",
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
            return GameResult("🧑‍🎓 新生的谢礼", f"交出 **学生牛奶 ×1**，获得{reward}。")
        if event == "mystery":
            player.pending_event = None
            outcome = self.rng.choice(("heal", "hurt", "battle", "gold"))
            if outcome == "heal":
                healed = min(30 + player.floor, player.max_hp - player.hp)
                player.hp += healed
                return GameResult("✨ 荣誉榜发出暖光", f"照片中的学生向你点头，恢复 **{healed} 点体力**。")
            if outcome == "gold":
                gold = self.blended_gold(
                    player.floor, 20 + player.floor * 5, 12 + player.floor
                )
                player.gold += gold
                return GameResult("🪙 荣誉榜掉出金币", f"相框背后滑出 **{gold} 金币**。")
            if outcome == "battle":
                player.enemy = self._make_monster(
                    player.floor, star=player.completion_count
                )
                return GameResult("👾 荣誉榜叫来了值日生！", f"**{player.enemy.name}** 从暗门里冲了出来！", True)
            damage = self.event_damage(player, 12 + player.floor // 2)
            player.hp = round(max(0, player.hp - damage), 2)
            if not player.is_alive:
                return self._die(player, f"荣誉榜中的照片咬了你一口，造成 {damage} 点伤害。")
            return GameResult("💥 荣誉榜咬了你一口", f"失去 **{damage} 点体力**。谁让你乱摸呢？", True)
        if event == "treasure_map":
            player.pending_event = None
            roll = self.rng.random()
            crystal_chance = self.crystal_drop_chance(
                player.floor, 0.03, player.daily_fortune_growth
            )
            if roll < crystal_chance:
                player.crystals += 1
                return GameResult("🔮 答案纸指向的秘宝", "你找到了极其稀有的 **魔法水晶 ×1**！")
            if roll < 0.28 + crystal_chance - 0.03:
                player.enemy = self._make_monster(
                    player.floor, mimic=True, star=player.completion_count
                )
                return GameResult("😈 答案纸是书包怪的点名单！", f"**{player.enemy.name}** 已经等候多时！", True)
            gold = self.blended_gold(
                player.floor,
                self.rng.randint(25, 55) * max(1, player.floor),
                self.rng.randint(20, 45) + player.floor * 3,
            )
            player.gold += gold
            return GameResult("📄 找到答案纸藏品！", f"绕了一点远路，最终找到 **{gold} 金币**。")
        if event == "trapped_beast":
            player.pending_event = None
            roll = self.rng.random()
            if roll < 0.22:
                damage = self.event_damage(player, 8 + player.floor // 2)
                player.hp = round(max(0, player.hp - damage), 2)
                if not player.is_alive:
                    return self._die(player, f"校园吉祥物惊慌反咬，造成 {damage} 点伤害。")
                return GameResult("🐾 吉祥物受惊了！", f"它误咬了你一口，失去 **{damage} 点体力**，随后逃进走廊。", True)
            if roll < 0.35:
                player.enemy = self._make_monster(
                    player.floor, star=player.completion_count
                )
                return GameResult("👾 器材室管理员回来了！", f"**{player.enemy.name}** 把你当成了入侵者！", True)
            item_pool = ["学生牛奶", "清凉油", "运动饮料"]
            if player.floor >= 20:
                item_pool.append("安神补脑液")
            item = self.rng.choice(item_pool)
            player.consumables[item] = player.consumables.get(item, 0) + 1
            return GameResult("🐾 吉祥物记住了你的气味", f"它叼来 **{item} ×1** 作为谢礼，然后摇着尾巴离开了。")
        if event == "wishing_well":
            player.pending_event = None
            cost = 15 + player.floor * 2
            if player.gold < cost:
                return GameResult("🪙 愿望没有回音", f"许愿需要投入 **{cost} 金币**，你的钱袋不够沉。")
            player.gold -= cost
            roll = self.rng.random()
            if roll < 0.12:
                player.consumables["幸运护符"] = player.consumables.get("幸运护符", 0) + 1
                return GameResult("🌟 愿望成真！", f"系上价值 {cost} 金币的纸签，树梢落下 **幸运护符 ×1**。")
            if roll < 0.62:
                exp = 25 + player.floor * 4
                level_text = self._gain_exp(player, exp)
                return GameResult("✨ 许愿树闪闪发光", f"系上价值 {cost} 金币的纸签，获得 **{exp} 经验**。{level_text}")
            return GameResult("🍂 树上只有落叶", f"花费 {cost} 金币，只换来一片很有礼貌的落叶。")
        player.pending_event = None
        luck_multiplier = 1 + min(0.5, player.luck * 0.03)
        old_gold = int(self.rng.randint(8, 20) * max(1, player.floor) * luck_multiplier)
        current_gold = int((self.rng.randint(6, 16) + player.floor * 2) * luck_multiplier)
        gold = self.blended_gold(player.floor, old_gold, current_gold)
        player.gold += gold
        extra = ""
        if self.rng.random() < min(0.65, 0.25 + player.luck * 0.02):
            player.consumables["学生牛奶"] = player.consumables.get("学生牛奶", 0) + 1
            extra = "，以及一盒学生牛奶"
        return GameResult("🗄️ 储物柜开启！", f"消耗 2 点精力，获得 **{gold} 金币**{extra}。")

    def decline_event(self, player: Player) -> GameResult:
        event = player.pending_event
        player.pending_event = None
        if event == "chest":
            return GameResult(
                "🚶 你离开了储物柜",
                "你压下好奇心，放弃柜子里的奖励，安全地继续前进。",
            )
        if event == "mimic":
            avoid_chance = self.mimic_avoid_chance(player)
            if self.rng.random() < avoid_chance:
                return GameResult(
                    "🤫 你避开了书包怪",
                    f"你凭借 **{format_number(player.agility)} 点敏捷**悄悄后退；"
                    "那只可疑书包没有发现你，仍在原地耐心装死。",
                )
            player.enemy = self._make_monster(
                player.floor, mimic=True, star=player.completion_count
            )
            return GameResult(
                "😈 书包怪识破了你！",
                f"你刚转身，书包便张开大嘴扑来！"
                f"**{player.enemy.name}** 拦住了退路。",
                True,
            )
        if event == "fairy":
            return GameResult("👋 你婉拒了新生", "新生理解地点点头，抱着空白作业本离开了。")
        if event == "mystery":
            return GameResult("🚶 你忍住了好奇心", "你没有乱摸来历不明的东西。今天也很稳健。")
        if event == "treasure_map":
            return GameResult("📄 你收起了答案纸", "这条岔路看起来不太可靠，你决定继续原本的路线。")
        if event == "trapped_beast":
            return GameResult("🐾 你没有靠近吉祥物", "谨慎也许不够英雄，但通常比较长寿。")
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
            return GameResult("精力不足", "食用校园营养餐或饮用学生牛奶需要 **2 点精力**；请使用恢复精力的补给或呼叫救援。")
        greater_count = player.consumables.get("校园营养餐", 0)
        if greater_count > 0 and player.hp < player.max_hp:
            healed = min(60, player.max_hp - player.hp)
            player.hp += healed
            player.consumables["校园营养餐"] = greater_count - 1
            player.energy -= 2
            return GameResult("🍱 食用校园营养餐", f"消耗 **2 精力**，恢复 **{healed} 点体力**。")
        count = player.consumables.get("学生牛奶", 0)
        if count <= 0:
            return GameResult("没有体力补给", "你的道具栏中没有学生牛奶或校园营养餐。")
        if player.hp >= player.max_hp:
            return GameResult("无需治疗", "你的体力已经全满。")
        healed = min(35, player.max_hp - player.hp)
        player.hp += healed
        player.consumables["学生牛奶"] = count - 1
        player.energy -= 2
        return GameResult("🥛 饮用学生牛奶", f"消耗 **2 精力**，恢复了 {healed} 点体力。")

    def use_mana_potion(self, player: Player) -> GameResult:
        if player.energy < 2:
            return GameResult("精力不足", "使用清凉油或食用强劲薄荷糖需要 **2 点精力**；请使用恢复精力的补给或呼叫救援。")
        greater_count = player.consumables.get("强劲薄荷糖", 0)
        if greater_count > 0 and player.mp < player.max_mp:
            restored = min(50, player.max_mp - player.mp)
            player.mp += restored
            player.consumables["强劲薄荷糖"] = greater_count - 1
            player.energy -= 2
            return GameResult(
                "🍬 食用强劲薄荷糖",
                f"消耗 **2 精力**，恢复 **{restored} 点精神力**。",
            )
        count = player.consumables.get("清凉油", 0)
        if count <= 0:
            return GameResult("没有精神力补给", "你的道具栏中没有清凉油或强劲薄荷糖。")
        if player.mp >= player.max_mp:
            return GameResult("精神力已满", "你现在不需要使用精神力补给。")
        restored = min(25, player.max_mp - player.mp)
        player.mp += restored
        player.consumables["清凉油"] = count - 1
        player.energy -= 2
        return GameResult("🧴 使用清凉油", f"消耗 **2 精力**，恢复 **{restored} 点精神力**。")

    def use_energy_potion(self, player: Player) -> GameResult:
        greater_count = player.consumables.get("安神补脑液", 0)
        if greater_count > 0 and player.energy < player.max_energy:
            space = player.max_energy - player.energy
            if space <= 2:
                return GameResult("精力接近全满", "至少空出 **3 点精力**再饮用，避免浪费药效。")
            restored = min(60, space)
            net = restored - 2
            player.energy += net
            player.consumables["安神补脑液"] = greater_count - 1
            return GameResult(
                "🧠 饮用安神补脑液",
                f"补给恢复 **{restored} 精力**，饮用消耗 **2 精力**，实际增加 **{net}**。",
            )
        count = player.consumables.get("运动饮料", 0)
        if count <= 0:
            return GameResult("没有精力补给", "你的道具栏中没有运动饮料或安神补脑液。")
        if player.energy >= player.max_energy:
            return GameResult("精力已满", "你现在不需要使用精力补给。")
        space = player.max_energy - player.energy
        if space <= 2:
            return GameResult("精力接近全满", "至少空出 **3 点精力**再饮用，避免浪费药效。")
        restored = min(30, space)
        net = restored - 2
        player.energy += net
        player.consumables["运动饮料"] = count - 1
        return GameResult(
            "🥤 饮用运动饮料",
            f"补给恢复 **{restored} 精力**，饮用消耗 **2 精力**，实际增加 **{net}**。",
        )

    def request_rescue(self, player: Player) -> GameResult:
        """打开脱困选择，不在玩家确认前扣除任何东西。"""
        if player.enemy:
            return GameResult("暂时无法撤离", "怪物正拦在面前，必须先结束当前战斗。", True)
        if player.energy >= 3:
            return GameResult("还不需要救援", "你仍有足够精力继续探索。")
        if (
            player.consumables.get("运动饮料", 0) > 0
            or player.consumables.get("安神补脑液", 0) > 0
        ):
            return GameResult("行囊里还有补给", "先使用一份精力补给就能继续前进。")
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
            or player.consumables.get("运动饮料", 0) > 0
            or player.consumables.get("安神补脑液", 0) > 0
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
        player.pending_quiz = None
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
            "随后把你安全送回酒馆。\n"
            f"等级、经验和层数已重置；普通道具随机只保留：**{kept_text}**。"
            f"金币由 **{original_gold}** 减少为 **{player.gold}**；"
            "装备、魔法水晶和永久加成保留。\n"
            "你已恢复为 **Lv.1**，体力、精神力和精力全部补满。",
            escaped=True,
        )

    def goddess_prayer(self, player: Player) -> GameResult:
        """放弃本次等级与经验，从地下城一层重新开始，不返回酒馆。"""
        if (
            player.enemy or player.energy >= 3
            or player.consumables.get("运动饮料", 0) > 0
            or player.consumables.get("安神补脑液", 0) > 0
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
        player.pending_quiz = None
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
            f"\n提升了 {levels} 级，体力 +24、精神力 +10、精力 +12！"
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
        player.enemy, player.pending_event, player.pending_quiz, player.in_adventure = None, None, None, False
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
        mimic_name = f"{topic_for_floor(floor)}·会咬人的书包"
        name = mimic_name if mimic else self.rng.choice(monster_names_for_floor(floor))
        lines = {
            mimic_name: "作业可以不交，但你必须留下！",
        }
        lines.setdefault(name, f"{name}撕碎了课表，摆出准备抽查的架势！")
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
        name = self.MAJOR_BOSS_NAMES.get(floor, f"第{floor}层统考") if major else small_boss_name_for_floor(floor)
        lines: dict[str, str] = {}
        if floor == 100:
            lines[name] = "考试可以补考，但你只有一条命。"
        lines.setdefault(name, f"我是 **{name}**，想下课就先通过我的抽查！")
        attack = int((16 if major else 12) * scale * attack_multiplier)
        exp = int((80 + floor * (10 if major else 6)) * reward_multiplier)
        return Enemy(
            name, hp, hp, attack, exp,
            "大 Boss" if major else "小 Boss",
            floor + (3 if major else 1), lines[name],
            floor=floor, adventure_star=star,
            alias=FINAL_BOSS_ALIAS if floor == 100 else "",
            quiz_subject=zone_for_floor(floor).subject,
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
        return GameResult("🎒 你发现了无人认领的书包", "拉链缝里传来文具碰撞声。打开后可能获得金币、校园补给，也可能被它咬住。")

    def _event_chest(self, player: Player) -> GameResult:
        player.pending_event = "chest"
        return GameResult("🗄️ 你发现了上锁的储物柜", "柜门后传来轻轻的碰撞声。打开后可能获得金币、校园补给或其他物品。")

    def _event_trap(self, player: Player) -> GameResult:
        raw_damage = self.rng.randint(5, 12) + player.floor // 3
        damage = self.event_damage(player, raw_damage)
        trap = self.rng.choice(("rock", "ambush", "rune", "thief", "snatcher"))
        if trap == "rock":
            player.hp = round(max(0, player.hp - damage), 2)
            if not player.is_alive:
                return self._die(player, f"你遭遇落石并失去 {damage} 点体力。")
            return GameResult("🧹 黑板擦陷阱！", f"一整排黑板擦从柜顶落下，失去 **{damage} 点体力**。", True)
        if trap == "ambush":
            player.enemy = self._make_monster(
                player.floor, star=player.completion_count
            )
            ambush_damage = max(1, damage // 2)
            player.hp = round(max(0, player.hp - ambush_damage), 2)
            if not player.is_alive:
                return self._die(player, "你遭到藏在暗处的怪物偷袭。")
            return GameResult("📣 走廊突击检查！", f"失去 **{ambush_damage} 点体力**，**{player.enemy.name}** 拦住了去路！", True)
        if trap == "rune":
            player.mp = round(max(0, player.mp - damage), 2)
            return GameResult("📝 随堂测验陷阱！", f"试卷抽走了思考能力，失去 **{damage} 点精神力**。", True)
        if trap == "thief":
            lost = min(player.gold, self.rng.randint(8, 20) * max(1, player.floor))
            player.gold -= lost
            chase_chance = self.raccoon_chase_chance(player)
            if lost > 0 and self.rng.random() < chase_chance:
                player.enemy = self._make_monster(
                    player.floor, star=player.completion_count
                )
                player.enemy.name = f"{topic_for_floor(player.floor)}·蒙面浣熊"
                player.enemy.catchphrase = "吱！追得上我，金币就还给你！"
                player.enemy.stolen_gold = lost
                return GameResult(
                    "🦝 抓住偷钱浣熊了！",
                    f"浣熊抢走了 **{lost} 金币**，但你凭借 **{format_number(player.agility)} 点敏捷**追上了它！"
                    f"\n击败 **{player.enemy.name}**，就能夺回全部赃款。",
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
            "🏥 你找到了校医室！",
            f"值班床铺与药柜散发着安心的气息。休息后最多恢复 **{20 + player.floor // 2} 体力、"
            f"{12 + player.floor // 4} 精神力、14 精力**。",
        )

    def _event_shop(self, player: Player) -> GameResult:
        player.pending_event = "merchant"
        player.merchant_stock = self._roll_merchant_stock(player.floor)
        player.merchant_refreshes = 0
        return GameResult(
            f"🧳 你遇到了旅行商人·{MERCHANT_NAME}！",
            f"**{MERCHANT_NAME}** 推着塞满文具、校园补给和违禁零食的小车穿过走廊。"
            "货物每次相遇都会变化：药剂常见，偶尔也会出现竞赛加分、武器或装备。",
        )

    def _event_fairy(self, player: Player) -> GameResult:
        player.pending_event = "fairy"
        return GameResult(
            "🧑‍🎓 你遇到了忘带作业的新生！",
            "她希望得到 **学生牛奶 ×1**平复惊吓。帮助她可能获得金币、经验，极低概率获得魔法水晶。",
        )

    def _event_mystery(self, player: Player) -> GameResult:
        player.pending_event = "mystery"
        return GameResult(
            "🏅 你看见了会变化的荣誉榜",
            "榜上的模范学生照片正盯着你。触碰后可能恢复体力、掉落金币、受到伤害，甚至引来怪物。",
        )

    def _event_treasure_map(self, player: Player) -> GameResult:
        player.pending_event = "treasure_map"
        return GameResult(
            "📄 你捡到了一张神秘答案纸！",
            "答案纸指向一间偏离当前路线的教室。前往后可能找到大量金币或稀有水晶，也可能是陷阱。",
        )

    def _event_trapped_beast(self, player: Player) -> GameResult:
        player.pending_event = "trapped_beast"
        return GameResult(
            "🐾 你遇到了被锁住的校园吉祥物",
            "它被困在器材室铁链里。解救它可能获得谢礼，但惊慌的吉祥物也可能反咬或引来敌人。",
        )

    def _event_wishing_well(self, player: Player) -> GameResult:
        player.pending_event = "wishing_well"
        cost = 15 + player.floor * 2
        return GameResult(
            "🌳 你遇到了操场旁的许愿树",
            f"树枝挂满历届学生的纸条。系上价值 **{cost} 金币**的许愿签，可能获得经验或幸运护符。",
        )

    def _event_empty(self, player: Player) -> GameResult:
        return GameResult("📚 你经过了无人的自习室", "桌椅整齐得不正常，但这里暂时没有危险。")

    def force_event(self, player: Player, event: str) -> GameResult:
        """管理员测试入口：不消耗探索步数和精力，直接生成指定事件。"""
        player.enemy = None
        player.pending_event = None
        player.pending_quiz = None
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
