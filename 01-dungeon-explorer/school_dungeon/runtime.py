from __future__ import annotations

import asyncio
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from .game.engine import GameEngine, GameResult
from .game.formatting import format_number
from .game.fortune_link import sync_daily_fortune
from .game.models import Enemy, Player
from .game.shop import RARITY_EMOJI, ShopItem, daily_stock, purchase
from .game.crystal import (
    CRYSTAL_EXCHANGE_COST,
    CRYSTAL_RARITY_EMOJI,
    CRYSTAL_RARITY_WEIGHTS,
    CRYSTAL_REWARDS,
    crystal_charm_values_text,
    equip_crystal_reward,
    exchange_crystals,
)
from .game.equipment import ensure_equipment_inventory, equip_from_inventory
from .game.storage import PlayerStore
from .game.school_content import FINAL_BOSS_ALIAS, MERCHANT_NAME, floor_label, zone_for_floor
from .game.daily_quests import (
    claim_all,
    completed_unclaimed,
    progress as quest_progress,
    quests_for,
    record_action as record_daily_quest_action,
    sync_daily_quests,
)

PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT.parent / ".env")
engine = GameEngine()
store = PlayerStore(PROJECT_ROOT / "data" / "school_dungeon.db")
TAVERN_IMAGE = Path(__file__).parent / "assets" / "adventurer-tavern-chibi-hq.jpg"
CAVE_IMAGE = Path(__file__).parent / "assets" / "school-entrance.png"
FLOOR_SCENE_DIR = Path(__file__).parent / "assets" / "floors"
GOLD_SHOP_IMAGE = Path(__file__).parent / "assets" / "gold-shop-banner.jpg"
CRYSTAL_SHOP_IMAGE = Path(__file__).parent / "assets" / "crystal-exchange-banner.jpg"
FORTUNE_DRAWS_FILE = Path(os.getenv(
    "FORTUNE_DRAWS_FILE",
    (
        "/opt/fortune-bot/data/fortune_draws.json"
        if os.name != "nt"
        else str(Path(__file__).parent.parent / "data" / "fortune_draws.json")
    ),
))
views_added = False
titles_backfilled = False
HOST_ENTRANCE_PANEL_FACTORY = None
HOST_PLAYER_STORE = None
ICE_SOUL_BLUE = 0x4A90E2
FROST_SNOW_BLUE = 0xE6F7FF
ADVENTURER_ROLES = {
    1: ("❄️ 一星学生", ICE_SOUL_BLUE, FROST_SNOW_BLUE),
    2: ("❄️ 二星学生", 0x18B8D8, 0xBDF6FF),
    3: ("❄️ 三星学生", 0x246BFD, 0x8FC7FF),
    4: ("❄️ 四星学生", 0x054ACB, 0x73A9FF),
    5: ("❄️ 优秀学生", 0x0A254A, 0x4F9AD6),
}
ADVENTURER_ROLE_NAMES = {spec[0] for spec in ADVENTURER_ROLES.values()}
DUNGEON_ADVENTURER_ROLE_NAME = "🏫 诡异学园学生"
DUNGEON_ONE_NAME = "地下城一｜幽灯岩窟"
DUNGEON_TWO_NAME = "地下城二｜永不下课的学园"


def active_adventure_names(user_id: int, name: str) -> tuple[str, ...]:
    """返回玩家仍未结束的冒险；兼容修复前可能同时存在的两份进度。"""
    active: list[str] = []
    if HOST_PLAYER_STORE is not None:
        host_player = HOST_PLAYER_STORE.get(user_id, name)
        if host_player.is_adventuring:
            active.append(DUNGEON_ONE_NAME)
    school_player = store.get(user_id, name)
    if school_player.is_adventuring:
        active.append(DUNGEON_TWO_NAME)
    return tuple(active)


def active_adventure_text(active: tuple[str, ...]) -> str:
    return "、".join(f"**{item}**" for item in active)


async def reject_tavern_service(
    interaction: discord.Interaction,
    service_name: str,
) -> bool:
    active = active_adventure_names(
        interaction.user.id,
        interaction.user.display_name,
    )
    if not active:
        return False
    await interaction.response.send_message(
        f"⚔️ 你仍身处 {active_adventure_text(active)}，无法使用{service_name}。"
        "请先结束当前冒险并返回酒馆。",
        ephemeral=True,
    )
    return True


def bar(value: int, maximum: int, width: int = 10) -> str:
    filled = round(width * value / maximum) if maximum else 0
    return "▰" * filled + "▱" * (width - filled)


def display_number(value: int | float) -> str:
    return format_number(value)


def today_key() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def sync_player_fortune(player: Player, guild_id: int | None) -> int:
    return sync_daily_fortune(player, guild_id, FORTUNE_DRAWS_FILE)


def fortune_status_text(player: Player) -> str:
    if player.daily_fortune_score <= 0:
        return "🪷 今日尚未问卦｜新生谢礼水晶概率增长 **0%**"
    if player.daily_fortune_growth <= 0:
        return f"🪷 今日总运 **{player.daily_fortune_score}/100**｜卦气平稳"
    return (
        f"🪷 今日总运 **{player.daily_fortune_score}/100**｜"
        f"新生谢礼与藏宝图水晶概率增长 **{player.daily_fortune_growth:.0%}**"
    )


def weekly_ranking_embed() -> discord.Embed:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    monday = now.date() - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    rows = store.weekly_top(15, now)
    if rows:
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = [
            f"{medals.get(rank, '🏅')} **TOP{rank}**｜"
            f"<@{user_id}>（{discord.utils.escape_markdown(name)}）"
            f"｜第 **{floor}** 层"
            for rank, (user_id, name, floor) in enumerate(rows, 1)
        ]
        description = "\n".join(lines)
    else:
        description = "本周还没有学生留下挑战记录。"
    embed = discord.Embed(
        title="🏫 永不下课的学园｜每周挑战层数排行",
        description=description,
        color=ICE_SOUL_BLUE,
    )
    embed.set_footer(
        text=(
            f"统计周期：{monday:%Y-%m-%d} ～ {sunday:%Y-%m-%d}（北京时间）"
            "｜每周六自动更新"
        )
    )
    return embed


async def award_adventurer_title(
    member: discord.Member,
    completion_count: int,
) -> tuple[str, discord.Role | None]:
    guild = member.guild
    tier = min(5, max(1, completion_count))
    role_name, primary_colour, secondary_colour = ADVENTURER_ROLES[tier]
    role = discord.utils.get(guild.roles, name=role_name)
    try:
        gradient_enabled = "ENHANCED_ROLE_COLORS" in guild.features
        color_kwargs: dict[str, discord.Colour] = {
            "colour": discord.Colour(primary_colour),
        }
        if gradient_enabled:
            color_kwargs["secondary_colour"] = discord.Colour(secondary_colour)
        if role is None:
            role = await guild.create_role(
                name=role_name,
                **color_kwargs,
                hoist=True,
                reason=f"幽灯岩窟第 {completion_count} 次百层通关奖励",
            )
        elif guild.me and role < guild.me.top_role:
            role = await role.edit(
                **color_kwargs,
                hoist=True,
                reason="更新百层通关进阶称号配色",
            )
        if guild.me and role >= guild.me.top_role:
            return (
                f"称号 {role.mention} 已建立，但它高于 Bot 身份组，暂时无法装备。",
                role,
            )
        previous_roles = [
            owned_role
            for owned_role in member.roles
            if owned_role.name in ADVENTURER_ROLE_NAMES and owned_role != role
        ]
        if role not in member.roles:
            await member.add_roles(
                role,
                reason=f"幽灯岩窟第 {completion_count} 次百层通关",
            )
        removable_roles = [
            old_role
            for old_role in previous_roles
            if not guild.me or old_role < guild.me.top_role
        ]
        if removable_roles:
            await member.remove_roles(
                *removable_roles,
                reason=f"晋升为 {role_name}",
            )
        if role in member.roles and not previous_roles:
            return f"你已经拥有彩色称号 {role.mention}。", role
        return f"已晋升并授予彩色称号 {role.mention}。", role
    except discord.Forbidden:
        return (
            f"通关记录已保存，但我没有权限授予 **{role_name}**。"
            "请给 Bot“管理身份组”权限，并确保 Bot 身份组位于奖励身份组上方。",
            role,
        )
    except discord.HTTPException as error:
        return f"通关记录已保存，但身份组发放失败：{error}", role


async def backfill_adventurer_titles() -> None:
    """按现有存档为老玩家补发当前最高的百层通关称号。"""
    guild_id = os.getenv("TEST_GUILD_ID") or os.getenv("GUILD_ID")
    guild = bot.get_guild(int(guild_id)) if guild_id else None
    if guild is None and len(bot.guilds) == 1:
        guild = bot.guilds[0]
    if guild is None:
        print("无法确定服务器，暂未补发学生通关称号。")
        return
    awarded = 0
    skipped = 0
    for user_id, completion_count in store.completed_players():
        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        except discord.NotFound:
            skipped += 1
            continue
        except discord.HTTPException as error:
            print(f"补发学生称号时无法读取成员 {user_id}：{error}")
            skipped += 1
            continue
        status, role = await award_adventurer_title(member, completion_count)
        if role and role in member.roles:
            skipped += 1
        elif role:
            awarded += 1
        else:
            skipped += 1
        print(f"学生称号核对 {user_id}：{status}")
    print(f"学生称号补发完成：处理 {awarded} 人，跳过或已拥有 {skipped} 人。")


async def ensure_dungeon_adventurer_role(
    guild: discord.Guild,
) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=DUNGEON_ADVENTURER_ROLE_NAME)
    try:
        if role is None:
            role = await guild.create_role(
                name=DUNGEON_ADVENTURER_ROLE_NAME,
                colour=discord.Colour.default(),
                hoist=False,
                mentionable=False,
                reason="标记实际参与过诡异学园的学生",
            )
            try:
                role = await role.edit(
                    position=1,
                    reason="将诡异学园学生后台身份组放在最下方",
                )
            except discord.HTTPException:
                pass
        if guild.me and role >= guild.me.top_role:
            print(
                f"{DUNGEON_ADVENTURER_ROLE_NAME} 高于 Bot 身份组，暂时无法自动分配。"
            )
            return None
        return role
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"创建诡异学园学生身份组失败：{error}")
        return None


