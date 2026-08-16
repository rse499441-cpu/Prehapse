#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/dungeon-explorer-bot
SERVICE_NAME=dungeon-explorer-bot.service
BASE_PYTHON=/opt/xiaojiang-chat-bot/.venv/bin/python

if ! id discordbot >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin discordbot
fi

if [ ! -f "$APP_DIR/.env" ]; then
  echo "缺少 $APP_DIR/.env，无法启动地下城 Bot。" >&2
  exit 1
fi

if [ ! -x "$BASE_PYTHON" ]; then
  echo "找不到线上共用的 Python：$BASE_PYTHON" >&2
  exit 1
fi

"$BASE_PYTHON" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

install -m 0644 "$APP_DIR/deploy/dungeon-explorer-bot.service" \
  "/etc/systemd/system/$SERVICE_NAME"
mkdir -p "$APP_DIR/data"
chown -R discordbot:discordbot "$APP_DIR"
chmod 0600 "$APP_DIR/.env"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME"
