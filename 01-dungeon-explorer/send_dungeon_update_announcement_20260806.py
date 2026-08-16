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
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{extension}?size=256"
    discriminator = int(str(user.get("discriminator") or "0"))
    index = discriminator % 5 if discriminator else (int(user_id) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def text_component(content: str) -> dict[str, object]:
    return {"type": 10, "content": content}


def divider() -> dict[str, object]:
    return {"type": 14, "divider": True, "spacing": 1}


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

        role = next((item for item in roles if item["name"] == ADVENTURER_ROLE_NAME), None)
        if role is None:
            raise RuntimeError(f"服务器中尚未建立 {ADVENTURER_ROLE_NAME} 身份组。")
        role_id = str(role["id"])
        role_mention = f"<@&{role_id}>"

        sections = [
            {
                "type": 9,
                "components": [text_component(
                    "# ❄️ 地下城酒馆更新公告\n"
                    "各位冒险者晚上好呀！酒馆老板小小秦带着地下城的新消息来啦～\n"
                    "本次更新相较7月28日的上线版本主要调整了装备、百层祝福、永久护符及旅行商人的相关规则，同时新增了储值商人。"
                )],
                "accessory": {
                    "type": 11,
                    "media": {"url": avatar_url(bot_user)},
                    "description": "酒馆老板小小秦",
                },
            },
            divider(),
            text_component(
                "### 📣 冒险者集合\n"
                f"{role_mention}\n\n"
                "本次仅通知地下城冒险者。"
            ),
            divider(),
            text_component(
                "## 1. 🎒 装备收藏规则调整\n"
                "通过以下途径获得的武器与护具，现在都会统一收入装备库：\n\n"
                "- 金币商店\n- 旅行商人\n- Boss 掉落\n- 魔法水晶兑换\n\n"
                "装备库会按名称自动去重，同名装备只保留一份收藏记录。已经收入装备库的装备属于长期保留内容，不会因死亡结算而丢失。"
            ),
            divider(),
            text_component(
                "## 2. 🏅 百层祝福独立计算\n"
                "每次完成百层远征，都会永久获得：\n\n"
                "- **攻击 +5**\n- **防御 +3**\n\n"
                "百层祝福现在只按照实际通关次数计算，与装备及各类护符分开记录。更换装备或死亡结算不会使祝福丢失。"
            ),
            divider(),
            text_component(
                "## 3. 🧿 商人护符规则调整\n"
                "旅行商人出售的四种永久护符，现在会分别独立累计：\n\n"
                "- 赤牙护符：永久攻击\n- 石纹护符：永久防御\n- 风羽护符：永久敏捷\n- 四叶护符：永久幸运\n\n"
                "不同属性的护符互不占用衰减档位。例如，赤牙护符的数量只影响攻击护符收益，不会降低石纹、风羽或四叶护符的收益。\n\n"
                "每一种护符分别按照自身累计数量计算：\n\n"
                "- 第 1～20 枚：每枚 **+1.0**\n- 第 21～40 枚：每枚 **+0.8**\n"
                "- 第 41～60 枚：每枚 **+0.5**\n- 第 61～80 枚：每枚 **+0.3**\n"
                "- 第 81～100 枚：每枚 **+0.2**\n- 第 101 枚起：每枚 **+0.1**\n\n"
                "系统会分别保存四种护符的历史获得次数和累计属性，玩家的历史获得护符加成也会按照统一规则重新修正。"
            ),
            divider(),
            text_component(
                "## 4. 💎 水晶护符独立累计\n"
                "通过魔法水晶获得的永久护符，现已与旅行商人护符完全分开计算。\n\n"
                "水晶护符会按照抽中时的原始数值永久累加，**不会受到商人护符数量衰减的影响**。传说复合护符仍视为一次抽取，但其中包含的每项属性都会分别记录。\n\n"
                "最终属性统一由以下四部分组成：\n\n"
                "**当前装备＋百层祝福＋商人护符＋水晶护符**\n\n"
                "地下城面板显示、战斗伤害和实际减伤都会使用同一套结果。"
            ),
            divider(),
            text_component(
                "## 5. 🛒 旅行商人调整\n"
                "旅行商人的商品与库存规则进行了调整：\n\n"
                "- 每次相遇初始出现 **4 个货位**\n- 不再保底出现任何类型货位\n"
                "- 货位类型概率为：药剂 **60%**、护符 **25%**、装备 **15%**\n"
                "- 药剂类货位每格库存 **4 件**\n- 护符与装备每格库存 **1 件**\n"
                "- 装备售罄后，只会补充药剂或护符，概率分别为 **70%**、**30%**\n"
                "- 20 层之前不会出现强效精力药水\n\n"
                "刷新费用变更为：**85＋十层区间×5**\n\n"
                "因此第 1～10 层的单次刷新费用为 **90 金币**。"
            ),
            divider(),
            text_component(
                "## 6. 🔮 酒馆问卦联动调整\n"
                "酒馆当日总运达到一定数值后，会提高所有可获得魔法水晶的事件中水晶的获取概率：\n\n"
                "- 总运 70～79：水晶概率 ×**1.20**\n- 总运 80～89：水晶概率 ×**1.40**\n"
                "- 总运 90～100：水晶概率 ×**1.60**\n\n"
                "该效果不会直接增加角色的幸运属性，并会在北京时间次日失效。"
            ),
            divider(),
            text_component(
                "## 7. 🏦 新增储值商人\n"
                "酒馆内新增储值商人。所有位于酒馆的冒险者都可以免费使用存取服务。\n\n"
                "存入的金币：\n\n- 不会在死亡结算时减半\n- 不会被蒙面浣熊偷走\n- 存取不收取手续费\n\n"
                "想要为下一次远征保存一笔启动资金的话，记得先去找储值商人哦！"
            ),
            divider(),
            text_component(
                "以上调整会统一适用于所有冒险者。感谢大家一直以来的游玩和反馈，也欢迎大家在接下来的冒险旅途中遇到任何疑问、困难、Bug时，随时在冒险者攻略频道踊跃发言反馈！\n\n"
                "祝各位远征顺利、药剂多多、泉水眷顾、宝箱不咬人！\n\n"
                "——酒馆老板 **小小秦** 🥂❄️"
            ),
        ]

        payload = {
            "flags": 32768,
            "components": [{"type": 17, "accent_color": 0x4A90E2, "components": sections}],
            "allowed_mentions": {"parse": [], "roles": [role_id], "replied_user": False},
        }

        role_url = f"{API_ROOT}/guilds/{guild_id}/roles/{role_id}"
        restore_mentionable = not bool(role.get("mentionable"))
        if restore_mentionable:
            async with session.patch(role_url, json={"mentionable": True}) as response:
                response.raise_for_status()
        try:
            async with session.post(f"{API_ROOT}/channels/{CHANNEL_ID}/messages", json=payload) as response:
                body = await response.text()
                if response.status != 200:
                    raise RuntimeError(f"Discord returned HTTP {response.status}: {body}")
                message = await response.json()
                print(message["id"])
        finally:
            if restore_mentionable:
                async with session.patch(role_url, json={"mentionable": False}) as response:
                    response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