async def assign_dungeon_adventurer_role(member: discord.Member) -> bool:
    role = await ensure_dungeon_adventurer_role(member.guild)
    if role is None:
        return False
    if role in member.roles:
        return True
    try:
        await member.add_roles(role, reason="首次进入幽灯岩窟")
        return True
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"为成员 {member.id} 添加诡异学园学生身份组失败：{error}")
        return False


async def backfill_dungeon_adventurer_roles() -> None:
    guild_id = os.getenv("TEST_GUILD_ID") or os.getenv("GUILD_ID")
    guild = bot.get_guild(int(guild_id)) if guild_id else None
    if guild is None and len(bot.guilds) == 1:
        guild = bot.guilds[0]
    if guild is None:
        print("无法确定服务器，暂未补发诡异学园学生后台身份组。")
        return
    role = await ensure_dungeon_adventurer_role(guild)
    if role is None:
        return
    assigned = 0
    for user_id in store.player_ids():
        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        except discord.NotFound:
            continue
        except discord.HTTPException as error:
            print(f"补发诡异学园学生身份组时无法读取成员 {user_id}：{error}")
            continue
        if role in member.roles:
            continue
        try:
            await member.add_roles(role, reason="按地下城存档补发后台身份组")
            assigned += 1
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"补发诡异学园学生身份组给 {user_id} 失败：{error}")
    print(f"诡异学园学生后台身份组补发完成：新增 {assigned} 人。")


def completion_celebration_copy(completion_count: int) -> tuple[str, str]:
    if completion_count == 1:
        return (
            "### “……恭喜，看起来你也不是想象中的那么弱嘛……这个给你。\n"
            "这是百层通关的勋章和奖励。下次再接再厉吧，"
            "我会一直关注你的。”\n"
            "——by **酒馆老板小小秦** 🥂❄️",
            "🎊 第一次百层学园探索完成，新的传说从酒馆开始！",
        )
    if completion_count == 2:
        return (
            "### “第二次从王座走回来了？看来第一次并不是运气。\n"
            "收下这枚更明亮的冰晶吧——从今天起，大家会记住你的名字。”\n"
            "——by **酒馆老板小小秦** 🥂🧊",
            "✨ 第二次百层学园探索完成，你已晋升为二星学生！",
        )
    if completion_count == 3:
        return (
            "### “三次踏过同一场风雪，还能带着笑回来……真了不起。\n"
            "幽灯岩窟已经无法埋没你的光芒，这份三星荣誉属于你。”\n"
            "——by **酒馆老板小小秦** 🥂💠",
            "💠 第三次百层学园探索完成，你的冒险传说愈发耀眼！",
        )
    if completion_count == 4:
        return (
            "### “第四次百层凯旋。现在，就连岩窟深处的怪物也会畏惧你的脚步。\n"
            "接下这枚深蓝勋章吧——距离优秀学生，只差最后一次证明。”\n"
            "——by **酒馆老板小小秦** 🥂🌊",
            "🌊 第四次百层学园探索完成，最终晋升试炼已经开启！",
        )
    if completion_count == 5:
        return (
            "### “五次百层学园探索，五次平安归来。你已经不再是追逐传说的人——\n"
            "从这一刻起，你就是传说本身。欢迎回来，优秀学生。”\n"
            "——by **酒馆老板小小秦** 🥂🏅",
            "🏅 第五次百层学园探索完成，正式晋升为优秀学生！",
        )
    return (
        f"### “第 {completion_count} 次凯旋，酒馆的灯依然为你亮着。\n"
        "真正的求学没有终点——欢迎回来，学生。”\n"
        "——by **酒馆老板小小秦** 🥂❄️",
        f"❄️ 第 {completion_count} 次百层学园探索完成，新的征途仍在继续！",
    )


async def update_weekly_ranking(*, force: bool = False) -> bool:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if not force and now.weekday() != 5:
        return False
    channel_id = os.getenv("DUNGEON_RANKING_CHANNEL_ID") or store.get_setting(
        "weekly_ranking_channel_id"
    )
    if not channel_id:
        channel = await ensure_weekly_ranking_channel()
        if channel is None:
            return False
        channel_id = str(channel.id)
    try:
        channel = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
        message_id = store.get_setting("weekly_ranking_message_id")
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(embed=weekly_ranking_embed())
                return True
            except (discord.NotFound, discord.Forbidden):
                pass
        message = await channel.send(embed=weekly_ranking_embed())
        store.set_setting("weekly_ranking_message_id", message.id)
        return True
    except (ValueError, OSError, discord.HTTPException) as error:
        print(f"每周挑战排行发布失败：{error}")
        return False


async def ensure_weekly_ranking_channel() -> discord.TextChannel | None:
    configured_id = os.getenv("DUNGEON_RANKING_CHANNEL_ID") or store.get_setting(
        "weekly_ranking_channel_id"
    )
    if configured_id:
        try:
            channel = bot.get_channel(int(configured_id)) or await bot.fetch_channel(
                int(configured_id)
            )
            if isinstance(channel, discord.TextChannel):
                return channel
        except (ValueError, discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
    guild_id = os.getenv("TEST_GUILD_ID") or os.getenv("GUILD_ID")
    guild = bot.get_guild(int(guild_id)) if guild_id else None
    if guild is None:
        print("无法确定服务器，未创建每周挑战排行频道。")
        return None
    existing = discord.utils.get(guild.text_channels, name="🏆・每周挑战排行")
    if existing:
        store.set_setting("weekly_ranking_channel_id", existing.id)
        return existing
    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
            ),
        }
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                manage_messages=True,
            )
        channel = await guild.create_text_channel(
            "🏆・每周挑战排行",
            overwrites=overwrites,
            reason="地下城每周挑战 TOP15 专用频道",
            topic="幽灯岩窟每周挑战层数 TOP1～TOP15｜每周六自动更新",
        )
        store.set_setting("weekly_ranking_channel_id", channel.id)
        print(f"已创建每周挑战排行频道：{channel.id}")
        return channel
    except discord.Forbidden:
        print("创建每周挑战排行频道失败：Bot 缺少“管理频道”权限。")
    except discord.HTTPException as error:
        print(f"创建每周挑战排行频道失败：{error}")
    return None


@tasks.loop(minutes=10)
async def weekly_ranking_task() -> None:
    await update_weekly_ranking()


@weekly_ranking_task.before_loop
async def before_weekly_ranking_task() -> None:
    await bot.wait_until_ready()


def floor_scene_filename(floor: int) -> str:
    safe_floor = min(100, max(1, floor))
    return f"floor-{safe_floor:03d}.webp"


def floor_scene_file(floor: int) -> discord.File:
    filename = floor_scene_filename(floor)
    path = FLOOR_SCENE_DIR / filename
    if not path.exists():
        path = FLOOR_SCENE_DIR / "school-zone-placeholder.webp"
    return discord.File(path, filename=filename)


