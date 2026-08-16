from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv


CHANNEL_ID = "1530192212862701588"
API_ROOT = "https://discord.com/api/v10"
ADVENTURER_ROLE_NAME = "🗺️ 地下城冒险者"


def avatar_url(user: dict[str, object]) -> str:
    user_id = str(user["id"])
    avatar = user.get("avatar")
    if avatar:
        extension = "gif" if str(avatar).startswith("a_") else "png"
        return (
            f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{extension}"
            "?size=256"
        )
    discriminator = int(str(user.get("discriminator") or "0"))
    index = discriminator % 5 if discriminator else (int(user_id) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


async def main() -> None:
    local_env = Path(__file__).resolve().parent / ".env"
    server_env = Path("/opt/dungeon-explorer-bot/.env")
    load_dotenv(local_env if local_env.exists() else server_env)
    token = os.environ["DISCORD_TOKEN"]
    guild_id = os.getenv("TEST_GUILD_ID") or os.getenv("GUILD_ID")
    if not guild_id:
        raise RuntimeError("服务器配置中缺少 TEST_GUILD_ID 或 GUILD_ID。")
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{API_ROOT}/users/@me") as response:
            response.raise_for_status()
            bot_user = await response.json()
        async with session.get(f"{API_ROOT}/guilds/{guild_id}/roles") as response:
            response.raise_for_status()
            roles = await response.json()
        adventurer_role = next(
            (role for role in roles if role["name"] == ADVENTURER_ROLE_NAME),
            None,
        )
        if adventurer_role is None:
            raise RuntimeError(f"服务器中尚未建立 {ADVENTURER_ROLE_NAME} 身份组。")
        adventurer_role_id = str(adventurer_role["id"])
        adventurer_mention = f"<@&{adventurer_role_id}>"

        payload = {
            "flags": 32768,
            "components": [
                {
                    "type": 17,
                    "accent_color": 0x4A90E2,
                    "components": [
                        {
                            "type": 9,
                            "components": [
                                {
                                    "type": 10,
                                    "content": (
                                        "# ❄️ 地下城酒馆公告\n"
                                        "各位冒险者晚上好呀！小小秦带着地下城的新消息来啦～"
                                    ),
                                }
                            ],
                            "accessory": {
                                "type": 11,
                                "media": {"url": avatar_url(bot_user)},
                                "description": "酒馆老板小小秦",
                            },
                        },
                        {"type": 14, "divider": True, "spacing": 1},
                        {
                            "type": 10,
                                "content": (
                                    "### 📣 冒险者集合\n"
                                    f"{adventurer_mention}\n\n"
                                    "本次仅通知地下城冒险者。"
                                ),
                        },
                        {"type": 14, "divider": True, "spacing": 1},
                        {
                            "type": 10,
                            "content": (
                                "## 1. 🦝 浣熊事件\n"
                                "被蒙面浣熊偷走金币后，现在有机会凭借敏捷追上它并进入战斗！\n\n"
                                "基础追击概率为 **20%**，每点敏捷增加 **5%**，最高为 "
                                "**50%**。成功击败浣熊后，可以夺回本次被偷走的全部金币。\n\n"
                                "遇到可疑宝箱时也可以选择悄悄离开；如果里面藏着宝箱怪，"
                                "则有概率成功避开，敏捷越高越容易脱身。"
                            ),
                        },
                        {"type": 14, "divider": True, "spacing": 1},
                        {
                            "type": 10,
                            "content": (
                                "## 2. 🏅 百层通关称号更新\n"
                                "每次完成百层远征，获得的称号都会不同：\n\n"
                                "- 第一次：❄️ 一星冒险者\n"
                                "- 第二次：❄️ 二星冒险者\n"
                                "- 第三次：❄️ 三星冒险者\n"
                                "- 第四次：❄️ 四星冒险者\n"
                                "- 第五次：❄️ 初级冒险者\n\n"
                                "每个称号都有不同的冰蓝渐变配色和专属通关庆祝文案。\n\n"
                                "此前已经完成多次百层远征的玩家，会根据原有存档记录自动补发"
                                "对应称号。使用 `/冒险者称号`，还可以自由切换自己已经解锁的"
                                "称号颜色。"
                            ),
                        },
                        {"type": 14, "divider": True, "spacing": 1},
                        {
                            "type": 10,
                            "content": (
                                "## 3. 🧪 强效药水显示修复\n"
                                "修复了购买强效治疗药水后，金币正常扣除，但地下城面板没有显示"
                                "数量的问题。\n\n"
                                "此前购买的药水并没有丢失。现在面板会分别显示普通与强效版本的"
                                "治疗、魔力和精力药水，购买及使用情况都能正常查看。\n\n"
                                "感谢各位冒险者的反馈，祝大家远征顺利！\n\n"
                                "——酒馆老板 **小小秦** 🥂❄️"
                            ),
                        },
                    ],
                }
            ],
            "allowed_mentions": {
                "parse": [],
                "roles": [adventurer_role_id],
                "replied_user": False,
            },
        }

        role_url = f"{API_ROOT}/guilds/{guild_id}/roles/{adventurer_role_id}"
        restore_mentionable = not bool(adventurer_role.get("mentionable"))
        if restore_mentionable:
            async with session.patch(
                role_url,
                json={"mentionable": True},
            ) as response:
                response.raise_for_status()
        try:
            async with session.post(
                f"{API_ROOT}/channels/{CHANNEL_ID}/messages",
                json=payload,
            ) as response:
                body = await response.text()
                if response.status != 200:
                    raise RuntimeError(
                        f"Discord returned HTTP {response.status}: {body}"
                    )
                message = await response.json()
                print(message["id"])
        finally:
            if restore_mentionable:
                async with session.patch(
                    role_url,
                    json={"mentionable": False},
                ) as response:
                    response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
