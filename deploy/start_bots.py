"""Run the dungeon and casino bots together without storing secrets in Git."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DUNGEON_DIR = ROOT / "01-dungeon-explorer"
CASINO_DIR = ROOT / "02-yan-qingchuan-casino"
DEFAULT_DB_PATH = DUNGEON_DIR / "data" / "dungeon.db"


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required private environment variable: {name}")
    return value


def child_environment(token_name: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["DISCORD_TOKEN"] = required(token_name)
    environment["DUNGEON_DB_PATH"] = os.getenv(
        "DUNGEON_DB_PATH",
        str(DEFAULT_DB_PATH),
    )
    return environment


def stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 15
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    processes = [
        subprocess.Popen(
            [sys.executable, "-u", "bot.py"],
            cwd=DUNGEON_DIR,
            env=child_environment("DUNGEON_DISCORD_TOKEN"),
        ),
        subprocess.Popen(
            [sys.executable, "-u", "casino_bot.py"],
            cwd=CASINO_DIR,
            env=child_environment("CASINO_DISCORD_TOKEN"),
        ),
    ]

    def handle_shutdown(_signum: int, _frame: object) -> None:
        stop(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    stop(processes)
                    return return_code or 1
            time.sleep(1)
    finally:
        stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
