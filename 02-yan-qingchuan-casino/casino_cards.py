"""Compose Discord card-table images from Kenney's CC0 Playing Cards Pack."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
CARD_DIR = ROOT / "assets" / "casino" / "kenney-playing-cards" / "PNG" / "Cards (large)"
DICE_DIR = ROOT / "assets" / "casino" / "kenney-playing-cards" / "PNG" / "Cards (medium)"
TABLE_DIR = ROOT / "assets" / "casino" / "yan-table"
VERTICAL_TABLE = TABLE_DIR / "yan-table-vertical-neutral.png"
COMPACT_LOSE_TABLE = TABLE_DIR / "yan-table-compact-lose.png"


def _table(state: str = "neutral") -> Image.Image:
    path = COMPACT_LOSE_TABLE if state == "lose" else VERTICAL_TABLE
    return Image.open(path).convert("RGBA")


def _path(card: tuple[str, int] | None) -> Path:
    if card is None:
        return CARD_DIR / "card_back.png"
    suit, rank = card
    label = {11: "J", 12: "Q", 13: "K", 14: "A"}.get(rank, f"{rank:02d}")
    return CARD_DIR / f"card_{suit}_{label}.png"


def render_card_groups(groups: list[list[tuple[str, int] | None]], filename: str = "cards.png") -> tuple[BytesIO, str]:
    rows: list[list[Image.Image]] = []
    for group in groups:
        row = []
        for card in group:
            with Image.open(_path(card)) as source:
                picture = source.convert("RGBA")
                row.append(picture.resize((picture.width * 2, picture.height * 2), Image.Resampling.LANCZOS))
        rows.append(row)
    width, height = rows[0][0].size
    gap, margin, row_gap = 24, 24, 34
    canvas_width = max(margin * 2 + width * len(row) + gap * max(0, len(row) - 1) for row in rows)
    canvas_height = margin * 2 + height * len(rows) + row_gap * max(0, len(rows) - 1)
    canvas = Image.new("RGBA", (canvas_width, canvas_height), "#170D10")
    for row_index, row in enumerate(rows):
        row_width = width * len(row) + gap * max(0, len(row) - 1)
        start_x = (canvas_width - row_width) // 2
        for index, picture in enumerate(row):
            canvas.alpha_composite(picture, (start_x + index * (width + gap), margin + row_index * (height + row_gap)))
    output = BytesIO()
    canvas.convert("RGB").save(output, "PNG", optimize=True)
    output.seek(0)
    output.name = filename
    return output, filename


def render_cards(cards: list[tuple[str, int] | None], filename: str = "cards.png") -> tuple[BytesIO, str]:
    return render_card_groups([cards], filename)


def render_dice(rolls: list[int], filename: str = "dice.png") -> tuple[BytesIO, str]:
    pictures = []
    for value in rolls:
        with Image.open(DICE_DIR / f"dice_decorated_{value}.png") as source:
            picture = source.convert("RGBA")
            pictures.append(picture.resize((picture.width * 4, picture.height * 4), Image.Resampling.NEAREST))
    width, height = pictures[0].size
    gap, margin = 22, 24
    canvas = Image.new("RGBA", (margin * 2 + width * len(pictures) + gap * (len(pictures) - 1), height + margin * 2), "#170D10")
    for index, picture in enumerate(pictures):
        canvas.alpha_composite(picture, (margin + index * (width + gap), margin))
    output = BytesIO()
    canvas.convert("RGB").save(output, "PNG", optimize=True)
    output.seek(0)
    output.name = filename
    return output, filename


def _place(scene: Image.Image, picture: Image.Image, x: int, y: int) -> None:
    alpha = picture.getchannel("A")
    shadow = Image.new("RGBA", picture.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda value: value * 90 // 255))
    scene.alpha_composite(shadow, (x + 7, y + 9))
    scene.alpha_composite(picture, (x, y))


def _card(card: tuple[str, int] | None, size: int) -> Image.Image:
    with Image.open(_path(card)) as source:
        return source.convert("RGBA").resize((size, size), Image.Resampling.NEAREST)


def render_yan_cards(
    rounds: list[list[tuple[str, int]]],
    next_player: tuple[str, int] | None = None,
    show_next: bool = False,
    state: str = "neutral",
    filename: str = "table-cards.png",
) -> tuple[BytesIO, str]:
    scene = _table(state)
    entries: list[list[tuple[str, int] | None]] = [list(pair) for pair in rounds]
    if show_next:
        entries.append([next_player, None])
    count = max(1, len(entries))
    size = 180 if count <= 3 else 142
    compact = state == "lose"
    start_y = (880 if count <= 3 else 830) if compact else (735 if count <= 3 else 710)
    step = (205 if count <= 3 else 150) if compact else (228 if count <= 3 else 176)
    left_x = 270
    right_x = scene.width - left_x - size
    for index, pair in enumerate(entries):
        y = start_y + index * step
        _place(scene, _card(pair[0], size), left_x, y)
        _place(scene, _card(pair[1], size), right_x, y)
    output = BytesIO()
    scene.convert("RGB").save(output, "JPEG", quality=91, optimize=True)
    output.seek(0)
    output.name = filename
    return output, filename


def render_yan_blackjack(
    dealer: list[tuple[str, int] | None],
    player: list[tuple[str, int]],
    state: str = "neutral",
    filename: str = "blackjack-cards.png",
) -> tuple[BytesIO, str]:
    scene = _table(state)
    size, gap = 136, 18
    rows = ((dealer, 875), (player, 1110)) if state == "lose" else ((dealer, 755), (player, 1110))
    for cards, y in rows:
        total = len(cards) * size + max(0, len(cards) - 1) * gap
        start = (scene.width - total) // 2
        for index, card in enumerate(cards):
            _place(scene, _card(card, size), start + index * (size + gap), y)
    output = BytesIO()
    scene.convert("RGB").save(output, "JPEG", quality=91, optimize=True)
    output.seek(0); output.name = filename
    return output, filename


def render_yan_dice(player: list[int], dealer: list[int] | None = None, reveal: bool = False, state: str = "neutral", filename: str = "player-dice.png") -> tuple[BytesIO, str]:
    scene = _table(state)
    size, gap = 126, 22
    start = (scene.width - (5 * size + 4 * gap)) // 2
    values = dealer or [1] * 5
    for index, value in enumerate(values):
        with Image.open(DICE_DIR / f"dice_decorated_{value}.png") as source:
            die = source.convert("RGBA").resize((size, size), Image.Resampling.NEAREST)
        if not reveal:
            pixels = die.load()
            for y in range(size):
                for x in range(size):
                    r, g, b, a = pixels[x, y]
                    if a:
                        shade = 38 + r * 18 // 255
                        pixels[x, y] = (shade, shade + 4, shade + 6, a)
        _place(scene, die, start + index * (size + gap), 880 if state == "lose" else 770)
    for index, value in enumerate(player):
        with Image.open(DICE_DIR / f"dice_decorated_{value}.png") as source:
            die = source.convert("RGBA").resize((size, size), Image.Resampling.NEAREST)
        _place(scene, die, start + index * (size + gap), 1130)
    output = BytesIO()
    scene.convert("RGB").save(output, "JPEG", quality=91, optimize=True)
    output.seek(0); output.name = filename
    return output, filename