def inventory_embed(player: Player) -> discord.Embed:
    engine.ensure_floor(player)
    ensure_equipment_inventory(player)
    items = "\n".join(
        f"• {name} × **{count}**" for name, count in player.consumables.items() if count
    ) or "空空如也"
    embed = discord.Embed(
        title=f"🎒 {player.name} 的学生档案",
        description=(
            f"探索难度 **★{player.completion_count}**　"
            f"**Lv.{player.level}**　EXP **{player.exp}/{player.exp_required}**\n"
            f"当前位于 **第 {player.floor} 层**　探索 **{player.steps}/{player.required_steps}**"
        ),
        color=0xD89A5B,
    )
    embed.add_field(
        name="📊 当前状态",
        value=(
            f"❤️ `{bar(player.hp, player.max_hp)}` {display_number(player.hp)}/{display_number(player.max_hp)}\n"
            f"💧 `{bar(player.mp, player.max_mp)}` {display_number(player.mp)}/{display_number(player.max_mp)}\n"
            f"⚡ `{bar(player.energy, player.max_energy)}` {display_number(player.energy)}/{display_number(player.max_energy)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚔️ 当前属性",
        value=(
            f"武器：**{player.weapon}**（攻击 +{player.weapon_attack}）\n"
            f"服装：**{player.clothing}**（防御 +{player.clothing_defense}）\n"
            f"最终：攻击加成 **+{display_number(player.attack_bonus)}**｜"
            f"防御 **{display_number(player.defense)}**\n"
            f"敏捷 **{display_number(player.agility)}**｜幸运 **{display_number(player.luck)}**\n"
            f"竞赛加分：学科 ×{player.merchant_charm_base_stats.get('attack', 0)} "
            f"(**+{display_number(player.merchant_charm_bonus('attack'))}**)｜"
            f"科创 ×{player.merchant_charm_base_stats.get('defense', 0)} "
            f"(**+{display_number(player.merchant_charm_bonus('defense'))}**)\n"
            f"体育 ×{player.merchant_charm_base_stats.get('agility', 0)} "
            f"(**+{display_number(player.merchant_charm_bonus('agility'))}**)｜"
            f"人文 ×{player.merchant_charm_base_stats.get('luck', 0)} "
            f"(**+{display_number(player.merchant_charm_bonus('luck'))}**)\n"
            f"水晶护符（不衰减）：攻击 **+{display_number(player.crystal_charm_bonus('attack'))}**｜"
            f"防御 **+{display_number(player.crystal_charm_bonus('defense'))}**｜"
            f"敏捷 **+{display_number(player.crystal_charm_bonus('agility'))}**｜"
            f"幸运 **+{display_number(player.crystal_charm_bonus('luck'))}**\n"
            f"水晶护符抽取 **{player.crystal_charm_draw_count} 次**｜"
            f"属性次数：攻 {player.crystal_charm_stat_counts.get('attack', 0)}／"
            f"防 {player.crystal_charm_stat_counts.get('defense', 0)}／"
            f"敏 {player.crystal_charm_stat_counts.get('agility', 0)}／"
            f"幸 {player.crystal_charm_stat_counts.get('luck', 0)}"
        ),
        inline=True,
    )
    embed.add_field(name="🎒 道具栏", value=items, inline=True)
    embed.add_field(
        name="💰 钱袋",
        value=f"🪙 金币 **{player.gold}**\n🔮 魔法水晶 **{player.crystals}**",
        inline=True,
    )
    embed.add_field(name="🪷 今日卦运联动", value=fortune_status_text(player), inline=False)
    embed.set_footer(text="使用酒馆里的“学生物品栏”可随时切换已经获得的物品。")
    return embed


def event_section(title: str, has_enemy: bool) -> str:
    if has_enemy:
        return "👾 敌影出现"
    if any(word in title for word in ("宝箱", "书包", "储物柜")):
        return "📦 宝藏出现"
    if "泉水" in title or "校医室" in title:
        return "⛲ 奇遇出现"
    if "商人" in title:
        return "🧳 商人出现"
    if "精灵" in title or "新生" in title:
        return "🧑‍🎓 新生出现"
    if "石像" in title or "荣誉榜" in title:
        return "🗿 神秘物体出现"
    if "藏宝图" in title or "地图" in title or "答案纸" in title:
        return "🗺️ 隐藏路线出现"
    if "妖兽" in title or "吉祥物" in title:
        return "🐺 受困生物出现"
    if "许愿井" in title or "愿望" in title or "许愿树" in title:
        return "🪙 许愿事件出现"
    if any(word in title for word in ("陷阱", "落石", "偷袭", "背包")):
        return "🪤 意外发生"
    return "🧭 探索记录"


def player_panel_text(player: Player, result: GameResult | None) -> tuple[str, str]:
    title = result.title if result else "🧭 正在探索"
    message = result.message if result else "你小心翼翼地观察着四周……"
    event = f"# {title}\n{message}"
    if player.enemy:
        enemy = player.enemy
        alias = f"｜别名：{enemy.alias}" if enemy.alias else ""
        event += (
            f"\n\n## {event_section(title, True)}\n"
            f"### {enemy.boss_kind}｜{enemy.name}{alias}\n> “{enemy.catchphrase}”\n"
            f"❤️ 生命　`{bar(enemy.hp, enemy.max_hp)}` **{display_number(enemy.hp)}/{display_number(enemy.max_hp)}**\n"
            f"⚔️ 攻击　`{bar(enemy.attack, max(1, enemy.attack + 10))}` **{enemy.attack}**\n"
            f"☠️ 等级　`{bar(enemy.level, max(10, player.floor + 10))}` **Lv.{enemy.level}**"
        )
        if player.pending_quiz:
            quiz = player.pending_quiz
            letters = "ABCD"
            option_lines = "\n".join(
                f"> **{letters[index]}.** {option}"
                for index, option in enumerate(quiz["options"])
            )
            event += (
                f"\n\n## 📝 {quiz['subject']}限时题\n"
                f"### {quiz['prompt']}\n{option_lines}\n"
                f"-# 必须在 <t:{int(float(quiz['deadline']))}:R> 作答；超时按错误处理。"
            )
    else:
        event += f"\n\n## {event_section(title, False)}"
    status = (
        f"## 🧑‍🎓 学生｜{player.name}\n"
        f"探索难度 **★{player.completion_count}**　"
        f"**Lv.{player.level}**　EXP **{player.exp}/{player.exp_required}**　"
        f"🗡️ 攻击 **{8 + player.level * 2}～{12 + player.level * 3} "
        f"+ {display_number(player.attack_bonus)}**\n"
        "🔮 学识火花 **×1.20/6精神力**　灵感光矢 **×1.50/12精神力**　真理星雨 **×1.85/22精神力**\n"
        f"❤️ `{bar(player.hp, player.max_hp)}` **{display_number(player.hp)}/{display_number(player.max_hp)}**\n"
        f"💧 `{bar(player.mp, player.max_mp)}` **{display_number(player.mp)}/{display_number(player.max_mp)}**\n"
        f"⚡ `{bar(player.energy, player.max_energy)}` **{display_number(player.energy)}/{display_number(player.max_energy)}**\n\n"
        f"## 🎒 行囊\n"
        f"🪙 **{player.gold}**　🔮 **{player.crystals}**　"
        f"⚔️ **{player.weapon} +{player.weapon_attack}**　👕 **{player.clothing}**\n"
        f"🛡️ 防御 **{display_number(player.defense)}**　💨 敏捷 **{display_number(player.agility)}**　🍀 幸运 **{display_number(player.luck)}**\n"
        f"🏅 竞赛加分：学科 ×{player.merchant_charm_base_stats.get('attack', 0)} "
        f"(+{display_number(player.merchant_charm_bonus('attack'))})｜"
        f"科创 ×{player.merchant_charm_base_stats.get('defense', 0)} "
        f"(+{display_number(player.merchant_charm_bonus('defense'))})｜"
        f"体育 ×{player.merchant_charm_base_stats.get('agility', 0)} "
        f"(+{display_number(player.merchant_charm_bonus('agility'))})｜"
        f"人文 ×{player.merchant_charm_base_stats.get('luck', 0)} "
        f"(+{display_number(player.merchant_charm_bonus('luck'))})\n"
        f"💎 水晶护符（不衰减）：攻击 +{display_number(player.crystal_charm_bonus('attack'))}｜"
        f"防御 +{display_number(player.crystal_charm_bonus('defense'))}｜"
        f"敏捷 +{display_number(player.crystal_charm_bonus('agility'))}｜"
        f"幸运 +{display_number(player.crystal_charm_bonus('luck'))}｜"
        f"抽取 {player.crystal_charm_draw_count} 次\n"
        f"{fortune_status_text(player)}\n"
        f"🥛 学生牛奶 **×{player.consumables.get('学生牛奶', 0)}**　"
        f"🍱 校园营养餐 **×{player.consumables.get('校园营养餐', 0)}**\n"
        f"🧴 清凉油 **×{player.consumables.get('清凉油', 0)}**　"
        f"🍬 强劲薄荷糖 **×{player.consumables.get('强劲薄荷糖', 0)}**\n"
        f"🥤 运动饮料 **×{player.consumables.get('运动饮料', 0)}**　"
        f"🧠 安神补脑液 **×{player.consumables.get('安神补脑液', 0)}**\n"
        f"👣 探索 **{player.steps}/{player.required_steps}**\n"
        "-# 探索消耗 3 精力｜互动消耗 2 精力｜超常发挥 ×1.5"
    )
    return event, status


class DungeonActionButton(discord.ui.Button):
    def __init__(self, action: str, label: str, emoji: str, style: discord.ButtonStyle):
        super().__init__(
            label=label, emoji=emoji, style=style,
            custom_id=f"school_dungeon:action:{action}",
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        if isinstance(panel, DungeonPanel):
            await panel.run_action(interaction, self.action)


class DungeonActions(discord.ui.ActionRow):
    def __init__(self, player: Player):
        buttons: list[discord.ui.Button] = []
        if player.pending_quiz:
            letters = "ABCD"
            for index, option in enumerate(player.pending_quiz["options"]):
                buttons.append(DungeonActionButton(
                    f"quiz_answer_{index}",
                    f"{letters[index]}. {str(option)[:68]}",
                    "📝",
                    discord.ButtonStyle.secondary,
                ))
        elif player.enemy:
            buttons.extend([
                DungeonActionButton("attack", "普通攻击", "⚔️", discord.ButtonStyle.danger),
                DungeonActionButton("skill_minor", "学识火花·6精神力", "✨", discord.ButtonStyle.primary),
                DungeonActionButton("skill_medium", "灵感光矢·12精神力", "🔷", discord.ButtonStyle.primary),
                DungeonActionButton("skill_major", "真理星雨·22精神力", "🌠", discord.ButtonStyle.danger),
            ])
        elif not player.pending_event:
            buttons.append(DungeonActionButton("explore", "继续探索", "👣", discord.ButtonStyle.primary))
        pending_buttons = {
            "chest": ("interact_event", "打开储物柜", "🗄️"),
            "mimic": ("interact_event", "打开书包", "🎒"),
            "fountain": ("interact_event", "在校医室休息", "🏥"),
            "merchant": ("merchant_menu", "查看商品", "🧳"),
            "fairy": ("interact_event", "帮助新生", "🧑‍🎓"),
            "mystery": ("interact_event", "触碰荣誉榜", "🏅"),
            "treasure_map": ("interact_event", "跟随答案纸", "📄"),
            "trapped_beast": ("interact_event", "解救吉祥物", "🐾"),
            "wishing_well": ("interact_event", "系上许愿签", "🌳"),
        }
        if player.pending_event in pending_buttons:
            action, label, emoji = pending_buttons[player.pending_event]
            buttons.append(DungeonActionButton(action, label, emoji, discord.ButtonStyle.success))
        super().__init__(*buttons[:5])


DECLINABLE_EVENTS = {
    "chest", "mimic", "merchant", "fairy", "mystery",
    "treasure_map", "trapped_beast", "wishing_well",
}


class DungeonDeclineActions(discord.ui.ActionRow):
    def __init__(self, player: Player):
        leave_label = (
            "不打开，悄悄离开"
            if player.pending_event in {"chest", "mimic"}
            else "婉拒／离开"
        )
        super().__init__(DungeonActionButton(
            "decline_event", leave_label, "🚶", discord.ButtonStyle.secondary,
        ))


class DungeonUtilities(discord.ui.ActionRow):
    def __init__(self, player: Player):
        buttons = [
            DungeonActionButton("use_potion", "体力补给", "🥛", discord.ButtonStyle.success),
            DungeonActionButton("use_mana_potion", "精神力补给", "🧴", discord.ButtonStyle.success),
            DungeonActionButton("use_energy_potion", "精力补给", "🥤", discord.ButtonStyle.success),
            DungeonActionButton("refresh", "刷新", "🔄", discord.ButtonStyle.secondary),
        ]
        if (
            not player.enemy
            and player.energy < 3
            and player.consumables.get("运动饮料", 0) <= 0
            and player.consumables.get("安神补脑液", 0) <= 0
        ):
            buttons.append(DungeonActionButton(
                "request_rescue",
                "呼叫救援",
                "🛺",
                discord.ButtonStyle.danger,
            ))
        super().__init__(*buttons)


class ReturnTavernButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="返回酒馆", emoji="🍺", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        tavern_image = discord.File(TAVERN_IMAGE, filename="adventurer-tavern-chibi-hq.jpg")
        await interaction.response.edit_message(
            view=host_entrance_panel(),
            attachments=[tavern_image],
        )

class RescueChoiceButton(discord.ui.Button):
    def __init__(self, action: str, label: str, emoji: str, style: discord.ButtonStyle):
        super().__init__(label=label, emoji=emoji, style=style)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = self.view
        if isinstance(panel, DungeonPanel):
            await panel.run_action(interaction, self.action)


class DungeonPanel(discord.ui.LayoutView):
    def __init__(self, owner_id: int, player: Player, result: GameResult | None = None):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        engine.ensure_floor(player)
        if result and result.completed:
            container = discord.ui.Container(accent_colour=ICE_SOUL_BLUE)
            avatar_url = bot.user.display_avatar.url if bot.user else ""
            celebration_quote, celebration_footer = completion_celebration_copy(
                player.completion_count
            )
            title_name = result.awarded_title or GameEngine.adventurer_title(
                player.completion_count
            )
            coloured_title = result.role_mention or f"**{title_name}**"
            container.add_item(discord.ui.Section(
                "# 🎉❄️ 百层学园探索完成！❄️🎉",
                celebration_quote,
                accessory=discord.ui.Thumbnail(
                    avatar_url,
                    description="酒馆老板小小秦",
                ),
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(
                f"{result.message}\n\n"
                "## 🏅 通关荣誉\n"
                f"你已获得称号：{coloured_title}\n"
                "⚔️ 永久攻击 **+5**｜🛡️ 永久防御 **+3**\n"
                f"{celebration_footer}"
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.ActionRow(ReturnTavernButton()))
            self.add_item(container)
            return
        if result and result.death:
            container = discord.ui.Container(accent_colour=0x9B2C2C)
            avatar_url = bot.user.display_avatar.url if bot.user else ""
            container.add_item(discord.ui.Section(
                "# 💀 你死了",
                "### 啧，冒险结束了。你连自己都照顾不好吗？喝了这个……"
                "本来是要卖10000金币的，但是送给你好了\n"
                "——by **酒馆老板小小秦**",
                accessory=discord.ui.Thumbnail(
                    avatar_url,
                    description="酒馆老板小小秦",
                ),
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(result.message))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.ActionRow(
                ReturnTavernButton()
            ))
            self.add_item(container)
            return
        if result and result.escaped:
            container = discord.ui.Container(accent_colour=0xC78B46)
            container.add_item(discord.ui.TextDisplay(
                "# 🛺 鼹鼠车夫把你送回来了\n"
                f"{result.message}\n\n"
                "### 🍺 小小秦说\n"
                "> “能回来就好。下次出门前，记得检查精力补给。”"
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.ActionRow(ReturnTavernButton()))
            self.add_item(container)
            return
        if result and result.rescue_requested:
            container = discord.ui.Container(accent_colour=0xB8793A)
            container.add_item(discord.ui.TextDisplay(
                "# 🛺 精力耗尽·紧急脱困\n"
                f"{result.message}\n\n"
                "## 方案一｜鼹鼠车夫：返回酒馆\n"
                "💀 按死亡方式结算：金币减半，普通道具随机只保留两件。\n"
                "等级、经验和层数重置，装备、魔法水晶与永久加成保留。\n"
                "随后以 **Lv.1**、全状态补满，直接返回酒馆。\n\n"
                "## 方案二｜向女神祈祷：不返回酒馆\n"
                "🙏 放弃当前 **全部等级和经验**，以 **Lv.1** 回到地下城第 **1 层**。\n"
                "金币、装备和道具全部保留，体力、精神力和精力全部补满。\n\n"
                "⚠️ 两种选择确认后都不能撤销，请仔细选择。"
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.ActionRow(
                RescueChoiceButton(
                    "mole_rescue", "付给鼹鼠车夫并回酒馆", "🛺",
                    discord.ButtonStyle.danger,
                ),
                RescueChoiceButton(
                    "goddess_prayer", "向女神祈祷并重新开始", "🙏",
                    discord.ButtonStyle.primary,
                ),
            ))
            self.add_item(container)
            return
        event, status = player_panel_text(player, result)
        zone = zone_for_floor(player.floor)
        container = discord.ui.Container(accent_colour=0x6554A6)
        container.add_item(discord.ui.TextDisplay(
            f"# 🏫 永不下课的学园｜★{player.completion_count}｜第 {player.floor} / 100 层\n"
            f"### {zone.subject}｜{floor_label(player.floor)}"
        ))
        gallery = discord.ui.MediaGallery()
        gallery.add_item(
            media=f"attachment://{floor_scene_filename(player.floor)}",
            description=f"永不下课的学园第 {player.floor} 层｜{floor_label(player.floor)}",
        )
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(event))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(status))
        container.add_item(discord.ui.Separator())
        container.add_item(DungeonActions(player))
        if not player.pending_quiz:
            if player.pending_event in DECLINABLE_EVENTS:
                container.add_item(DungeonDeclineActions(player))
            container.add_item(DungeonUtilities(player))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("这不是你的面板，请使用 `/地下城二`。", ephemeral=True)
        return False

    async def run_action(self, interaction: discord.Interaction, action: str) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        sync_player_fortune(player, interaction.guild_id)
        floor_before_action = player.floor
        energy_before_action = player.energy
        gold_before_action = player.gold
        event_before_action = player.pending_event
        enemy_before_action = player.enemy
        if action == "merchant_menu":
            await interaction.response.edit_message(view=MerchantPanel(self.owner_id, player))
            return
        if action.startswith("quiz_answer_"):
            result = engine.answer_quiz(player, int(action.removeprefix("quiz_answer_")))
        elif action.startswith("skill_"):
            result = engine.attack(player, skill_tier=action.removeprefix("skill_"))
        elif action == "refresh":
            result = None
        else:
            result = getattr(engine, action)(player)
        achieved_floor = 100 if result and result.completed else max(floor_before_action, player.floor)
        newly_completed = record_daily_quest_action(
            player,
            today_key(),
            action,
            floor_before_action,
            achieved_floor,
            energy_before_action,
            gold_before_action,
            event_before_action,
            enemy_before_action,
            result.title if result else "",
        )
        if result and newly_completed:
            names = "、".join(quest.name for quest in newly_completed)
            result.message += (
                f"\n\n🎉 **每日委托已完成：{names}**\n"
                "回到酒馆点击 **今日布置作业** 即可领取奖励。"
            )
        store.record_weekly_challenge(
            interaction.user.id,
            interaction.user.display_name,
            achieved_floor,
        )
        store.save(player)
        if result and result.completed:
            await interaction.response.defer()
            await interaction.edit_original_response(
                view=DungeonPanel(self.owner_id, player, result),
                attachments=[],
            )
            if isinstance(interaction.user, discord.Member):
                try:
                    role_status, awarded_role = await asyncio.wait_for(
                        award_adventurer_title(
                            interaction.user,
                            player.completion_count,
                        ),
                        timeout=10,
                    )
                except TimeoutError:
                    awarded_role = None
                    role_status = (
                        f"身份组发放等待超时。请检查 Bot 的“管理身份组”权限，以及 "
                        f"Bot 身份组是否位于 **{GameEngine.adventurer_title(player.completion_count)}** 上方。"
                    )
            else:
                awarded_role = None
                role_status = "通关记录已保存，但身份组只能在 Discord 服务器内发放。"
            if awarded_role:
                result.role_mention = awarded_role.mention
                await interaction.edit_original_response(
                    view=DungeonPanel(self.owner_id, player, result),
                    attachments=[],
                )
            await interaction.followup.send(
                f"🎖️ {role_status}",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            view=DungeonPanel(self.owner_id, player, result),
            attachments=[] if result and result.death else [floor_scene_file(player.floor)],
        )
        if player.pending_quiz and interaction.message:
            quiz = dict(player.pending_quiz)
            asyncio.create_task(expire_boss_quiz(
                interaction.message,
                self.owner_id,
                player.name,
                str(quiz["token"]),
                float(quiz["deadline"]),
            ))


async def expire_boss_quiz(
    message: discord.Message,
    owner_id: int,
    player_name: str,
    token: str,
    deadline: float,
) -> None:
    """十秒到期后自动按答错结算；令牌避免旧计时器误伤新题。"""
    await asyncio.sleep(max(0.0, deadline - time.time() + 0.05))
    player = store.get(owner_id, player_name)
    if not player.pending_quiz or player.pending_quiz.get("token") != token:
        return
    result = engine.answer_quiz(player, None)
    store.save(player)
    try:
        await message.edit(
            view=DungeonPanel(owner_id, player, result),
            attachments=[] if result.death else [floor_scene_file(player.floor)],
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return


def merchant_table(player: Player) -> str:
    rows = engine.merchant_offers(player)
    lines = ["类别｜物品　　　　　　｜库存｜属性　　　　　　　　　｜价格"]
    for key, name, category, effect, price in rows:
        lines.append(
            f"{category:<2}｜{name:<9}｜×{player.merchant_stock.get(key, 0)}｜"
            f"{effect:<14}｜{price} 金币"
        )
    return "```text\n" + "\n".join(lines) + "```"


class MerchantSelect(discord.ui.Select):
    def __init__(self, player: Player):
        options = [
            discord.SelectOption(
                label=f"{name}（{category} ×{player.merchant_stock.get(key, 0)}）",
                value=key,
                description=f"{effect}｜{price} 金币",
                emoji={"药剂": "🧪", "护符": "🧿", "武器": "⚔️", "装备": "🛡️"}[category],
            )
            for key, name, category, effect, price in engine.merchant_offers(player)
        ]
        if not options:
            options = [discord.SelectOption(label="商品已经售罄", value="sold_out", emoji="📦")]
        super().__init__(
            placeholder="选择一件商品购买",
            options=options,
            disabled=not player.merchant_stock,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        result = engine.buy_merchant_item(player, self.values[0])
        store.save(player)
        await interaction.response.edit_message(view=MerchantPanel(interaction.user.id, player, result))


class MerchantFinishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="结束交易", emoji="✅", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        result = engine.decline_event(player)
        store.save(player)
        await interaction.response.edit_message(
            view=DungeonPanel(interaction.user.id, player, result),
            attachments=[floor_scene_file(player.floor)],
        )

class MerchantRefreshButton(discord.ui.Button):
    def __init__(self, player: Player):
        cost = engine.merchant_refresh_cost(player.floor)
        super().__init__(
            label=f"刷新全部｜{cost} 金币",
            emoji="🔄",
            style=discord.ButtonStyle.danger,
            disabled=player.merchant_refreshes >= 5,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        result = engine.refresh_merchant_stock(player)
        store.save(player)
        await interaction.response.edit_message(
            view=MerchantPanel(interaction.user.id, player, result)
        )


class MerchantMenuActions(discord.ui.ActionRow):
    def __init__(self, player: Player):
        super().__init__(MerchantRefreshButton(player), MerchantFinishButton())


class MerchantPanel(discord.ui.LayoutView):
    def __init__(self, owner_id: int, player: Player, result: GameResult | None = None):
        super().__init__(timeout=600)
        self.owner_id = owner_id
        container = discord.ui.Container(accent_colour=0xD89A5B)
        message = f"\n\n> {result.message}" if result else ""
        container.add_item(discord.ui.TextDisplay(
            f"# 🧳 旅行商人｜{MERCHANT_NAME}\n"
            f"> “上课铃还没响。要买就快一点。”——**{MERCHANT_NAME}**\n\n"
            "装备和竞赛加分库存为 1，药剂每格库存为 4。\n"
            "药剂／竞赛加分售罄：药剂 60%｜竞赛加分 25%｜装备 15%。\n"
            "装备售罄：只补药剂 70%｜竞赛加分 30%，不会连续补装备。\n"
            "也可以支付金币刷新全部四格。\n"
            "售罄补货和付费刷新共享本次相遇的 **5 次总额度**。\n"
            f"当前金币：**{player.gold}**｜刷新：**{player.merchant_refreshes}/5**"
            f"{message}\n\n{merchant_table(player)}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(MerchantSelect(player)))
        container.add_item(MerchantMenuActions(player))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("这不是你的商店菜单。", ephemeral=True)
        return False


class CaveSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="选择要进入的学园……",
            custom_id="dungeon:cave_select",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(
                label="永不下课的学园",
                value="endless_school",
                description="十科百层的异常学校 · 推荐 Lv.1",
                emoji="🏫",
            )],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        active = active_adventure_names(
            interaction.user.id,
            interaction.user.display_name,
        )
        if active and DUNGEON_TWO_NAME not in active:
            await interaction.response.send_message(
                f"⚔️ 你仍身处 {active_adventure_text(active)}，"
                f"无法立刻进入 **{DUNGEON_TWO_NAME}**。请先结束当前冒险并返回酒馆。",
                ephemeral=True,
            )
            return
        player = store.get(interaction.user.id, interaction.user.display_name)
        sync_player_fortune(player, interaction.guild_id)
        engine.ensure_floor(player)
        player.in_adventure = True
        player.gold_storage_available = False
        store.save(player)
        result = GameResult("🏫 永不下课的学园", "你推开封闭的校门，教学楼里传来本不该响起的上课铃……")
        await interaction.response.edit_message(
            content=None,
            embed=None,
            view=DungeonPanel(interaction.user.id, player, result),
            attachments=[floor_scene_file(player.floor)],
        )
        if isinstance(interaction.user, discord.Member):
            await assign_dungeon_adventurer_role(interaction.user)


class CaveSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(CaveSelect())


class AdventurerTitleSelect(discord.ui.Select):
    def __init__(self, player: Player):
        unlocked_tier = min(5, player.completion_count)
        options = [
            discord.SelectOption(
                label=ADVENTURER_ROLES[tier][0],
                value=str(tier),
                description=(
                    "第五次百层通关称号"
                    if tier == 5 else f"第 {tier} 次百层通关称号"
                ),
                emoji="❄️",
            )
            for tier in range(1, unlocked_tier + 1)
        ]
        super().__init__(
            placeholder="选择一个已解锁的学生称号……",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        tier = int(self.values[0])
        if tier > min(5, player.completion_count):
            await interaction.response.send_message(
                "这个称号尚未解锁。",
                ephemeral=True,
            )
            return
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "称号只能在 Discord 服务器内切换。",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        status, _ = await award_adventurer_title(interaction.user, tier)
        await interaction.edit_original_response(
            content=f"🎨 {status}\n你可以随时再次选择其他已解锁称号。",
            view=AdventurerTitleView(player),
        )


class AdventurerTitleView(discord.ui.View):
    def __init__(self, player: Player):
        super().__init__(timeout=300)
        self.add_item(AdventurerTitleSelect(player))


class ExploreEntranceButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="探索", emoji="🧭", style=discord.ButtonStyle.primary,
            custom_id="dungeon:open_explore",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        sync_player_fortune(player, interaction.guild_id)
        engine.ensure_floor(player)
        store.save(player)
        embed = discord.Embed(
            title="🏫 永不下课的学园",
            description=(
                "开学前夜，封闭多年的学校重新亮起了灯。\n"
                "课本、试卷与校规已经变成怪物，而第100层的期末考试正在等待。\n\n"
                "### 要进入学园探索吗？"
            ),
            color=0x8B8FE8,
        )
        embed.set_image(url="attachment://school-entrance.png")
        cave_image = discord.File(CAVE_IMAGE, filename="school-entrance.png")
        await interaction.response.send_message(
            embed=embed, file=cave_image, view=CaveSelectionView(), ephemeral=True,
        )


class GoldStorageModal(discord.ui.Modal):
    def __init__(self, action: str):
        title = "存入金币" if action == "deposit" else "取出金币"
        super().__init__(title=title)
        self.action = action
        self.amount = discord.ui.TextInput(
            label="金币数量",
            placeholder="请输入正整数",
            required=True,
            max_length=12,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if await reject_tavern_service(interaction, "储值商人"):
            return
        player = store.get(interaction.user.id, interaction.user.display_name)
        try:
            amount = int(str(self.amount.value).strip())
        except ValueError:
            await interaction.response.send_message("请输入有效的正整数。", ephemeral=True)
            return
        result = (
            engine.deposit_gold(player, amount)
            if self.action == "deposit"
            else engine.withdraw_gold(player, amount)
        )
        store.save(player)
        await interaction.response.send_message(
            f"**{result.title}**\n{result.message}\n\n"
            f"随身金币：🪙 **{player.gold}**｜已储存：🏦 **{player.stored_gold}**",
            ephemeral=True,
        )


class GoldStorageActionButton(discord.ui.Button):
    def __init__(self, action: str):
        super().__init__(
            label="存入" if action == "deposit" else "取出",
            emoji="📥" if action == "deposit" else "📤",
            style=(
                discord.ButtonStyle.success
                if action == "deposit"
                else discord.ButtonStyle.secondary
            ),
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(GoldStorageModal(self.action))


class GoldStorageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(GoldStorageActionButton("deposit"))
        self.add_item(GoldStorageActionButton("withdraw"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return not await reject_tavern_service(interaction, "储值商人")


class GoldStorageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="储值商人", emoji="🏦", style=discord.ButtonStyle.secondary,
            custom_id="dungeon:gold_storage",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if await reject_tavern_service(interaction, "储值商人"):
            return
        player = store.get(interaction.user.id, interaction.user.display_name)
        await interaction.response.send_message(
            "# 🏦 酒馆储值商人\n"
            "这里只保管金币，不收手续费，也不产生利息。\n\n"
            f"随身金币：🪙 **{player.gold}**｜已储存：🏦 **{player.stored_gold}**",
            view=GoldStorageView(),
            ephemeral=True,
        )


class ComingSoonButton(discord.ui.Button):
    def __init__(self, label: str, emoji: str, custom_id: str, currency: str):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary, custom_id=custom_id)
        self.currency = currency

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"{self.currency}功能将在下一阶段开放。", ephemeral=True
        )


def gold_shop_products_text(stock: list[ShopItem]) -> str:
    equipment = [item for item in stock if item.category in {"武器", "护具"}]
    consumables = [item for item in stock if item.category == "道具"]

    def line(item: ShopItem) -> str:
        rarity = f"{RARITY_EMOJI[item.rarity]} **[{item.rarity}] {item.name}**"
        return f"{rarity}\n> {item.stat_text}｜🪙 **{item.price}**"

    return (
        "## ⚔️ 今日装备\n"
        + "\n".join(line(item) for item in equipment)
        + "\n\n## 🧪 今日道具\n"
        + "\n".join(line(item) for item in consumables)
    )


class GoldShopSelect(discord.ui.Select):
    def __init__(self, stock: list[ShopItem]):
        super().__init__(
            placeholder="选择要购买的商品……",
            options=[
                discord.SelectOption(
                    label=f"[{item.rarity}] {item.name}",
                    value=item.key,
                    description=f"{item.stat_text}｜{item.price} 金币",
                    emoji=RARITY_EMOJI[item.rarity],
                )
                for item in stock
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        stock = daily_stock(today_key())
        item = next((entry for entry in stock if entry.key == self.values[0]), None)
        if not item:
            result = "商城已经跨日刷新，请重新打开金币商城。"
        else:
            _, result = purchase(player, item)
            store.save(player)
        await interaction.response.edit_message(
            view=GoldShopPanel(interaction.user.id, player, result)
        )


class GoldShopPanel(discord.ui.LayoutView):
    def __init__(self, owner_id: int, player: Player, result: str | None = None):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        stock = daily_stock(today_key())
        container = discord.ui.Container(accent_colour=0xE0A12B)
        container.add_item(discord.ui.Section(
            "# 🪙 诡异学园金币商店",
            "### 只收金币，不收眼泪；买完不退，哭也没用。\n——by **酒馆老板小小秦**",
            accessory=discord.ui.Thumbnail(
                bot.user.display_avatar.url,
                description="地下城探索 Bot",
            ),
        ))
        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(
            media="attachment://gold-shop-banner.jpg",
            description="今日金币商城",
        )
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
        result_text = f"\n\n> {result}" if result else ""
        container.add_item(discord.ui.TextDisplay(
            "## 📖 属性怎么算？\n"
            "⚔️ **攻击**：直接加进每次普通攻击和招式伤害。\n"
            "🛡️ **防御**：怪物反击伤害 − 防御；随机事件还会额外减去 `防御 ÷ 3`。\n"
            "💨 **敏捷**：每点提供 **1.5% 闪避**（最高 35%）；"
            "随机事件损失再减去 `敏捷 ÷ 2`。\n"
            "🍀 **幸运**：每点增加 **0.5% 超常发挥、1.5% 战后额外掉落、"
            "1.5% 真宝箱概率**；宝箱金币每点 +3%，额外校园补给概率每点 +2%。\n"
            "> 真宝箱基础概率 62.5%，最高 90%；各项概率均有上限，计算结果向下取整。\n"
            "🏫 **装备归属：地下城二**｜本店武器、护具只能在地下城二装备和使用，不能带入地下城一。\n"
            f"当前金币：🪙 **{player.gold}**｜今日日期：**{today_key()}**\n"
            "可连续选择商品购买；全部买完后，再点击下方的 **返回酒馆**。"
            f"{result_text}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(gold_shop_products_text(stock)))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(GoldShopSelect(stock)))
        container.add_item(discord.ui.ActionRow(ReturnTavernButton()))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("这不是你的金币商城面板。", ephemeral=True)
            return False
        return not await reject_tavern_service(interaction, "金币商店")


class GoldShopButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="金币商店", emoji="🪙", style=discord.ButtonStyle.secondary,
            custom_id="dungeon:coin_shop",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if await reject_tavern_service(interaction, "金币商店"):
            return
        player = store.get(interaction.user.id, interaction.user.display_name)
        shop_image = discord.File(GOLD_SHOP_IMAGE, filename="gold-shop-banner.jpg")
        await interaction.response.send_message(
            view=GoldShopPanel(interaction.user.id, player),
            file=shop_image,
            ephemeral=True,
        )

def crystal_rewards_text() -> str:
    lines = []
    for rarity in ("优良", "稀有", "黄金", "传说"):
        examples = [item.name for item in CRYSTAL_REWARDS if item.rarity == rarity]
        lines.append(
            f"{CRYSTAL_RARITY_EMOJI[rarity]} **{rarity}｜"
            f"{CRYSTAL_RARITY_WEIGHTS[rarity]}%**　"
            + "、".join(examples[:3])
            + f"……（共 **{len(examples)}** 件）"
        )
    return "\n".join(lines)


class CrystalExchangeButton(discord.ui.Button):
    def __init__(self, count: int, style: discord.ButtonStyle):
        super().__init__(
            label=f"砸 {count} 次｜{CRYSTAL_EXCHANGE_COST * count} 水晶",
            emoji={1: "🔨", 5: "💥", 10: "🌠"}[count],
            style=style,
        )
        self.count = count

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        ok, result, rewards = exchange_crystals(player, count=self.count)
        store.save(player)
        rarity_order = {"优良": 0, "稀有": 1, "黄金": 2, "传说": 3}
        highest_rarity = (
            max((reward.rarity for reward in rewards), key=rarity_order.get)
            if ok and rewards else None
        )
        await interaction.response.edit_message(
            view=CrystalExchangePanel(
                interaction.user.id,
                player,
                result,
                result_rarity=highest_rarity,
            )
        )

class CrystalEquipmentSelect(discord.ui.Select):
    def __init__(self, player: Player):
        owned = [
            item for item in CRYSTAL_REWARDS
            if player.crystal_equipment.get(item.key, 0) > 0
            and item.category in {"武器", "护具"}
        ]
        options = [
            discord.SelectOption(
                label=f"[{item.rarity}] {item.name}",
                value=item.key,
                description=f"{item.category}｜{item.stat_text}",
                emoji=CRYSTAL_RARITY_EMOJI[item.rarity],
            )
            for item in owned
        ]
        if not options:
            options = [discord.SelectOption(label="尚未获得秘藏装备", value="none", emoji="📦")]
        super().__init__(
            placeholder="从秘藏装备栏选择装备……",
            options=options,
            disabled=not owned,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        _, result = equip_crystal_reward(player, self.values[0])
        store.save(player)
        await interaction.response.edit_message(
            view=CrystalExchangePanel(interaction.user.id, player, result)
        )


class CrystalExchangePanel(discord.ui.LayoutView):
    def __init__(
        self,
        owner_id: int,
        player: Player,
        result: str | None = None,
        result_rarity: str | None = None,
    ):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        accent_colours = {
            "优良": 0x4FAF67,
            "稀有": 0x4E8BD8,
            "黄金": 0xD69B32,
            "传说": 0xA84FD9,
        }
        container = discord.ui.Container(
            accent_colour=accent_colours.get(result_rarity, 0x7846B8)
        )
        container.add_item(discord.ui.Section(
            "# 🔮 神秘研究社库藏",
            "### “水晶会选择自己的主人。至于抽到什么……命运可不接受退货。”\n"
            "——by **神秘研究社社长**",
            accessory=discord.ui.Thumbnail(
                bot.user.display_avatar.url,
                description="水晶兑换",
            ),
        ))
        if CRYSTAL_SHOP_IMAGE.exists():
            container.add_item(discord.ui.Separator())
            gallery = discord.ui.MediaGallery()
            gallery.add_item(
                media="attachment://crystal-exchange-banner.jpg",
                description="神秘研究社库藏",
            )
            container.add_item(gallery)
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"## 💎 兑换规则\n"
            f"每次消耗 🔮 **{CRYSTAL_EXCHANGE_COST} 枚魔法水晶**，"
            "必定获得 **优良或以上**的装备／护符。\n"
            "📊 **单次概率：优良 45%｜稀有 35%｜黄金 17%｜传说 3%**\n"
            "可选择砸 **1 次／5 次／10 次**；多次兑换的每一件奖励独立计算概率。\n"
            "🏫 **学园探索途中也可以砸水晶**，不会改变当前楼层、战斗或探索进度。\n"
            "🏫 **奖池归属：地下城二｜神秘研究社库藏**。\n"
            "武器和护具会放入 **学生物品栏**，只能在地下城二选择穿戴；"
            "护符会直接提供少量永久属性。\n"
            "兑换结果彼此独立，传说装备极其稀有。\n\n"
            f"当前水晶：🔮 **{player.crystals}**\n\n"
            f"## 🧿 水晶护符累计数值\n{crystal_charm_values_text(player)}\n\n"
            f"## 📜 稀有度与秘藏一览\n{crystal_rewards_text()}"
        ))
        if result:
            quotes = {
                "优良": "“嗯，是一件优良秘藏。水晶出品，当然不会拿普通货色糊弄你。”",
                "稀有": "“还不错嘛，稀有装备可比金币商店里的常见货色难遇多了。”",
                "黄金": "“……居然闪着黄金光？看来今天的水晶很喜欢你，别得意忘形哦。”",
                "传说": "“等等……传说秘藏？！这种东西连我都很少见到。快收好，别让别人抢走了！”",
            }
            heading = {
                "优良": "🟢 水晶碎裂·优良秘藏",
                "稀有": "🔵 稀有光辉·秘藏出现",
                "黄金": "🟡🌟 金色奇迹·黄金秘藏",
                "传说": "🟣🌌✨ 星穹降临·传说秘藏！✨🌌",
            }
            container.add_item(discord.ui.Separator())
            if result_rarity:
                container.add_item(discord.ui.Section(
                    f"## {heading[result_rarity]}",
                    f"### {quotes[result_rarity]}\n——by **酒馆老板小小秦**",
                    accessory=discord.ui.Thumbnail(
                        bot.user.display_avatar.url,
                        description="酒馆老板小小秦",
                    ),
                ))
                container.add_item(discord.ui.TextDisplay(
                    f"## 🎁 本次全部兑换结果\n{result}"
                ))
            else:
                container.add_item(discord.ui.TextDisplay(
                    f"## 📌 操作结果\n{result}"
                ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(
            CrystalExchangeButton(1, discord.ButtonStyle.secondary),
            CrystalExchangeButton(5, discord.ButtonStyle.primary),
            CrystalExchangeButton(10, discord.ButtonStyle.danger),
        ))
        container.add_item(discord.ui.ActionRow(ReturnTavernButton()))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("这不是你的水晶兑换面板。", ephemeral=True)
            return False
        return True


class CrystalShopButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="水晶兑换", emoji="🔮", style=discord.ButtonStyle.secondary,
            custom_id="dungeon:crystal_shop",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        kwargs = {"view": CrystalExchangePanel(interaction.user.id, player), "ephemeral": True}
        if CRYSTAL_SHOP_IMAGE.exists():
            kwargs["file"] = discord.File(
                CRYSTAL_SHOP_IMAGE,
                filename="crystal-exchange-banner.jpg",
            )
        await interaction.response.send_message(**kwargs)

class EquipmentInventorySelect(discord.ui.Select):
    def __init__(self, player: Player, page: int):
        items = sorted(
            player.equipment_inventory.values(),
            key=lambda item: (item["category"], item["name"]),
        )
        page_items = items[page * 25:(page + 1) * 25]
        options = [
            discord.SelectOption(
                label=f"[{item['rarity']}] {item['name']}",
                value=item["name"],
                description=(
                    f"{item['category']}｜攻击+{display_number(item['attack'])} 防御+{display_number(item['defense'])} "
                    f"敏捷+{display_number(item['agility'])} 幸运+{display_number(item['luck'])}"
                ),
                emoji="⚔️" if item["category"] == "武器" else "🛡️",
            )
            for item in page_items
        ]
        super().__init__(
            placeholder=f"选择装备｜第 {page + 1} 页",
            options=options,
        )
        self.page = page

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        _, result = equip_from_inventory(player, self.values[0])
        store.save(player)
        await interaction.response.edit_message(
            view=EquipmentLibraryPanel(interaction.user.id, player, self.page, result)
        )


class EquipmentPageButton(discord.ui.Button):
    def __init__(self, page: int, label: str, emoji: str):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)
        self.page = page

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        ensure_equipment_inventory(player)
        store.save(player)
        await interaction.response.edit_message(
            view=EquipmentLibraryPanel(interaction.user.id, player, self.page)
        )


class EquipmentLibraryPanel(discord.ui.LayoutView):
    def __init__(
        self,
        owner_id: int,
        player: Player,
        page: int = 0,
        result: str | None = None,
    ):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        ensure_equipment_inventory(player)
        total = len(player.equipment_inventory)
        pages = max(1, (total + 24) // 25)
        page = max(0, min(page, pages - 1))
        message = f"\n\n> ✅ {result}" if result else ""
        container = discord.ui.Container(accent_colour=0x5378B8)
        container.add_item(discord.ui.TextDisplay(
            "# 🧰 学生物品栏\n"
            "诡异学园金币商店、校园小卖部老板和神秘研究社库藏获得的武器与护具都会收藏在这里。\n"
            "这里的装备只能用于地下城二，不能带入地下城一。\n"
            "同名装备自动去重，不会重复占据下拉栏。\n\n"
            f"当前武器：⚔️ **{player.weapon}**\n"
            f"当前护具：🛡️ **{player.clothing}**\n"
            f"已收藏：**{total} 件**｜第 **{page + 1}/{pages} 页**"
            f"{message}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(EquipmentInventorySelect(player, page)))
        nav = []
        if page > 0:
            nav.append(EquipmentPageButton(page - 1, "上一页", "⬅️"))
        if page + 1 < pages:
            nav.append(EquipmentPageButton(page + 1, "下一页", "➡️"))
        nav.append(ReturnTavernButton())
        container.add_item(discord.ui.ActionRow(*nav))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("这不是你的学生物品栏。", ephemeral=True)
            return False
        return True


class EquipmentLibraryButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="学生物品栏", emoji="🧰", style=discord.ButtonStyle.secondary,
            custom_id="dungeon:equipment_library",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        ensure_equipment_inventory(player)
        store.save(player)
        await interaction.response.send_message(
            view=EquipmentLibraryPanel(interaction.user.id, player),
            ephemeral=True,
        )


class MyStatusButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="学生档案", emoji="🎒", style=discord.ButtonStyle.success,
            custom_id="dungeon:my_status",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        sync_player_fortune(player, interaction.guild_id)
        engine.ensure_floor(player)
        store.save(player)
        await interaction.response.send_message(embed=inventory_embed(player), ephemeral=True)


def daily_quest_embed(player: Player) -> discord.Embed:
    day = today_key()
    sync_daily_quests(player, day)
    lines = []
    for quest in quests_for(day):
        current = quest_progress(player, quest)
        if quest.key in player.daily_quest_claimed:
            state = "✅ 已领取"
        elif current >= quest.target:
            state = "🎁 可领取"
        else:
            state = f"⏳ {current}/{quest.target}"
        lines.append(
            f"{quest.emoji} **{quest.name}**｜{state}\n"
            f"{quest.description}｜奖励 **{quest.reward_text}**"
        )
    embed = discord.Embed(
        title="📝 今日布置作业",
        description="\n\n".join(lines),
        color=0x48B8C7,
    )
    embed.set_footer(text=f"北京时间每日刷新｜{day}｜完成后请点击下方按钮领取")
    return embed


class ClaimDailyQuestsButton(discord.ui.Button):
    def __init__(self, disabled: bool = False):
        super().__init__(
            label="领取全部奖励",
            emoji="🎁",
            style=discord.ButtonStyle.success,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        player = store.get(interaction.user.id, interaction.user.display_name)
        claimed, message = claim_all(player, today_key())
        store.save(player)
        await interaction.response.edit_message(
            content=f"✅ {message}" if claimed else f"ℹ️ {message}",
            embed=daily_quest_embed(player),
            view=DailyQuestClaimView(player),
        )


class DailyQuestClaimView(discord.ui.View):
    def __init__(self, player: Player):
        super().__init__(timeout=300)
        self.add_item(ClaimDailyQuestsButton(not completed_unclaimed(player, today_key())))


class DailyQuestButton(discord.ui.Button):
    def __init__(self, custom_id: str = "dungeon:daily_quests"):
        super().__init__(
            label="今日布置作业",
            emoji="📜",
            style=discord.ButtonStyle.success,
            custom_id=custom_id,
        )
        self.available_in_adventure = custom_id == "dungeon:adventure_daily_quests"

    async def callback(self, interaction: discord.Interaction) -> None:
        if (
            not self.available_in_adventure
            and await reject_tavern_service(interaction, "酒馆每日任务面板")
        ):
            return
        player = store.get(interaction.user.id, interaction.user.display_name)
        sync_daily_quests(player, today_key())
        store.save(player)
        await interaction.response.send_message(
            embed=daily_quest_embed(player),
            view=DailyQuestClaimView(player),
            ephemeral=True,
        )


class DailyQuestButtons(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(DailyQuestButton())


class DungeonQuestUtilities(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(DailyQuestButton("dungeon:adventure_daily_quests"))


class EntranceButtons(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            ExploreEntranceButton(),
            GoldShopButton(),
            CrystalShopButton(),
            EquipmentLibraryButton(),
            MyStatusButton(),
        )


class EntrancePanel(discord.ui.LayoutView):
    def __init__(self, client_user: discord.ClientUser):
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_colour=0x48B8C7)
        container.add_item(discord.ui.Section(
            "# 🍺 学园酒馆",
            "### **欢迎回来勇者，接取委托、整理行囊，然后从这里滚去你的冒险。——by 酒馆老板小小秦**",
            accessory=discord.ui.Thumbnail(
                client_user.display_avatar.url,
                description="地下城探索 Bot",
            ),
        ))
        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(
            media="attachment://adventurer-tavern-chibi-hq.jpg",
            description="热闹又温暖的学园酒馆",
        )
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
        quests = quests_for(today_key())
        container.add_item(discord.ui.TextDisplay(
            "## 📝 今日布置作业\n"
            + "\n".join(
                f"> {quest.emoji} **{quest.name}**｜{quest.description}，"
                f"奖励 **{quest.reward_text}**"
                for quest in quests
            )
            + f"\n-# 北京时间每日刷新｜{today_key()}｜点击下方 **今日布置作业** 查看进度并领取。"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            "## 👤 当前学生情况\n"
            "点击 **学生档案**，随时查看个人等级、状态、装备、道具和货币。\n"
            "-# 个人数据仅自己可见，不会与其他学生混淆。"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(DailyQuestButtons())
        container.add_item(EntranceButtons())
        container.add_item(discord.ui.ActionRow(GoldStorageButton()))
        self.add_item(container)


async def ensure_entrance_panel() -> None:
    channel_id = os.getenv("SCHOOL_DUNGEON_CHANNEL_ID")
    if not channel_id or not bot.user:
        print("未设置 SCHOOL_DUNGEON_CHANNEL_ID，暂不发布学园入口面板。")
        return
    try:
        channel = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
        message_id = store.get_setting("entrance_panel_message_id")
        image = discord.File(TAVERN_IMAGE, filename="adventurer-tavern-chibi-hq.jpg")
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(
                    content=None, embed=None, view=EntrancePanel(bot.user), attachments=[image]
                )
                return
            except (discord.NotFound, discord.Forbidden):
                pass
        message = await channel.send(view=EntrancePanel(bot.user), file=image)
        store.set_setting("entrance_panel_message_id", message.id)
        print(f"已发布地下城入口面板：频道 {channel.id}")
    except (ValueError, OSError, discord.HTTPException) as error:
        print(f"地下城入口面板发布失败：{error}")


bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())


def bind_runtime(
    host_bot: commands.Bot,
    entrance_panel_factory=None,
    host_player_store=None,
) -> None:
    """把学园地下城绑定到已经登录的地下城一 Bot。"""
    global bot, HOST_ENTRANCE_PANEL_FACTORY, HOST_PLAYER_STORE
    bot = host_bot
    HOST_ENTRANCE_PANEL_FACTORY = entrance_panel_factory
    HOST_PLAYER_STORE = host_player_store
    if host_player_store is not None:
        store.set_shared_path(host_player_store.path)


def host_entrance_panel() -> discord.ui.LayoutView:
    if HOST_ENTRANCE_PANEL_FACTORY is not None:
        return HOST_ENTRANCE_PANEL_FACTORY(bot.user)
    return EntrancePanel(bot.user)


async def enter_school(interaction: discord.Interaction) -> None:
    """从共享酒馆选择页进入地下城二，并使用独立学园存档。"""
    active = active_adventure_names(
        interaction.user.id,
        interaction.user.display_name,
    )
    if active and DUNGEON_TWO_NAME not in active:
        await interaction.response.send_message(
            f"⚔️ 你仍身处 {active_adventure_text(active)}，"
            f"无法立刻进入 **{DUNGEON_TWO_NAME}**。请先结束当前冒险并返回酒馆。",
            ephemeral=True,
        )
        return
    if HOST_PLAYER_STORE is not None:
        host_player = HOST_PLAYER_STORE.get(
            interaction.user.id,
            interaction.user.display_name,
        )
        HOST_PLAYER_STORE.save(host_player)
    player = store.get(interaction.user.id, interaction.user.display_name)
    sync_player_fortune(player, interaction.guild_id)
    engine.ensure_floor(player)
    player.in_adventure = True
    player.gold_storage_available = False
    store.save(player)
    await interaction.response.defer()
    result = GameResult(
        "🏫 永不下课的学园",
        "你推开封闭的校门，教学楼里传来本不该响起的上课铃……",
    )
    await interaction.edit_original_response(
        content=None,
        embed=None,
        view=DungeonPanel(interaction.user.id, player, result),
        attachments=[floor_scene_file(player.floor)],
    )
    if isinstance(interaction.user, discord.Member):
        await assign_dungeon_adventurer_role(interaction.user)


@bot.event
async def on_ready() -> None:
    global views_added, titles_backfilled
    if not views_added:
        bot.add_view(EntrancePanel(bot.user))
        views_added = True
    guild_id = os.getenv("TEST_GUILD_ID") or os.getenv("GUILD_ID")
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()
    if not weekly_ranking_task.is_running():
        weekly_ranking_task.start()
    await ensure_weekly_ranking_channel()
    await update_weekly_ranking(force=True)
    await ensure_entrance_panel()
    if not titles_backfilled:
        await backfill_dungeon_adventurer_roles()
        await backfill_adventurer_titles()
        titles_backfilled = True
    print(f"已登录：{bot.user}")


@bot.tree.command(name="地下城二", description="打开永不下课学园探索面板")
async def dungeon(interaction: discord.Interaction) -> None:
    channel_id = os.getenv("SCHOOL_DUNGEON_CHANNEL_ID")
    if channel_id and interaction.channel_id != int(channel_id):
        channel = bot.get_channel(int(channel_id))
        mention = channel.mention if channel else f"频道 `{channel_id}`"
        await interaction.response.send_message(
            f"请前往 {mention} 使用地下城。", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "请选择要进入的学园：", view=CaveSelectionView(), ephemeral=True
    )


@bot.tree.command(name="挑战排行", description="查看本周地下城挑战层数 TOP15")
async def challenge_ranking(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=weekly_ranking_embed(), ephemeral=True)


@bot.tree.command(name="学生称号", description="切换一个已经解锁的百层通关称号颜色")
async def adventurer_title(interaction: discord.Interaction) -> None:
    player = store.get(interaction.user.id, interaction.user.display_name)
    if player.completion_count <= 0:
        await interaction.response.send_message(
            "你还没有解锁学生称号。首次通关诡异学园第 100 层后即可获得。",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        f"你已完成 **{player.completion_count}** 次百层学园探索。"
        "请选择想要展示的称号颜色：",
        view=AdventurerTitleView(player),
        ephemeral=True,
    )


@bot.tree.command(name="设置挑战排行频道", description="将当前频道设为每周挑战 TOP15 发布频道")
@discord.app_commands.default_permissions(administrator=True)
async def set_challenge_ranking_channel(interaction: discord.Interaction) -> None:
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.administrator:
        await interaction.response.send_message("只有服务器管理员可以设置排行频道。", ephemeral=True)
        return
    if interaction.channel_id is None:
        await interaction.response.send_message("无法识别当前频道。", ephemeral=True)
        return
    store.set_setting("weekly_ranking_channel_id", interaction.channel_id)
    await interaction.response.defer(ephemeral=True)
    published = await update_weekly_ranking(force=True)
    message = (
        "✅ 当前频道已设为每周挑战排行频道，榜单已发布；以后每周六自动更新。"
        if published
        else "频道设置已保存，但榜单发布失败，请检查 Bot 的查看频道、发送消息和嵌入链接权限。"
    )
    await interaction.followup.send(message, ephemeral=True)


@bot.tree.command(name="地下城二测试", description="管理员指定下一刻出现的学园事件")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.choices(event=[
    discord.app_commands.Choice(name="普通怪物", value="monster"),
    discord.app_commands.Choice(name="普通宝箱", value="chest"),
    discord.app_commands.Choice(name="宝箱怪（先伪装）", value="mimic"),
    discord.app_commands.Choice(name="宁静泉水", value="fountain"),
    discord.app_commands.Choice(name="旅行商人", value="merchant"),
    discord.app_commands.Choice(name="忘带作业的新生", value="fairy"),
    discord.app_commands.Choice(name="神秘石像", value="mystery"),
    discord.app_commands.Choice(name="藏宝图", value="treasure_map"),
    discord.app_commands.Choice(name="受困妖兽", value="trapped_beast"),
    discord.app_commands.Choice(name="地下许愿井", value="wishing_well"),
    discord.app_commands.Choice(name="随机陷阱", value="trap"),
    discord.app_commands.Choice(name="寂静长廊", value="empty"),
    discord.app_commands.Choice(name="小 Boss", value="small_boss"),
    discord.app_commands.Choice(name="大 Boss", value="major_boss"),
    discord.app_commands.Choice(name="立即死亡结算", value="instant_death"),
    discord.app_commands.Choice(name="百层通关庆祝", value="floor_100_completion"),
    discord.app_commands.Choice(name="全部清零并从头开始", value="full_reset"),
])
async def dungeon_test(
    interaction: discord.Interaction,
    event: discord.app_commands.Choice[str],
) -> None:
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.administrator:
        await interaction.response.send_message("只有服务器管理员可以使用测试指令。", ephemeral=True)
        return
    player = store.get(interaction.user.id, interaction.user.display_name)
    sync_player_fortune(player, interaction.guild_id)
    if event.value == "instant_death":
        challenged_floor = player.floor
        player.in_adventure = True
        player.hp = 1
        player.enemy = Enemy(
            "测试用雪崩史莱姆",
            999_999,
            999_999,
            999_999,
            0,
            "测试怪物",
            999,
            "这是管理员要求的立即死亡测试！",
        )
        result = engine.attack(player)
        store.record_weekly_challenge(
            interaction.user.id,
            interaction.user.display_name,
            challenged_floor,
        )
        store.save(player)
        await interaction.response.send_message(
            view=DungeonPanel(interaction.user.id, player, result),
            ephemeral=True,
        )
        return
    if event.value == "floor_100_completion":
        player.floor = 100
        player.in_adventure = True
        player.enemy = Enemy(
            "塞纳河畔的春水",
            1,
            1,
            1,
            10_000,
            "大 Boss",
            103,
            "期末考试现在开始。击败我即可验证百层奖励！",
            alias=FINAL_BOSS_ALIAS,
            quiz_subject="数学",
            quiz_triggers_done=[75, 50, 25],
        )
        result = engine.attack(player)
        store.record_weekly_challenge(
            interaction.user.id,
            interaction.user.display_name,
            100,
        )
        store.save(player)
        await interaction.response.defer(ephemeral=True)
        await interaction.edit_original_response(
            view=DungeonPanel(interaction.user.id, player, result),
            attachments=[],
        )
        if isinstance(interaction.user, discord.Member):
            try:
                role_status, awarded_role = await asyncio.wait_for(
                    award_adventurer_title(
                        interaction.user,
                        player.completion_count,
                    ),
                    timeout=10,
                )
            except TimeoutError:
                awarded_role = None
                role_status = (
                    f"身份组发放等待超时。请检查 Bot 的“管理身份组”权限，以及 "
                    f"Bot 身份组是否位于 **{GameEngine.adventurer_title(player.completion_count)}** 上方。"
                )
        else:
            awarded_role = None
            role_status = "通关记录已保存，但身份组只能在 Discord 服务器内发放。"
        if awarded_role:
            result.role_mention = awarded_role.mention
            await interaction.edit_original_response(
                view=DungeonPanel(interaction.user.id, player, result),
                attachments=[],
            )
        await interaction.followup.send(f"🎖️ {role_status}", ephemeral=True)
        return
    if event.value == "full_reset":
        reset_player = Player(interaction.user.id, interaction.user.display_name)
        engine.ensure_floor(reset_player)
        store.save(reset_player)
        store.clear_weekly_challenge(interaction.user.id)
        role_status = ""
        if isinstance(interaction.user, discord.Member):
            roles = [
                role
                for role in interaction.user.roles
                if role.name in ADVENTURER_ROLE_NAMES
            ]
            if roles:
                try:
                    await interaction.user.remove_roles(
                        *roles,
                        reason="管理员使用地下城全部清零测试",
                    )
                    role_status = "\n已移除全部学生通关身份组。"
                except discord.Forbidden:
                    role_status = (
                        "\n无法移除学生通关身份组："
                        "请检查 Bot 的“管理身份组”权限和身份组层级。"
                    )
                except discord.HTTPException as error:
                    role_status = f"\n移除身份组失败：{error}"
        tavern_image = discord.File(TAVERN_IMAGE, filename="adventurer-tavern-chibi-hq.jpg")
        await interaction.response.send_message(
            "## 🧹 地下城测试数据已全部清零\n"
            "等级、经验、楼层、金币、水晶、装备、道具和通关次数均已恢复为新手状态。\n"
            f"本周挑战排行记录也已删除。{role_status}",
            view=EntrancePanel(bot.user),
            file=tavern_image,
            ephemeral=True,
        )
        return
    engine.ensure_floor(player)
    result = engine.force_event(player, event.value)
    store.save(player)
    await interaction.response.send_message(
        view=DungeonPanel(interaction.user.id, player, result),
        file=floor_scene_file(player.floor),
        ephemeral=True,
    )


@bot.tree.command(name="金币测试", description="管理员领取 20,000 测试金币")
@discord.app_commands.default_permissions(administrator=True)
async def gold_test(interaction: discord.Interaction) -> None:
    permissions = getattr(interaction.user, "guild_permissions", None)
    if not permissions or not permissions.administrator:
        await interaction.response.send_message("只有服务器管理员可以使用测试指令。", ephemeral=True)
        return
    player = store.get(interaction.user.id, interaction.user.display_name)
    player.gold += 20_000
    store.save(player)
    await interaction.response.send_message(
        "🧪 已发放 **20,000 测试金币**！\n"
        f"你现在共有 🪙 **{player.gold}** 金币。返回酒馆后即可打开金币商城测试装备。",
        ephemeral=True,
    )


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("请在 .env 中设置 DISCORD_TOKEN")
    bot.run(token)
