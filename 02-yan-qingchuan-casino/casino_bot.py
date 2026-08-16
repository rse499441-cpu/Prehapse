"""Standalone Discord casino bot hosted by Yan Qingchuan."""
from __future__ import annotations

import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from gamble_games import PANEL_TITLE, CasinoMenuView, SharedGoldWallet, panel_embed


ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env", override=True)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
CHANNEL_ID = int(os.getenv("CASINO_CHANNEL_ID", "1536729710069944320"))
PROXY = os.getenv("DISCORD_PROXY") or None
DUNGEON_DB_PATH = Path(os.getenv(
    "DUNGEON_DB_PATH",
    "/opt/dungeon-explorer-bot/data/dungeon.db" if os.name != "nt"
    else str(ROOT / "dungeon-explorer-bot" / "data" / "dungeon.db"),
))

if not TOKEN or not GUILD_ID:
    raise RuntimeError("请在 .env 中设置新 Bot 的 DISCORD_TOKEN 和 GUILD_ID。")

wallet = SharedGoldWallet(DUNGEON_DB_PATH)
CASINO_ACCESS_ROLE = "赌徒｜内测版"


async def ensure_casino_access_role(client: discord.Client) -> None:
    guild = client.get_guild(GUILD_ID)
    channel = client.get_channel(CHANNEL_ID)
    if guild is None or not isinstance(channel, discord.TextChannel):
        print("赌场内测身份组设置跳过：服务器或频道尚未缓存。")
        return
    try:
        role = discord.utils.get(guild.roles, name=CASINO_ACCESS_ROLE)
        if role is None:
            role = await guild.create_role(
                name=CASINO_ACCESS_ROLE,
                permissions=discord.Permissions.none(),
                hoist=False,
                mentionable=False,
                reason="青川赌场内测频道入场身份组",
            )
        await channel.set_permissions(
            guild.default_role,
            view_channel=False,
            reason="青川赌场仅限内测身份组",
        )
        await channel.set_permissions(
            role,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            use_application_commands=True,
            reason="配置青川赌场内测身份组访问权限",
        )
        print(f"赌场内测身份组已配置：{role.name} ({role.id})")
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"赌场内测身份组配置失败：{error}")


async def publish_or_refresh(client: discord.Client, channel_id: int) -> None:
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as error:
            print(f"无法读取赌场频道 {channel_id}：{error}")
            return
    if not isinstance(channel, discord.TextChannel):
        print(f"赌场频道 {channel_id} 不是文字频道。")
        return
    try:
        current = None
        old_panels = []
        async for message in channel.history(limit=100):
            if message.author != client.user:
                continue
            titles = {item.title for item in message.embeds}
            if PANEL_TITLE in titles and current is None:
                current = message
            elif any(title and title.startswith("🪙 晏先生的地下牌局") for title in titles):
                old_panels.append(message)
        avatar = client.user.display_avatar.url if client.user else None
        for old in old_panels:
            await old.edit(view=None)
        if current:
            await current.edit(embed=panel_embed(avatar), view=CasinoMenuView(wallet))
            print(f"地下牌局新面板已更新：{channel_id}")
        else:
            await channel.send(embed=panel_embed(avatar), view=CasinoMenuView(wallet))
            print(f"地下牌局新面板已发布：{channel_id}")
    except (discord.Forbidden, discord.HTTPException) as error:
        print(f"地下牌局面板发布失败：{error}")


class CasinoBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default(), proxy=PROXY)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.add_view(CasinoMenuView(wallet))
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        print(f"晏青川赌场 Bot 已登录：{self.user}")
        await ensure_casino_access_role(self)
        await publish_or_refresh(self, CHANNEL_ID)


bot = CasinoBot()


@bot.tree.command(name="发布地下牌局", description="在当前频道发布晏先生的地下赌场面板")
@app_commands.default_permissions(manage_guild=True)
async def publish_casino(interaction: discord.Interaction) -> None:
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.guild_permissions.manage_guild:
        await interaction.response.send_message("只有拥有“管理服务器”权限的成员可以发布牌局。", ephemeral=True)
        return
    avatar = bot.user.display_avatar.url if bot.user else None
    await interaction.response.send_message(embed=panel_embed(avatar), view=CasinoMenuView(wallet))


if __name__ == "__main__":
    bot.run(TOKEN, log_handler=None)
