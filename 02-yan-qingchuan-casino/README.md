# 晏青川赌场 Bot

运行在 Discord 中的私密赌场小游戏。目前包含比大小、二十一点、吹牛骰等玩法，使用地下城数据库中的共享金币钱包。

## 项目结构

- `casino_bot.py`：Bot 入口、频道面板和权限配置。
- `gamble_games.py`：游戏规则、交互界面和金币结算。
- `casino_cards.py`：扑克牌、骰子和牌桌图片渲染。
- `assets/casino/`：运行所需牌面与牌桌素材。
- `deploy/casino-bot.service`：Linux systemd 部署示例。

## 本地启动

1. 安装 Python 3.11 或更高版本。
2. 创建虚拟环境并安装依赖：`pip install -r requirements.txt`
3. 将 `.env.example` 复制为 `.env`，填写 Discord Bot Token、服务器 ID、频道 ID 和地下城数据库路径。
4. 运行：`python casino_bot.py`

赌场读取地下城 SQLite 数据库中的共享金币，因此 `DUNGEON_DB_PATH` 必须指向可访问的地下城数据库。不要把真实数据库上传到 GitHub；开发者应使用测试数据库或本地副本。

## 协作安全

- 仓库必须保持为 **Private**。
- `.env`、真实 Token、数据库、日志和部署压缩包不得提交。
- 如需让协作者连接测试服务器，请单独、安全地提供测试配置，不要写进代码或提交记录。

## 素材许可

运行时扑克牌素材来自 Kenney Playing Cards Pack 1.0，采用 CC0 许可；详情见 `assets/casino/README.md` 与素材目录内的 `License.txt`。

