from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Player


def fortune_crystal_growth(overall_score: int) -> float:
    if overall_score >= 90:
        return 0.60
    if overall_score >= 80:
        return 0.40
    if overall_score >= 70:
        return 0.20
    return 0.0


def fortune_luck_bonus(overall_score: int) -> int:
    """旧调用兼容：运势不再直接增加幸运属性。"""
    return 0


def sync_daily_fortune(
    player: Player,
    guild_id: int | None,
    draw_file: str | Path,
    now: datetime | None = None,
) -> float:
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    day = current.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    player.daily_fortune_date = day
    player.daily_fortune_score = 0
    player.daily_fortune_bonus = 0
    player.daily_fortune_growth = 0.0
    if guild_id is None:
        return 0
    try:
        draws = json.loads(Path(draw_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    record = draws.get(f"{guild_id}:{player.user_id}:{day}") if isinstance(draws, dict) else None
    if not isinstance(record, dict):
        return 0
    try:
        score = int(record.get("overall_score", 0))
    except (TypeError, ValueError):
        return 0
    player.daily_fortune_score = max(0, min(100, score))
    player.daily_fortune_growth = fortune_crystal_growth(player.daily_fortune_score)
    return player.daily_fortune_growth
