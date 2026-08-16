# 私密云端部署

此配置会在同一个 Railway 私密服务中运行地下城与赌场两个 Discord Bot，
并让赌场读取地下城的 SQLite 钱包数据库。

## 必填私密变量

在 Railway 服务的 Variables 页面填写，绝对不要提交到 GitHub：

- `DUNGEON_DISCORD_TOKEN`：地下城 Bot 的新 Token
- `CASINO_DISCORD_TOKEN`：赌场 Bot 的新 Token
- `TEST_GUILD_ID`：Discord 服务器 ID
- `DUNGEON_CHANNEL_ID`：地下城频道 ID
- `DUNGEON_RANKING_CHANNEL_ID`：排行榜频道 ID，可留空
- `GUILD_ID`：赌场所在的 Discord 服务器 ID
- `CASINO_CHANNEL_ID`：赌场频道 ID
- `DUNGEON_DB_PATH`：建议填写
  `/app/01-dungeon-explorer/data/dungeon.db`

不要设置通用的 `DISCORD_TOKEN`。启动器会分别把两枚私密 Token 交给对应 Bot。

## 持久存档

必须给服务添加 Railway Volume，并挂载到：

`/app/01-dungeon-explorer/data`

否则重新部署后 SQLite 存档可能丢失。

## 部署方式

1. Railway 新建 Project，选择此私有 GitHub 仓库。
2. Railway 会读取根目录的 `Dockerfile` 与 `railway.toml`。
3. 添加上述 Variables。
4. 添加 Volume 并使用指定挂载路径。
5. 部署后查看日志，确认同时出现地下城和赌场 Bot 的登录成功消息。

两枚 Token 只存放在 Railway 的加密变量中，不写入代码、提交记录或日志。
