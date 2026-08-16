from __future__ import annotations


def format_number(value: int | float) -> str:
    """用户可见数值最多保留两位小数，去掉无意义的末尾零。"""
    return f"{value:.2f}".rstrip("0").rstrip(".")
