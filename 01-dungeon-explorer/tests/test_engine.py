import random
import unittest
from unittest.mock import Mock

from game.engine import GameEngine
from game.models import Enemy, Player


class EngineTests(unittest.TestCase):
    def test_required_steps_expand_with_depth(self):
        early = GameEngine(random.Random(1)).required_steps(1)
        deep = GameEngine(random.Random(1)).required_steps(100)
        self.assertTrue(12 <= early <= 24)
        self.assertTrue(24 <= deep <= 36)

    def test_every_tenth_floor_is_major_boss(self):
        engine = GameEngine(random.Random(1))
        self.assertEqual(engine._make_boss(4).boss_kind, "小 Boss")
        self.assertEqual(engine._make_boss(5).boss_kind, "小 Boss")
        self.assertEqual(engine._make_boss(10).boss_kind, "大 Boss")
        self.assertEqual(engine._make_boss(100).boss_kind, "大 Boss")

    def test_regular_floor_clears_without_a_boss(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "冒险者", floor=4, required_steps=1)

        result = engine.explore(player)

        self.assertEqual(result.title, "🚪 找到下层入口")
        self.assertEqual(player.floor, 5)
        self.assertIsNone(player.enemy)

    def test_floor_five_can_randomly_spawn_a_small_boss(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "冒险者", floor=5, required_steps=1)

        engine.explore(player)

        self.assertIsNotNone(player.enemy)
        self.assertEqual(player.enemy.boss_kind, "小 Boss")

    def test_floor_ten_always_spawns_its_fixed_major_boss(self):
        engine = GameEngine(random.Random(999))
        player = Player(1, "冒险者", floor=10, required_steps=1)

        engine.explore(player)

        self.assertEqual(player.enemy.boss_kind, "大 Boss")
        self.assertEqual(player.enemy.name, "黏液大公·噗叽伯爵")

    def test_old_saved_major_boss_name_is_migrated(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "老存档", floor=10, required_steps=5)
        player.enemy = Enemy("深渊领主", 100, 100, 10, 100, "大 Boss")

        engine.ensure_floor(player)

        self.assertEqual(player.enemy.name, "黏液大公·噗叽伯爵")

    def test_death_keeps_equipment_crystals_half_gold_and_two_items(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "测试者", level=8, exp=77, floor=20, hp=1, gold=888, crystals=9)
        player.weapon, player.clothing = "传说之剑", "龙鳞甲"
        player.consumables = {"治疗药水": 5}
        player.enemy = Enemy("测试怪", 999, 999, 999, 1)
        engine.attack(player)
        self.assertEqual((player.level, player.exp, player.floor), (1, 0, 1))
        self.assertEqual((player.gold, player.crystals), (444, 9))
        self.assertEqual((player.weapon, player.clothing), ("传说之剑", "龙鳞甲"))
        self.assertEqual(player.consumables, {"治疗药水": 2})
        self.assertTrue(player.gold_storage_available)

    def test_gold_curve_reaches_deep_floor_standard_without_a_step(self):
        self.assertEqual(GameEngine.blended_gold(1, 300, 60), 180)
        self.assertEqual(GameEngine.blended_gold(50, 300, 60), 140)
        self.assertEqual(GameEngine.blended_gold(75, 300, 60), 124)
        self.assertEqual(GameEngine.blended_gold(100, 300, 60), 108)

    def test_early_crystal_chance_is_one_and_a_half_times_base(self):
        self.assertAlmostEqual(GameEngine.crystal_drop_chance(30, 0.08), 0.12)
        self.assertAlmostEqual(GameEngine.crystal_drop_chance(31, 0.08), 0.08)
        self.assertAlmostEqual(GameEngine.crystal_drop_chance(30, 0.08, 0.60), 0.192)

    def test_gold_storage_is_available_to_everyone_in_tavern(self):
        player = Player(1, "储值测试", gold=500, gold_storage_available=False)

        deposited = GameEngine.deposit_gold(player, 320)
        withdrawn = GameEngine.withdraw_gold(player, 120)

        self.assertEqual(deposited.title, "🪙 储存成功")
        self.assertEqual(withdrawn.title, "🪙 取出成功")
        self.assertEqual((player.gold, player.stored_gold), (300, 200))

        player.in_adventure = True
        blocked = GameEngine.deposit_gold(player, 1)
        self.assertEqual(blocked.title, "无法储值")

    def test_treasure_map_crystal_chance_receives_daily_fortune_growth(self):
        rng = Mock()
        rng.random.return_value = 0.04
        engine = GameEngine(rng)
        player = Player(
            1, "高运寻宝者", floor=31, energy=10,
            pending_event="treasure_map", daily_fortune_growth=0.60,
        )

        result = engine.interact_event(player)

        self.assertEqual(result.title, "🔮 地图尽头的秘宝")
        self.assertEqual(player.crystals, 1)

    def test_boss_victory_advances_floor(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "测试者", floor=4)
        player.enemy = Enemy("守门石像", 1, 1, 1, 10, "小 Boss")
        engine.attack(player)
        self.assertEqual(player.floor, 5)
        self.assertEqual(player.steps, 0)
        self.assertIsNone(player.enemy)

    def test_floor_100_victory_completes_run_and_returns_to_tavern(self):
        engine = GameEngine(random.Random(1))
        player = Player(
            1, "百层勇者", level=18, exp=77, floor=100,
            in_adventure=True, hp=20, mp=3, energy=2,
        )
        player.enemy = Enemy("最终守层者", 1, 1, 1, 10_000, "大 Boss")

        result = engine.attack(player)

        self.assertTrue(result.completed)
        self.assertFalse(result.death)
        self.assertEqual(player.completion_count, 1)
        self.assertEqual(player.permanent_attack_bonus, 5)
        self.assertEqual(player.permanent_defense_bonus, 3)
        self.assertEqual(player.attack_bonus, player.weapon_attack + 5)
        self.assertEqual(player.defense, player.clothing_defense + 3)
        self.assertEqual((player.floor, player.steps), (1, 0))
        self.assertEqual((player.level, player.exp), (1, 0))
        self.assertEqual((player.max_hp, player.max_mp, player.max_energy), (100, 50, 100))
        self.assertFalse(player.in_adventure)
        self.assertTrue(player.gold_storage_available)
        self.assertIsNone(player.enemy)
        self.assertEqual(
            (player.hp, player.mp, player.energy),
            (player.max_hp, player.max_mp, player.max_energy),
        )
        self.assertIn("★1", result.message)
        self.assertEqual(result.awarded_title, "❄️ 一星冒险者")

    def test_adventurer_titles_advance_and_fifth_clear_grants_beginner(self):
        self.assertEqual(GameEngine.adventurer_title(1), "❄️ 一星冒险者")
        self.assertEqual(GameEngine.adventurer_title(2), "❄️ 二星冒险者")
        self.assertEqual(GameEngine.adventurer_title(3), "❄️ 三星冒险者")
        self.assertEqual(GameEngine.adventurer_title(4), "❄️ 四星冒险者")
        self.assertEqual(GameEngine.adventurer_title(5), "❄️ 初级冒险者")
        self.assertEqual(GameEngine.adventurer_title(6), "❄️ 初级冒险者")

        engine = GameEngine(random.Random(1))
        player = Player(1, "五星勇者", floor=100, completion_count=4)
        player.enemy = Enemy("最终守层者", 1, 1, 1, 10_000, "大 Boss")

        result = engine.attack(player)

        self.assertEqual(player.completion_count, 5)
        self.assertEqual(result.awarded_title, "❄️ 初级冒险者")
        self.assertIn("**❄️ 初级冒险者**", result.message)

    def test_star_difficulty_scales_enemy_hp_attack_and_exp(self):
        base_engine = GameEngine(random.Random(5))
        star_engine = GameEngine(random.Random(5))

        base = base_engine._make_boss(20, star=0)
        star = star_engine._make_boss(20, star=1)

        self.assertEqual(star.adventure_star, 1)
        self.assertAlmostEqual(star.max_hp / base.max_hp, 1.5, delta=0.02)
        self.assertAlmostEqual(star.attack / base.attack, 1.3, delta=0.03)
        self.assertGreater(star.exp_reward, base.exp_reward)

    def test_defense_cannot_reduce_physical_damage_to_zero(self):
        self.assertEqual(GameEngine.physical_damage(100, 999), 15)
        self.assertEqual(GameEngine.physical_damage(10, 999), 2)

    def test_boss_charged_magic_has_unique_effect_and_defense_penetration(self):
        engine = GameEngine(random.Random(2))
        player = Player(1, "坦克", hp=100, clothing_defense=999)
        player.enemy = Enemy(
            "黏液大公", 999, 999, 30, 0, "大 Boss",
            floor=10, charged_spell="腐蚀酸雨",
        )

        result = engine.attack(player)

        self.assertEqual(result.title, "🔮 敌方魔法发动！")
        self.assertLess(player.hp, 100)
        self.assertIn("腐蚀酸雨", result.message)
        self.assertIn("穿透", result.message)

    def test_boss_spell_names_change_by_zone(self):
        engine = GameEngine(random.Random(1))
        spells = {
            engine._spell_name(engine._make_boss(floor))
            for floor in range(10, 101, 10)
        }
        self.assertEqual(len(spells), 10)

    def test_mimic_is_hidden_until_interaction(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "测试者")

        result = engine._event_mimic(player)

        self.assertEqual(result.title, "📦 你遇到了宝箱")
        self.assertIsNone(player.enemy)
        self.assertEqual(player.pending_event, "mimic")

        reveal = engine.interact_event(player)

        self.assertEqual(reveal.title, "😈 你遇到了宝箱怪！")
        self.assertIsNotNone(player.enemy)
        self.assertEqual(player.enemy.boss_kind, "宝箱怪")
        self.assertIsNone(player.pending_event)

    def test_player_can_leave_a_real_chest_without_spending_energy(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "谨慎勇者", energy=20, pending_event="chest")

        result = engine.decline_event(player)

        self.assertEqual(result.title, "🚶 你离开了宝箱")
        self.assertEqual(player.energy, 20)
        self.assertIsNone(player.pending_event)
        self.assertIsNone(player.enemy)

    def test_agility_increases_mimic_avoid_chance_with_a_cap(self):
        normal = Player(1, "普通勇者")
        agile = Player(2, "灵巧勇者", clothing_agility=10)
        extremely_agile = Player(3, "追风勇者", clothing_agility=100)

        self.assertAlmostEqual(GameEngine.mimic_avoid_chance(normal), 0.70)
        self.assertAlmostEqual(GameEngine.mimic_avoid_chance(agile), 0.90)
        self.assertAlmostEqual(GameEngine.mimic_avoid_chance(extremely_agile), 0.95)

    def test_leaving_a_mimic_can_avoid_it_or_start_battle(self):
        rng = Mock()
        engine = GameEngine(rng)
        player = Player(1, "谨慎勇者", energy=20, pending_event="mimic")

        rng.random.return_value = 0.0
        avoided = engine.decline_event(player)

        self.assertEqual(avoided.title, "🤫 你避开了宝箱怪")
        self.assertIsNone(player.enemy)
        self.assertEqual(player.energy, 20)

        player.pending_event = "mimic"
        rng.random.return_value = 1.0
        engine._make_monster = Mock(
            return_value=Enemy("贪婪宝箱怪", 50, 50, 10, 20, "宝箱怪")
        )
        caught = engine.decline_event(player)

        self.assertEqual(caught.title, "😈 宝箱怪识破了你！")
        self.assertIsNotNone(player.enemy)
        self.assertEqual(player.enemy.boss_kind, "宝箱怪")
        self.assertEqual(player.energy, 20)

    def test_level_and_weapon_both_increase_damage(self):
        low_engine = GameEngine(random.Random(10))
        high_engine = GameEngine(random.Random(10))
        low = Player(1, "新手", level=1, weapon_attack=4)
        high = Player(2, "高手", level=10, weapon_attack=20)
        low.enemy = Enemy("木桩", 9999, 9999, 1, 0)
        high.enemy = Enemy("木桩", 9999, 9999, 1, 0)

        low_before, high_before = low.enemy.hp, high.enemy.hp
        low_engine.attack(low)
        high_engine.attack(high)

        self.assertGreater(high_before - high.enemy.hp, low_before - low.enemy.hp)

    def test_level_up_only_partially_restores_resources(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "负伤者", hp=10, mp=5, energy=7, exp=99)

        text = engine._gain_exp(player, 1)

        self.assertEqual(player.level, 2)
        self.assertEqual((player.max_hp, player.max_mp, player.max_energy), (108, 54, 103))
        self.assertEqual((player.hp, player.mp, player.energy), (34, 15, 19))
        self.assertIn("体力 +24", text)

    def test_stranded_player_can_pay_gold_to_return_to_tavern(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "迷路者", floor=12, energy=0, gold=100)
        player.in_adventure = True
        player.consumables = {}

        prompt = engine.request_rescue(player)
        result = engine.mole_rescue(player)

        self.assertTrue(prompt.rescue_requested)
        self.assertTrue(result.escaped)
        self.assertEqual(player.gold, 50)
        self.assertEqual((player.level, player.exp), (1, 0))
        self.assertEqual((player.floor, player.steps, player.energy), (1, 0, 100))
        self.assertFalse(player.in_adventure)

    def test_stranded_player_with_one_item_keeps_that_item(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "迷路者", floor=20, energy=0, gold=0)
        player.in_adventure = True
        player.consumables = {"治疗药水": 1}

        result = engine.mole_rescue(player)

        self.assertTrue(result.escaped)
        self.assertEqual(player.consumables["治疗药水"], 1)
        self.assertEqual(player.floor, 1)

    def test_mole_rescue_randomly_keeps_only_two_items(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "迷路者", floor=20, energy=0, gold=80, in_adventure=True)
        player.consumables = {"治疗药水": 3, "魔力药水": 2}

        engine.mole_rescue(player)

        self.assertEqual(sum(player.consumables.values()), 2)
        self.assertEqual(player.gold, 40)

    def test_completely_empty_player_is_never_permanently_stuck(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "倒霉蛋", floor=30, energy=0, gold=0)
        player.in_adventure = True
        player.consumables = {}

        result = engine.mole_rescue(player)

        self.assertTrue(result.escaped)
        self.assertIn("普通道具随机只保留", result.message)
        self.assertEqual(player.energy, 100)

    def test_goddess_prayer_restarts_at_level_one_without_returning_to_tavern(self):
        engine = GameEngine(random.Random(1))
        player = Player(
            1, "祈祷者", level=8, exp=77, floor=25, energy=0,
            gold=500, in_adventure=True,
        )
        player.consumables = {"治疗药水": 3}

        result = engine.goddess_prayer(player)

        self.assertFalse(result.escaped)
        self.assertEqual((player.level, player.exp, player.floor), (1, 0, 1))
        self.assertTrue(player.in_adventure)
        self.assertEqual(player.gold, 500)
        self.assertEqual(player.consumables, {"治疗药水": 3})
        self.assertEqual((player.hp, player.mp, player.energy), (100, 50, 100))

    def test_floor_twenty_enemies_are_stronger_than_old_curve(self):
        engine = GameEngine(random.Random(1))
        monster = engine._make_monster(20)
        boss = engine._make_boss(20)

        self.assertGreaterEqual(monster.attack, 27)
        self.assertGreaterEqual(boss.attack, 57)

    def test_agility_reduces_random_event_damage(self):
        low = Player(1, "笨重勇者", clothing_defense=1, clothing_agility=0)
        high = Player(2, "灵巧勇者", clothing_defense=1, clothing_agility=10)

        self.assertEqual(GameEngine.event_damage(low, 15), 15)
        self.assertEqual(GameEngine.event_damage(high, 15), 10)

    def test_agility_increases_raccoon_chase_chance_with_a_cap(self):
        normal = Player(1, "普通勇者")
        agile = Player(2, "灵巧勇者", clothing_agility=6)
        extremely_agile = Player(3, "追风勇者", clothing_agility=100)

        self.assertEqual(GameEngine.raccoon_chase_chance(normal), 0.20)
        self.assertEqual(GameEngine.raccoon_chase_chance(agile), 0.50)
        self.assertEqual(GameEngine.raccoon_chase_chance(extremely_agile), 0.50)

    def test_catching_raccoon_starts_battle_and_victory_returns_stolen_gold(self):
        rng = Mock()
        rng.randint.side_effect = [5, 10]
        rng.choice.return_value = "thief"
        rng.random.return_value = 0.0
        engine = GameEngine(rng)
        engine._make_monster = Mock(
            return_value=Enemy("占位怪物", 1, 1, 1, 0)
        )
        player = Player(1, "灵巧勇者", gold=100, clothing_agility=6)

        result = engine._event_trap(player)

        self.assertEqual(result.title, "🦝 抓住偷钱浣熊了！")
        self.assertEqual(player.gold, 90)
        self.assertEqual(player.enemy.name, "蒙面浣熊")
        self.assertEqual(player.enemy.stolen_gold, 10)

        rng.randint.side_effect = [20, 5, 6]
        rng.random.return_value = 1.0
        victory = engine.attack(player)

        self.assertEqual(player.gold, 106)
        self.assertIsNone(player.enemy)
        self.assertIn("夺回了被偷走的 **10 金币**", victory.message)

    def test_luck_increases_real_chest_probability_with_a_cap(self):
        normal = Player(1, "普通勇者")
        lucky = Player(2, "幸运勇者", weapon_luck=10)
        extremely_lucky = Player(3, "欧皇", weapon_luck=100)

        self.assertEqual(GameEngine.chest_chance(normal), 0.625)
        self.assertEqual(GameEngine.chest_chance(lucky), 0.775)
        self.assertEqual(GameEngine.chest_chance(extremely_lucky), 0.90)

    def test_three_magic_skills_have_ordered_cost_and_damage(self):
        damages = []
        costs = []
        for tier in ("minor", "medium", "major"):
            engine = GameEngine(random.Random(10))
            player = Player(1, "法师", mp=50)
            player.enemy = Enemy("木桩", 9999, 9999, 1, 0)
            before_hp, before_mp = player.enemy.hp, player.mp

            engine.attack(player, skill_tier=tier)

            damages.append(before_hp - player.enemy.hp)
            costs.append(before_mp - player.mp)
        self.assertEqual(costs, [6, 12, 22])
        self.assertLess(damages[0], damages[1])
        self.assertLess(damages[1], damages[2])

    def test_merchant_menu_supports_repeated_purchases(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "顾客", floor=3, gold=500)
        engine._event_shop(player)
        player.merchant_stock = {"healing_potion": 4, "mana_potion": 4}

        first = engine.buy_merchant_item(player, "healing_potion")
        engine.buy_merchant_item(player, "healing_potion")
        engine.buy_merchant_item(player, "healing_potion")
        fourth = engine.buy_merchant_item(player, "healing_potion")

        self.assertEqual(first.title, "🛍️ 购买成功")
        self.assertEqual(fourth.title, "🛍️ 购买成功")
        self.assertEqual(player.gold, 380)
        self.assertEqual(player.consumables["治疗药水"], 6)
        self.assertNotIn("healing_potion", player.merchant_stock)
        self.assertEqual(len(player.merchant_stock), 2)
        self.assertEqual(player.pending_event, "merchant")

    def test_merchant_stock_is_random_but_stable_during_encounter(self):
        engine = GameEngine(random.Random(7))
        player = Player(1, "顾客", floor=25, gold=999)
        engine._event_shop(player)

        first = engine.merchant_offers(player)
        second = engine.merchant_offers(player)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)
        self.assertTrue(all(price >= 40 for _, _, _, _, price in first))

    def test_merchant_restock_category_uses_60_25_15_weights(self):
        engine = GameEngine(random.Random(20260803))
        counts = {"药剂": 0, "护符": 0, "装备": 0}
        for _ in range(20_000):
            counts[engine._merchant_restock_category()] += 1

        self.assertAlmostEqual(counts["药剂"] / 20_000, 0.60, delta=0.015)
        self.assertAlmostEqual(counts["护符"] / 20_000, 0.25, delta=0.015)
        self.assertAlmostEqual(counts["装备"] / 20_000, 0.15, delta=0.015)

    def test_bought_equipment_restock_never_returns_equipment(self):
        engine = GameEngine(random.Random(4))
        player = Player(1, "顾客", floor=12, gold=2_000, pending_event="merchant")
        player.merchant_stock = {"iron_sword": 1}

        result = engine.buy_merchant_item(player, "iron_sword")

        self.assertEqual(result.title, "🛍️ 购买成功")
        self.assertNotIn("iron_sword", player.merchant_stock)
        self.assertEqual(len(player.merchant_stock), 1)
        replacement = next(iter(player.merchant_stock))
        self.assertIn(engine.MERCHANT_ITEMS[replacement][1], {"药剂", "护符"})
        self.assertIn("补上了一件新商品", result.message)

    def test_potion_and_charm_restock_use_general_category_weights(self):
        engine = GameEngine(random.Random(4))
        counts = {"药剂": 0, "护符": 0, "装备": 0}
        for _ in range(20_000):
            counts[engine._merchant_restock_category("药剂")] += 1
        self.assertAlmostEqual(counts["药剂"] / 20_000, 0.60, delta=0.015)
        self.assertAlmostEqual(counts["护符"] / 20_000, 0.25, delta=0.015)
        self.assertAlmostEqual(counts["装备"] / 20_000, 0.15, delta=0.015)

    def test_equipment_restock_uses_70_30_potion_charm_weights(self):
        engine = GameEngine(random.Random(20260803))
        counts = {"药剂": 0, "护符": 0}
        for _ in range(20_000):
            counts[engine._merchant_restock_category("武器")] += 1
        self.assertAlmostEqual(counts["药剂"] / 20_000, 0.70, delta=0.015)
        self.assertAlmostEqual(counts["护符"] / 20_000, 0.30, delta=0.015)

    def test_paid_refresh_replaces_every_merchant_slot(self):
        engine = GameEngine(random.Random(8))
        player = Player(1, "顾客", floor=20, gold=5_000, pending_event="merchant")
        player.merchant_stock = {
            "healing_potion": 4,
            "mana_potion": 4,
            "iron_sword": 1,
            "guard_charm": 1,
        }
        old_stock = dict(player.merchant_stock)

        result = engine.refresh_merchant_stock(player)

        self.assertEqual(result.title, "🔄 商店刷新完成")
        self.assertNotEqual(player.merchant_stock, old_stock)
        self.assertEqual(len(player.merchant_stock), 4)
        self.assertEqual(player.gold, 4_905)

    def test_refresh_uses_high_tier_potion_price_curve(self):
        self.assertEqual(GameEngine.merchant_refresh_cost(1), 90)
        self.assertEqual(GameEngine.merchant_refresh_cost(20), 95)
        self.assertEqual(GameEngine.merchant_refresh_cost(100), 135)

    def test_merchant_all_refresh_paths_share_five_use_limit(self):
        engine = GameEngine(random.Random(8))
        player = Player(1, "顾客", floor=20, gold=20_000, pending_event="merchant")
        player.merchant_stock = engine._roll_merchant_stock(player.floor)

        for _ in range(5):
            result = engine.refresh_merchant_stock(player)
            self.assertEqual(result.title, "🔄 商店刷新完成")

        blocked = engine.refresh_merchant_stock(player)

        self.assertEqual(player.merchant_refreshes, 5)
        self.assertEqual(blocked.title, "刷新次数已用完")

    def test_sold_out_restock_stops_after_five_total_refreshes(self):
        engine = GameEngine(random.Random(3))
        player = Player(
            1, "顾客", floor=10, gold=5_000,
            pending_event="merchant", merchant_refreshes=5,
        )
        player.merchant_stock = {"iron_sword": 1}

        result = engine.buy_merchant_item(player, "iron_sword")

        self.assertEqual(player.merchant_stock, {})
        self.assertIn("5 次刷新额度已用完", result.message)
        self.assertEqual(engine.merchant_offers(player), [])
        self.assertEqual(player.merchant_stock, {})

    def test_merchant_charm_grants_small_permanent_stat(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "顾客", gold=999, pending_event="merchant")
        player.merchant_stock = {"lucky_charm": 1}

        result = engine.buy_merchant_item(player, "lucky_charm")

        self.assertEqual(result.title, "🛍️ 购买成功")
        self.assertEqual(player.permanent_luck_bonus, 0)
        self.assertEqual(player.merchant_luck_bonus, 1)
        self.assertEqual(player.merchant_charm_count, 1)
        self.assertEqual(player.luck, 1)
        self.assertNotIn("lucky_charm", player.merchant_stock)

    def test_merchant_attack_charm_grants_permanent_attack(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "顾客", gold=999, pending_event="merchant")
        player.merchant_stock = {"fang_charm": 1}

        result = engine.buy_merchant_item(player, "fang_charm")

        self.assertEqual(result.title, "🛍️ 购买成功")
        self.assertEqual(player.permanent_attack_bonus, 0)
        self.assertEqual(player.merchant_attack_bonus, 1)
        self.assertEqual(player.attack_bonus, player.weapon_attack + 1)

    def test_merchant_charm_rates_follow_all_six_tiers(self):
        expected = {
            1: 1.0, 20: 1.0, 21: 0.8, 40: 0.8,
            41: 0.5, 60: 0.5, 61: 0.3, 80: 0.3,
            81: 0.2, 100: 0.2, 101: 0.1,
        }
        for charm_number, rate in expected.items():
            with self.subTest(charm_number=charm_number):
                self.assertEqual(GameEngine.merchant_charm_rate(charm_number), rate)

    def test_merchant_shop_displays_next_charm_actual_tier_value(self):
        engine = GameEngine(random.Random(1))
        player = Player(
            1, "顾客", merchant_charm_count=20,
            merchant_charm_base_stats={"defense": 20},
            merchant_stock={"guard_charm": 1},
        )

        offer = engine.merchant_offers(player)[0]

        self.assertEqual(offer[3], "永久防御 +0.8（该属性累计第 21 件）")

    def test_new_charm_recalculates_all_existing_merchant_charms(self):
        engine = GameEngine(random.Random(1))
        player = Player(
            1, "顾客", gold=999, pending_event="merchant",
            merchant_charm_count=20,
            merchant_charm_base_stats={"attack": 10, "defense": 10},
            merchant_attack_bonus=10,
            merchant_defense_bonus=10,
            merchant_stock={"guard_charm": 1},
        )

        result = engine.buy_merchant_item(player, "guard_charm")

        self.assertEqual(player.merchant_charm_count, 21)
        self.assertEqual(player.merchant_attack_bonus, 10)
        self.assertEqual(player.merchant_defense_bonus, 11)
        self.assertIn("永久防御 +1.0（该属性累计第 11 件）", result.message)

    def test_each_merchant_charm_stat_uses_its_own_count_tier(self):
        engine = GameEngine(random.Random(1))
        player = Player(
            1, "分类护符玩家", gold=999, pending_event="merchant",
            merchant_charm_count=31,
            merchant_charm_base_stats={"attack": 25, "defense": 6},
            merchant_attack_bonus=24,
            merchant_defense_bonus=6,
            merchant_stock={"guard_charm": 1},
        )

        offer = engine.merchant_offers(player)[0]
        result = engine.buy_merchant_item(player, "guard_charm")

        self.assertEqual(offer[3], "永久防御 +1.0（该属性累计第 7 件）")
        self.assertEqual(player.merchant_charm_base_stats, {"attack": 25, "defense": 7})
        self.assertEqual(player.merchant_attack_bonus, 24)
        self.assertEqual(player.merchant_defense_bonus, 7)
        self.assertIn("永久防御 +1.0（该属性累计第 7 件）", result.message)

    def test_fountain_waits_for_interaction(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "冒险者", hp=40, mp=10, energy=50)

        found = engine._event_recovery(player)

        self.assertEqual(found.title, "⛲ 你遇到了宁静泉水！")
        self.assertEqual((player.hp, player.mp, player.energy), (40, 10, 50))
        self.assertEqual(player.pending_event, "fountain")

        engine.interact_event(player)

        self.assertGreater(player.hp, 40)
        self.assertGreater(player.mp, 10)
        self.assertGreater(player.energy, 48)
        self.assertIsNone(player.pending_event)

    def test_admin_can_force_a_hidden_mimic(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "管理员")

        result = engine.force_event(player, "mimic")

        self.assertEqual(result.title, "📦 你遇到了宝箱")
        self.assertEqual(player.pending_event, "mimic")
        self.assertIsNone(player.enemy)

    def test_admin_forced_major_boss_survives_panel_migration_check(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "管理员", floor=1)

        engine.force_event(player, "major_boss")
        forced_name = player.enemy.name
        engine.ensure_floor(player)

        self.assertEqual(player.enemy.boss_kind, "大 Boss")
        self.assertEqual(player.enemy.name, forced_name)
        self.assertIn(forced_name, engine.MAJOR_BOSS_NAMES.values())

    def test_admin_non_monster_events_never_create_an_enemy(self):
        for event in (
            "chest", "mimic", "fountain", "merchant", "fairy", "mystery",
            "treasure_map", "trapped_beast", "wishing_well", "empty",
        ):
            with self.subTest(event=event):
                engine = GameEngine(random.Random(1))
                player = Player(1, "管理员")

                engine.force_event(player, event)

                self.assertIsNone(player.enemy)

    def test_every_major_boss_has_a_unique_name(self):
        engine = GameEngine(random.Random(1))
        names = [engine._make_boss(floor).name for floor in range(10, 101, 10)]

        self.assertEqual(len(names), 10)
        self.assertEqual(len(set(names)), 10)

    def test_bought_mana_and_energy_potions_can_be_used(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "顾客", gold=500, mp=1, energy=1)
        engine._event_shop(player)
        player.merchant_stock = {"mana_potion": 4, "energy_potion": 4}
        engine.buy_merchant_item(player, "mana_potion")
        engine.buy_merchant_item(player, "energy_potion")

        energy = engine.use_energy_potion(player)
        mana = engine.use_mana_potion(player)

        self.assertEqual(mana.title, "💧 使用魔力药水")
        self.assertEqual(energy.title, "⚡ 使用精力药水")
        self.assertEqual(player.mp, 26)
        self.assertEqual(player.energy, 27)

    def test_bought_greater_healing_potion_is_added_and_can_be_used(self):
        engine = GameEngine(random.Random(1))
        player = Player(
            1, "顾客", floor=20, gold=500, hp=20, pending_event="merchant"
        )
        player.merchant_stock = {"greater_healing_potion": 4}

        purchase = engine.buy_merchant_item(player, "greater_healing_potion")

        self.assertEqual(purchase.title, "🛍️ 购买成功")
        self.assertEqual(player.consumables["强效治疗药水"], 1)
        self.assertLess(player.gold, 500)

        used = engine.use_potion(player)

        self.assertEqual(used.title, "🧪 使用强效治疗药水")
        self.assertEqual(player.hp, 80)
        self.assertEqual(player.consumables["强效治疗药水"], 0)

    def test_deep_floor_can_offer_and_use_greater_energy_potion(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "深层勇者", floor=30, energy=0)
        player.consumables = {"强效精力药水": 1}

        result = engine.use_energy_potion(player)

        self.assertEqual(result.title, "⚡ 使用强效精力药水")
        self.assertEqual(player.energy, 58)
        self.assertEqual(player.consumables["强效精力药水"], 0)

    def test_greater_mana_potion_can_be_used(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "法师", mp=0, energy=10)
        player.consumables = {"强效魔力药水": 1}

        result = engine.use_mana_potion(player)

        self.assertEqual(result.title, "💧 使用强效魔力药水")
        self.assertEqual(player.mp, 50)
        self.assertEqual(player.energy, 8)

    def test_floor_one_hundred_gold_rewards_use_one_third_old_curve(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "经济测试", floor=100, gold=0)
        player.enemy = Enemy("木桩", 1, 1, 1, 0)

        result = engine.attack(player)

        self.assertEqual(result.title, "🎉 战斗胜利")
        self.assertLessEqual(player.gold, 475)
        self.assertGreater(player.gold, 110)

    def test_death_retains_exactly_two_consumable_units(self):
        engine = GameEngine(random.Random(1))
        player = Player(1, "冒险者", hp=1)
        player.consumables = {"治疗药水": 5, "魔力药水": 4, "精力药水": 3}
        before = sum(player.consumables.values())
        player.enemy = Enemy("危险木桩", 9999, 9999, 999, 0)

        result = engine.attack(player)

        after = sum(player.consumables.values())
        self.assertTrue(result.death)
        self.assertEqual(result.title, "💀 你死了")
        self.assertEqual(after, 2)
        self.assertLess(after, before)


if __name__ == "__main__":
    unittest.main()
