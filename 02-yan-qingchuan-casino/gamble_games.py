"""Discord casino games backed by the dungeon shared-gold wallet."""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import traceback
from contextlib import closing
from pathlib import Path

import discord
from casino_cards import render_card_groups, render_cards, render_dice, render_yan_blackjack, render_yan_cards, render_yan_dice

BET_OPTIONS = (10, 50, 100, 500)
MAX_ROUND_STAKE = 3000
BASE_WIN_PROFIT_RATE = 50
SUITS = ("spades", "hearts", "diamonds", "clubs")
SUIT_MARKS = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}
RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}
DICE = ("⚀", "⚁", "⚂", "⚃", "⚄", "⚅")
PANEL_TITLE = "🪙 晏先生的地下牌局｜新桌"


def legal_dice_bid(quantity: int, face: int, previous_quantity: int, previous_face: int) -> bool:
    return quantity > previous_quantity or (quantity == previous_quantity and face > previous_face)


def dice_bid_holds(actual: int, quantity: int) -> bool:
    """Return whether a revealed dice total satisfies the announced quantity."""
    return actual >= quantity


def streak_bonus_rate(streak: int) -> int:
    return 100 if streak >= 7 else 80 if streak >= 5 else 30 if streak >= 3 else 0


def scaled_win_profit(stake: int, original_profit: int, streak: int) -> int:
    """Use half profit before a streak tier, otherwise full profit plus its bonus."""
    base_rate = 100 if streak_bonus_rate(streak) else BASE_WIN_PROFIT_RATE
    base_profit = max(0, original_profit) * base_rate // 100
    streak_bonus = max(0, stake) * streak_bonus_rate(streak) // 100
    return base_profit + streak_bonus


def loss_penalty(stake: int, streak: int) -> int:
    """Return the extra charge applied after the up-front stake has been lost."""
    return max(0, stake) * streak_bonus_rate(streak) // 100


def apply_loss_collection(
    gold: int,
    stored_gold: int,
    amount: int,
) -> tuple[int, int, int, int, int]:
    """Pay a loss from carried gold, then savings, then create wallet debt."""
    remaining = max(0, amount)
    wallet_paid = min(max(0, gold), remaining)
    remaining -= wallet_paid
    stored_paid = min(max(0, stored_gold), remaining)
    remaining -= stored_paid
    debt_added = remaining
    return (
        gold - wallet_paid - debt_added,
        stored_gold - stored_paid,
        wallet_paid,
        stored_paid,
        debt_added,
    )


def loss_collection_note(stored_paid: int, debt_added: int) -> str:
    notes = []
    if stored_paid:
        notes.append(f"已从储值积蓄偿还 🏦 **{stored_paid}**")
    if debt_added:
        notes.append(f"新增负债 🧾 **{debt_added}**")
    return f"｜{'｜'.join(notes)}" if notes else ""


class SharedGoldWallet:
    def __init__(self, path: Path) -> None:
        self.path, self.lock = path, asyncio.Lock()

    async def balance(self, user_id: int) -> int:
        async with self.lock:
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                row = conn.execute("SELECT gold FROM shared_wallets WHERE user_id=?", (user_id,)).fetchone()
                return int(row[0]) if row else 0

    async def place_bet(self, user_id: int, bet: int) -> int | None:
        async with self.lock:
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                changed = conn.execute(
                    "UPDATE shared_wallets SET gold=gold-? WHERE user_id=? AND gold>=?",
                    (bet, user_id, bet),
                ).rowcount
                if changed != 1:
                    conn.rollback()
                    return None
                balance = conn.execute("SELECT gold FROM shared_wallets WHERE user_id=?", (user_id,)).fetchone()[0]
                conn.commit()
                return int(balance)

    async def credit(self, user_id: int, amount: int) -> int:
        async with self.lock:
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("UPDATE shared_wallets SET gold=gold+? WHERE user_id=?", (amount, user_id))
                balance = conn.execute("SELECT gold FROM shared_wallets WHERE user_id=?", (user_id,)).fetchone()[0]
                conn.commit()
                return int(balance)

    @staticmethod
    def _ensure_streak_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS casino_streaks ("
            "user_id INTEGER NOT NULL, game TEXT NOT NULL, "
            "streak INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, game))"
        )

    async def record_result(self, user_id: int, game: str, result: str) -> tuple[int, int]:
        async with self.lock:
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_streak_table(conn)
                conn.execute(
                    "INSERT OR IGNORE INTO casino_streaks(user_id, game, streak) VALUES (?, ?, 0)",
                    (user_id, game),
                )
                previous = int(conn.execute(
                    "SELECT streak FROM casino_streaks WHERE user_id=? AND game=?",
                    (user_id, game),
                ).fetchone()[0])
                current = previous + 1 if result == "win" else 0 if result == "loss" else previous
                conn.execute(
                    "UPDATE casino_streaks SET streak=? WHERE user_id=? AND game=?",
                    (current, user_id, game),
                )
                conn.commit()
                return previous, current

    async def reset_streak(self, user_id: int, game: str) -> int:
        async with self.lock:
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_streak_table(conn)
                conn.execute(
                    "INSERT OR IGNORE INTO casino_streaks(user_id, game, streak) VALUES (?, ?, 0)",
                    (user_id, game),
                )
                previous = int(conn.execute(
                    "SELECT streak FROM casino_streaks WHERE user_id=? AND game=?",
                    (user_id, game),
                ).fetchone()[0])
                conn.execute(
                    "UPDATE casino_streaks SET streak=0 WHERE user_id=? AND game=?",
                    (user_id, game),
                )
                conn.commit()
                return previous

    async def collect_loss_penalty(self, user_id: int, amount: int) -> tuple[int, int, int]:
        async with self.lock:
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                wallet_row = conn.execute(
                    "SELECT gold FROM shared_wallets WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                gold = int(wallet_row[0]) if wallet_row else 0
                state_row = conn.execute(
                    "SELECT state FROM players WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                state = {}
                if state_row:
                    try:
                        state = json.loads(state_row[0])
                    except (TypeError, ValueError, json.JSONDecodeError):
                        state = {}
                stored_gold = max(0, int(state.get("stored_gold", 0)))
                new_gold, new_stored, _, stored_paid, debt_added = apply_loss_collection(
                    gold,
                    stored_gold,
                    amount,
                )
                if wallet_row is None:
                    conn.execute(
                        "INSERT INTO shared_wallets(user_id, gold, crystals) VALUES (?, ?, 0)",
                        (user_id, new_gold),
                    )
                else:
                    conn.execute(
                        "UPDATE shared_wallets SET gold=? WHERE user_id=?",
                        (new_gold, user_id),
                    )
                if state_row and new_stored != stored_gold:
                    state["stored_gold"] = new_stored
                    conn.execute(
                        "UPDATE players SET state=? WHERE user_id=?",
                        (json.dumps(state, ensure_ascii=False), user_id),
                    )
                conn.commit()
                return new_gold, stored_paid, debt_added


def embed(title: str, text: str, colour: int = 0x6B1726) -> discord.Embed:
    return discord.Embed(title=title, description=text, colour=colour)


def card_file(cards: list[tuple[str, int] | None], filename: str = "table-cards.png") -> discord.File:
    data, name = render_cards(cards, filename)
    return discord.File(data, filename=name)


def dice_file(rolls: list[int], filename: str = "player-dice.png") -> discord.File:
    data, name = render_dice(rolls, filename)
    return discord.File(data, filename=name)


class OwnedView(discord.ui.View):
    def __init__(self, owner_id: int, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("这张牌桌属于另一位客人。", ephemeral=True)
        return False

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        traceback.print_exception(type(error), error, error.__traceback__)
        message = "牌桌刚才出了点问题，下注未完成。请关闭这张私密牌桌后重新进入。"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class ReplayButton(discord.ui.Button):
    def __init__(self, owner_id: int, wallet: SharedGoldWallet, game: str) -> None:
        super().__init__(label="再来一局", style=discord.ButtonStyle.success, row=4)
        self.owner_id, self.wallet, self.game = owner_id, wallet, game

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.game == "blackjack":
            view = BlackjackTable(self.owner_id, self.wallet)
            await interaction.response.edit_message(embed=view.table_embed(), view=view, attachments=[])
        elif self.game == "dice":
            view = DiceBluffTable(self.owner_id, self.wallet)
            await interaction.response.edit_message(embed=view.table_embed(), view=view, attachments=[])
        else:
            view = HighLowModeView(self.owner_id, self.wallet)
            await interaction.response.edit_message(embed=embed("比大小｜选择牌桌", "选择普通桌、三连桌或五连桌；所有操作会继续在本面板刷新。"), view=view, attachments=[])


class WagerSelect(discord.ui.Select):
    def __init__(self, table: "WagerTable") -> None:
        self.table = table
        super().__init__(
            placeholder=f"下注金额：{table.bet} 金币",
            options=[discord.SelectOption(label=f"🪙 {value} 金币", value=str(value)) for value in table.bet_options],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if getattr(self.table, "bet_reserved", False):
            await interaction.response.send_message("连胜局已经开始，途中不能更改下注。", ephemeral=True)
            return
        self.table.bet = int(self.values[0])
        await interaction.response.edit_message(embed=self.table.table_embed(), view=self.table)


class CustomWagerModal(discord.ui.Modal, title="设置下注金额"):
    amount = discord.ui.TextInput(label="金币数量", placeholder="输入任意正整数", min_length=1, max_length=9)

    def __init__(self, table: "WagerTable") -> None:
        super().__init__()
        self.table = table

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if getattr(self.table, "bet_reserved", False):
            await interaction.response.send_message("连胜局已经开始，途中不能更改下注。", ephemeral=True)
            return
        try:
            value = int(self.amount.value)
        except ValueError:
            value = 0
        balance = await self.table.wallet.balance(self.table.owner_id)
        if value < self.table.min_bet or value > balance or (self.table.max_bet is not None and value > self.table.max_bet):
            upper = min(balance, self.table.max_bet) if self.table.max_bet is not None else balance
            await interaction.response.send_message(f"请输入 {self.table.min_bet} 到 {upper} 之间的金币数。", ephemeral=True)
            return
        self.table.bet = value
        await interaction.response.edit_message(embed=self.table.table_embed(), view=self.table)


class WagerTable(OwnedView):
    game_key = ""

    def __init__(self, owner_id: int, wallet: SharedGoldWallet, *, min_bet: int = 1, max_bet: int | None = MAX_ROUND_STAKE, bet_options: tuple[int, ...] = BET_OPTIONS) -> None:
        super().__init__(owner_id)
        self.wallet, self.bet = wallet, 10
        self.max_bet = max_bet
        self.min_bet = min_bet
        self.bet_options = tuple(value for value in bet_options if value >= min_bet and (max_bet is None or value <= max_bet))
        self.bet = self.bet_options[0] if self.bet_options else min_bet
        self.add_item(WagerSelect(self))

    @discord.ui.button(label="自定义下注", emoji="✍️", style=discord.ButtonStyle.secondary, row=1)
    async def custom_bet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CustomWagerModal(self))

    @discord.ui.button(label="连胜归零", emoji="🧹", style=discord.ButtonStyle.secondary, row=1)
    async def clear_streak(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if getattr(self, "bet_reserved", False):
            await interaction.response.send_message("本局已经开始，结算后才能手动清零连胜。", ephemeral=True)
            return
        previous = await self.wallet.reset_streak(self.owner_id, self.game_key)
        await interaction.response.send_message(
            f"已将本玩法连胜从 **{previous}** 手动归零。",
            ephemeral=True,
        )

    async def reserve(self, interaction: discord.Interaction) -> bool:
        if await self.wallet.place_bet(self.owner_id, self.bet) is not None:
            return True
        balance = await self.wallet.balance(self.owner_id)
        await interaction.response.send_message(f"金币不足。你现在只有 🪙 **{balance}**。", ephemeral=True)
        return False

    def table_embed(self) -> discord.Embed:
        raise NotImplementedError


class HighLowModeView(OwnedView):
    def __init__(self, owner_id: int, wallet: SharedGoldWallet) -> None:
        super().__init__(owner_id)
        self.wallet = wallet

    async def open_table(self, interaction: discord.Interaction, *, blind: bool, target_wins: int) -> None:
        table = HighLowTable(self.owner_id, self.wallet, blind=blind, target_wins=target_wins)
        picture = table.picture()
        shown = table.table_embed()
        shown.set_image(url="attachment://table-cards.jpg")
        await interaction.response.edit_message(embed=shown, view=table, attachments=[picture])

    @discord.ui.button(label="普通明赌｜1–100", style=discord.ButtonStyle.primary, row=0)
    async def seen(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_table(interaction, blind=False, target_wins=1)

    @discord.ui.button(label="普通盲赌｜1–100", style=discord.ButtonStyle.secondary, row=0)
    async def blind(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_table(interaction, blind=True, target_wins=1)

    @discord.ui.button(label="三连明赌｜101–300", style=discord.ButtonStyle.success, row=1)
    async def triple_seen(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_table(interaction, blind=False, target_wins=3)

    @discord.ui.button(label="三连盲赌｜101–300", style=discord.ButtonStyle.danger, row=1)
    async def triple_blind(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_table(interaction, blind=True, target_wins=3)

    @discord.ui.button(label="五连明赌｜301–1000", style=discord.ButtonStyle.success, row=2)
    async def five_seen(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_table(interaction, blind=False, target_wins=5)

    @discord.ui.button(label="五连盲赌｜301–1000", style=discord.ButtonStyle.danger, row=2)
    async def five_blind(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_table(interaction, blind=True, target_wins=5)


class HighLowTable(WagerTable):
    game_key = "highlow"

    def __init__(self, owner_id: int, wallet: SharedGoldWallet, blind: bool, target_wins: int = 1) -> None:
        if target_wins == 5:
            super().__init__(owner_id, wallet, min_bet=301, max_bet=1000, bet_options=(301, 500, 800, 1000))
        elif target_wins == 3:
            super().__init__(owner_id, wallet, min_bet=101, max_bet=300, bet_options=(101, 200, 300))
        else:
            super().__init__(owner_id, wallet, max_bet=100, bet_options=(10, 50, 100))
        self.blind = blind
        self.target_wins = target_wins
        self.player = (random.choice(SUITS), random.randint(2, 14))
        self.streak = 0
        self.bet_reserved = False
        self.rounds: list[list[tuple[str, int]]] = []

    def picture(self, include_next: bool = True, state: str = "neutral") -> discord.File:
        data, name = render_yan_cards(self.rounds, None if self.blind else self.player, include_next, state=state, filename="table-cards.jpg")
        return discord.File(data, filename=name)

    def table_embed(self) -> discord.Embed:
        mode = "盲赌" if self.blind else "明赌"
        payout = "1:1（原赔率利润的 50%）" if self.blind else "0.5:1（原赔率利润的 50%）"
        challenge = f"{self.target_wins} 连胜局｜当前 **{self.streak}/{self.target_wins}**" if self.target_wins > 1 else "普通单局"
        rule = f"必须连续赢满 {self.target_wins} 局才结算；每局开牌都会保留在牌路中，途中输一局便失去整笔本金。" if self.target_wins > 1 else "一局定胜负。"
        result = embed("比大小｜下注", f"模式：**{mode}**｜当前下注：🪙 **{self.bet}**｜{challenge}｜净赢赔率：**{payout}**\n\n{rule}\n\n{'你的牌仍然盖着。' if self.blind else '你已经看过自己的牌。'}现在可以改注，再选择比大或比小。")
        result.set_image(url="attachment://table-cards.jpg")
        return result

    async def play(self, interaction: discord.Interaction, guess: str) -> None:
        if self.max_bet is not None and self.bet > self.max_bet:
            await interaction.response.send_message(f"本桌单笔最高只能下注 {self.max_bet} 金币。", ephemeral=True)
            return
        if not self.bet_reserved:
            if not await self.reserve(interaction): return
            self.bet_reserved = True
        await interaction.response.defer()
        dealer = (random.choice(SUITS), random.randint(2, 14))
        player = self.player
        tied = dealer[1] == player[1]
        won = not tied and ((player[1] > dealer[1]) == (guess == "high"))
        high_stakes = self.target_wins > 1
        self.rounds.append([player, dealer])
        if won:
            self.streak += 1
        completed = won and (not high_stakes or self.streak >= self.target_wins)
        continuing = high_stakes and won and not completed
        balance = await self.wallet.balance(self.owner_id)
        if continuing:
            note = f"本局获胜，连胜 **{self.streak}/{self.target_wins}**。本金与奖金仍在桌上；下方第三张是下一局你的牌。"
            self.player = (random.choice(SUITS), random.randint(2, 14))
        elif completed:
            _, casino_streak = await self.wallet.record_result(self.owner_id, self.game_key, "win")
            original_profit = self.bet * (2 if self.blind else 1)
            profit = scaled_win_profit(self.bet, original_profit, casino_streak)
            rate = streak_bonus_rate(casino_streak)
            balance = await self.wallet.credit(self.owner_id, self.bet + profit)
            note = (
                f"{f'{self.target_wins} 连胜达成！' if high_stakes else ''}"
                f"净赢 🪙 **{profit}**｜累计连胜 **{casino_streak}**｜"
                f"连胜加成 **{rate}%**｜余额 🪙 **{balance}**"
            )
            for item in self.children: item.disabled = True
        else:
            previous_streak, _ = await self.wallet.record_result(self.owner_id, self.game_key, "loss")
            rate = streak_bonus_rate(previous_streak)
            penalty = loss_penalty(self.bet, previous_streak)
            balance, stored_paid, debt_added = await self.wallet.collect_loss_penalty(
                self.owner_id,
                penalty,
            )
            reason = "双方同点，按规则由庄家获胜。" if tied else ("连胜中断。" if high_stakes else "本局未押中。")
            note = (
                f"{reason}共失去 🪙 **{self.bet + penalty}**｜"
                f"原连胜 **{previous_streak}** 已归零｜追加扣款 **{rate}%**"
                f"{loss_collection_note(stored_paid, debt_added)}｜余额 🪙 **{balance}**"
            )
            for item in self.children: item.disabled = True
        if not continuing:
            self.add_item(ReplayButton(self.owner_id, self.wallet, "highlow"))
        result = embed("开牌", f"你的牌与庄家牌如下。\n\n{note}", 0x57F287 if won else 0xED4245)
        picture = self.picture(include_next=continuing, state="lose" if completed else "neutral")
        result.set_image(url="attachment://table-cards.jpg")
        await interaction.edit_original_response(embed=result, view=self, attachments=[picture])

    @discord.ui.button(label="押我的牌更大", emoji="🔺", style=discord.ButtonStyle.primary, row=2)
    async def high(self, interaction: discord.Interaction, _: discord.ui.Button): await self.play(interaction, "high")
    @discord.ui.button(label="押我的牌更小", emoji="🔻", style=discord.ButtonStyle.primary, row=2)
    async def low(self, interaction: discord.Interaction, _: discord.ui.Button): await self.play(interaction, "low")


def hand_value(hand: list[tuple[str, int]]) -> int:
    ranks = [card[1] for card in hand]
    value = sum(11 if rank == 14 else min(rank, 10) for rank in ranks)
    aces = ranks.count(14)
    while value > 21 and aces:
        value, aces = value - 10, aces - 1
    return value


def hand_text(hand: list[tuple[str, int]], hide_first: bool = False) -> str:
    values = [f"{SUIT_MARKS[card[0]]}{RANK_NAMES.get(card[1], card[1])}" for card in hand]
    if hide_first: values[0] = "🂠"
    return "　".join(f"`{value}`" for value in values)


class BlackjackGame(OwnedView):
    def __init__(self, owner_id: int, wallet: SharedGoldWallet, bet: int) -> None:
        super().__init__(owner_id)
        self.wallet, self.bet = wallet, bet
        deck = [(suit, rank) for suit in SUITS for rank in range(2, 15)]
        random.shuffle(deck)
        self.deck = deck
        self.hands = [[deck.pop(), deck.pop()]]
        self.bets = [bet]
        self.dealer = [deck.pop(), deck.pop()]
        self.active = 0
        self.finished: set[int] = set()
        self.split_used = False
        self.insurance_decided = self.dealer[1][1] != 14
        self._refresh_buttons()

    @property
    def player(self) -> list[tuple[str, int]]:
        return self.hands[self.active]

    def dealer_blackjack(self) -> bool:
        return len(self.dealer) == 2 and hand_value(self.dealer) == 21

    def _refresh_buttons(self) -> None:
        hand = self.player
        first_action = len(hand) == 2 and self.active not in self.finished
        self.hit.disabled = hand_value(hand) >= 21
        self.double.disabled = not first_action or hand_value(hand) == 21
        self.split.disabled = not (
            first_action and not self.split_used and hand[0][1] == hand[1][1]
        )
        self.insurance.disabled = self.insurance_decided or self.dealer[1][1] != 14

    def game_embed(self, reveal: bool = False, note: str = "") -> discord.Embed:
        dealer_value = hand_value(self.dealer) if reveal else "?"
        hand_lines = []
        for index, hand in enumerate(self.hands):
            marker = "👉" if index == self.active and index not in self.finished else "▫️"
            state = "（已停）" if index in self.finished else ""
            hand_lines.append(f"{marker} 手牌 {index + 1}：{hand_text(hand)}　**{hand_value(hand)}**　下注 🪙 **{self.bets[index]}**{state}")
        result = embed("Blackjack", f"庄家点数：**{dealer_value}**\n\n" + "\n".join(hand_lines) + note)
        result.set_image(url="attachment://blackjack-cards.jpg")
        return result

    def picture(self, reveal: bool = False, state: str = "neutral") -> discord.File:
        dealer_cards: list[tuple[str, int] | None] = ([self.dealer[0]] if reveal else [None]) + self.dealer[1:]
        data, name = render_yan_blackjack(dealer_cards, list(self.player), state=state, filename="blackjack-cards.jpg")
        return discord.File(data, filename=name)

    async def dealer_check(self, interaction: discord.Interaction) -> bool:
        if self.insurance_decided:
            return True
        self.insurance_decided = True
        if self.dealer_blackjack():
            await self.settle(interaction, dealer_has_blackjack=True)
            return False
        self._refresh_buttons()
        return True

    async def advance(self, interaction: discord.Interaction) -> None:
        remaining = [index for index in range(len(self.hands)) if index not in self.finished]
        if remaining:
            self.active = remaining[0]
            self._refresh_buttons()
            await interaction.response.edit_message(embed=self.game_embed(), view=self, attachments=[self.picture()])
            return
        await self.settle(interaction)

    async def settle(self, interaction: discord.Interaction, dealer_has_blackjack: bool = False, insurance_payout: int = 0) -> None:
        if not dealer_has_blackjack:
            while hand_value(self.dealer) < 17:
                self.dealer.append(self.deck.pop())
        dealer_value = hand_value(self.dealer)
        payouts, lines = insurance_payout, []
        for index, hand in enumerate(self.hands):
            value, wager = hand_value(hand), self.bets[index]
            natural = len(hand) == 2 and value == 21 and not self.split_used
            if dealer_has_blackjack:
                payout, label = (wager, "平局") if natural else (0, "庄家 Blackjack")
            elif value > 21:
                payout, label = 0, "爆牌"
            elif natural:
                payout, label = wager * 5 // 2, "Blackjack 3:2"
            elif dealer_value > 21 or value > dealer_value:
                payout, label = wager * 2, "胜 1:1"
            elif value == dealer_value:
                payout, label = wager, "平局退注"
            else:
                payout, label = 0, "负"
            payouts += payout
            lines.append(f"手牌 {index + 1}：**{value} 点｜{label}**")
        total_stake = sum(self.bets)
        outcome = "win" if payouts > total_stake else "push" if payouts == total_stake else "loss"
        previous_streak, streak = await self.wallet.record_result(self.owner_id, "blackjack", outcome)
        stored_paid = debt_added = penalty = 0
        if outcome == "win":
            original_profit = payouts - total_stake
            profit = scaled_win_profit(total_stake, original_profit, streak)
            rate = streak_bonus_rate(streak)
            bonus = total_stake * rate // 100
            payouts = total_stake + profit
            balance = await self.wallet.credit(self.owner_id, payouts)
            streak_note = (
                f"\n连胜：**{streak}**｜基础利润按原赔率的 **50%** 结算｜"
                f"连胜加成：**{rate}%**"
                + (f"｜连胜奖励 🪙 **{bonus}**" if bonus else "")
            )
        elif outcome == "push":
            rate = streak_bonus_rate(streak)
            balance = await self.wallet.credit(self.owner_id, payouts)
            streak_note = f"\n平局不断档｜当前连胜：**{streak}**"
        else:
            if payouts:
                await self.wallet.credit(self.owner_id, payouts)
            rate = streak_bonus_rate(previous_streak)
            penalty = loss_penalty(total_stake, previous_streak)
            balance, stored_paid, debt_added = await self.wallet.collect_loss_penalty(
                self.owner_id,
                penalty,
            )
            net_loss = total_stake - payouts + penalty
            streak_note = (
                f"\n本局净损失：🪙 **{net_loss}**｜原连胜 **{previous_streak}** 已归零｜"
                f"追加扣款：**{rate}%**"
                f"{loss_collection_note(stored_paid, debt_added)}"
            )
        for item in self.children:
            item.disabled = True
        self.add_item(ReplayButton(self.owner_id, self.wallet, "blackjack"))
        result = self.game_embed(True, "\n\n" + "\n".join(lines) + streak_note + f"\n\n余额：🪙 **{balance}**")
        result.colour = 0x57F287 if outcome == "win" else 0xFEE75C if outcome == "push" else 0xED4245
        await interaction.response.edit_message(embed=result, view=self, attachments=[self.picture(True, "lose" if outcome == "win" else "neutral")])

    @discord.ui.button(label="要牌", emoji="➕", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.dealer_check(interaction): return
        self.player.append(self.deck.pop())
        self.double.disabled = True
        self.split.disabled = True
        if hand_value(self.player) >= 21:
            self.finished.add(self.active)
            await self.advance(interaction)
        else:
            await interaction.response.edit_message(embed=self.game_embed(), view=self, attachments=[self.picture()])

    @discord.ui.button(label="停牌", emoji="✋", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.dealer_check(interaction): return
        self.finished.add(self.active)
        await self.advance(interaction)

    @discord.ui.button(label="加倍下注", emoji="⏫", style=discord.ButtonStyle.danger)
    async def double(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.dealer_check(interaction): return
        wager = self.bets[self.active]
        if sum(self.bets) + wager > MAX_ROUND_STAKE:
            await interaction.response.send_message("本局累计投入不能超过 3000 金币。", ephemeral=True)
            return
        if await self.wallet.place_bet(self.owner_id, wager) is None:
            await interaction.response.send_message("金币不足，无法加倍。", ephemeral=True)
            return
        self.bets[self.active] *= 2
        self.player.append(self.deck.pop())
        self.finished.add(self.active)
        await self.advance(interaction)

    @discord.ui.button(label="分牌", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def split(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.dealer_check(interaction): return
        wager = self.bets[self.active]
        if sum(self.bets) + wager > MAX_ROUND_STAKE:
            await interaction.response.send_message("本局累计投入不能超过 3000 金币。", ephemeral=True)
            return
        if await self.wallet.place_bet(self.owner_id, wager) is None:
            await interaction.response.send_message("金币不足，无法为第二手牌补下注。", ephemeral=True)
            return
        first, second = self.player
        self.hands = [[first, self.deck.pop()], [second, self.deck.pop()]]
        self.bets = [wager, wager]
        self.active, self.split_used = 0, True
        if first[1] == 14:
            self.finished.update((0, 1))
            await self.settle(interaction)
            return
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.game_embed(note="\n\n已分为两手牌，依次操作。"), view=self, attachments=[self.picture()])

    @discord.ui.button(label="保险", emoji="🛡️", style=discord.ButtonStyle.success)
    async def insurance(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        stake = max(1, self.bet // 2)
        if sum(self.bets) + stake > MAX_ROUND_STAKE:
            await interaction.response.send_message("购买保险后，本局累计投入会超过 3000 金币。", ephemeral=True)
            return
        if await self.wallet.place_bet(self.owner_id, stake) is None:
            await interaction.response.send_message("金币不足，无法购买保险。", ephemeral=True)
            return
        self.insurance_decided = True
        if self.dealer_blackjack():
            await self.settle(interaction, dealer_has_blackjack=True, insurance_payout=stake * 3)
            return
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.game_embed(note=f"\n\n保险下注 🪙 **{stake}** 已失去；庄家没有 Blackjack，牌局继续。"), view=self, attachments=[self.picture()])


class BlackjackTable(WagerTable):
    game_key = "blackjack"

    def table_embed(self) -> discord.Embed:
        return embed(
            "Blackjack｜入局",
            f"下注：🪙 **{self.bet}**\n\n"
            "**目标：你的点数要比庄家大，但绝对不能超过 21。**\n\n"
            "**点数怎么算**\n"
            "• 2–10：牌面写多少就是多少。\n"
            "• J、Q、K：都算 10 点。\n"
            "• A：自动按最有利的情况算 1 或 11 点。\n\n"
            "**按钮是什么意思**\n"
            "• **要牌**：再拿一张；总点数超过 21 就立刻输。\n"
            "• **停牌**：不要了，轮到庄家拿牌。\n"
            "• **加倍下注**：再押同样金币，只再拿一张，然后自动停牌。\n"
            "• **分牌**：起手两张点数相同，可拆成两手；第二手要再押一份相同赌注。\n"
            "• **保险**：只有庄家亮出 A 时出现。你额外押原注的一半，赌庄家的暗牌是 10/J/Q/K、正好组成 Blackjack；猜中保险按 2:1 净赢，猜错保险金归庄家，原来的牌局照常继续。**保险不是保你这局不输。**\n\n"
            "**怎么结算**\n"
            "普通胜利原赔率 1:1｜起手两张正好 21 点原赔率 3:2｜同点退回本金｜庄家 17 点必须停牌。\n"
            "实际基础净利润按原赔率的 50% 结算。\n"
            "\n\n连续获胜奖励：3 连胜 +30%｜5 连胜 +80%｜7 连胜起 +100%；失败会按失败前档位追加扣款并归零，平局不断档。",
        )

    @discord.ui.button(label="发牌", style=discord.ButtonStyle.success, row=1)
    async def deal(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.reserve(interaction): return
        game = BlackjackGame(self.owner_id, self.wallet, self.bet)
        dealer_up = game.dealer[1][1]
        if dealer_up in (10, 11, 12, 13) and game.dealer_blackjack():
            await game.settle(interaction, dealer_has_blackjack=True)
            return
        if hand_value(game.player) == 21 and dealer_up != 14:
            game.finished.add(0)
            await game.settle(interaction)
            return
        await interaction.response.edit_message(embed=game.game_embed(), view=game, attachments=[game.picture()])


class BidQuantitySelect(discord.ui.Select):
    def __init__(self, game: "DiceBluffGame") -> None:
        self.game = game
        super().__init__(placeholder="选择数量（1–10）", options=[discord.SelectOption(label=f"{value} 个", value=str(value)) for value in range(1, 11)], row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.game.draft_quantity = int(self.values[0])
        await interaction.response.edit_message(embed=self.game.game_embed("已选择数量；还可以调整点数，确认后才正式叫点。"), view=self.game, attachments=[self.game.picture()])


class BidFaceSelect(discord.ui.Select):
    def __init__(self, game: "DiceBluffGame") -> None:
        self.game = game
        super().__init__(placeholder="选择点数（2–6）", options=[discord.SelectOption(label=f"{value} 点", value=str(value)) for value in range(2, 7)], row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.game.draft_face = int(self.values[0])
        await interaction.response.edit_message(embed=self.game.game_embed("已选择点数；还可以调整数量，确认后才正式叫点。"), view=self.game, attachments=[self.game.picture()])


class DiceBluffGame(OwnedView):
    def __init__(self, owner_id: int, wallet: SharedGoldWallet, bet: int) -> None:
        super().__init__(owner_id)
        self.wallet, self.bet = wallet, bet
        self.player = [random.randint(1, 6) for _ in range(5)]
        self.dealer = [random.randint(1, 6) for _ in range(5)]
        self.quantity, self.face, self.done = 2, random.randint(2, 6), False
        self.draft_quantity, self.draft_face = self.quantity, self.face
        self.history = [f"晏青川：**{self.quantity} 个 {self.face}**"]
        self.add_item(BidQuantitySelect(self))
        self.add_item(BidFaceSelect(self))

    def game_embed(self, note: str = "晏青川先叫。") -> discord.Embed:
        draft = f"准备叫：**{self.draft_quantity} 个 {self.draft_face}**"
        history = "\n".join(self.history[-4:])
        result = embed("骰子吹牛", f"你的骰子只对你展示。\n\n当前叫点：**{self.quantity} 个 {self.face}**｜{draft}\n当前总注：🪙 **{self.bet}**\n*1 点可作任意点数；新叫点必须提高数量，或在数量相同时提高点数。*\n\n**最近叫点**\n{history}\n\n{note}")
        result.set_image(url="attachment://player-dice.jpg")
        return result

    def picture(self, reveal: bool = False, state: str = "neutral") -> discord.File:
        data, name = render_yan_dice(self.player, self.dealer, reveal, state=state, filename="player-dice.jpg")
        return discord.File(data, filename=name)

    async def settle(self, interaction: discord.Interaction, challenger_wins: bool, note: str) -> None:
        self.done = True
        for item in self.children: item.disabled = True
        previous_streak, streak = await self.wallet.record_result(
            self.owner_id,
            "dice",
            "win" if challenger_wins else "loss",
        )
        if challenger_wins:
            rate = streak_bonus_rate(streak)
            profit = scaled_win_profit(self.bet, self.bet, streak)
            bonus = self.bet * rate // 100
            balance = await self.wallet.credit(self.owner_id, self.bet + profit)
            settlement = (
                f"净赢 🪙 **{profit}**｜连胜 **{streak}**｜加成 **{rate}%**"
                + (f"（连胜奖励 🪙 {bonus}）" if bonus else "")
            )
        else:
            rate = streak_bonus_rate(previous_streak)
            penalty = loss_penalty(self.bet, previous_streak)
            balance, stored_paid, debt_added = await self.wallet.collect_loss_penalty(
                self.owner_id,
                penalty,
            )
            settlement = (
                f"共失去 🪙 **{self.bet + penalty}**｜原连胜 **{previous_streak}** 已归零｜"
                f"追加扣款 **{rate}%**{loss_collection_note(stored_paid, debt_added)}"
            )
        self.add_item(ReplayButton(self.owner_id, self.wallet, "dice"))
        result = self.game_embed(f"{note}\n{settlement}｜余额 🪙 **{balance}**")
        result.colour = 0x57F287 if challenger_wins else 0xED4245
        await interaction.response.edit_message(embed=result, view=self, attachments=[self.picture(True, "lose" if challenger_wins else "neutral")])

    async def dealer_turn(self, interaction: discord.Interaction) -> None:
        actual = sum(value in (1, self.face) for value in self.player + self.dealer)
        own_support = sum(value in (1, self.face) for value in self.dealer)
        expected_total = own_support + 5 * (2 / 6)
        challenge_chance = 0.68 if self.quantity > expected_total else 0.18
        if (self.quantity == 10 and self.face == 6) or random.random() < challenge_chance:
            bid_holds = dice_bid_holds(actual, self.quantity)
            verdict = "这句叫点是真的。" if bid_holds else "你叫高了。"
            await self.settle(
                interaction,
                bid_holds,
                f"晏青川开盅。实际共有 **{actual} 个 {self.face}**，{verdict}",
            )
            return
        if self.face < 6 and random.random() < 0.45:
            self.face += 1
        else:
            self.quantity = min(10, self.quantity + 1)
            self.face = random.randint(2, 6)
        self.history.append(f"晏青川：**{self.quantity} 个 {self.face}**")
        self.draft_quantity, self.draft_face = self.quantity, self.face
        await interaction.response.edit_message(embed=self.game_embed("晏青川已经回应。现在轮到你重新组合下一口叫点。"), view=self, attachments=[self.picture()])

    @discord.ui.button(label="确认叫点", emoji="📣", style=discord.ButtonStyle.primary, row=2)
    async def submit_bid(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        legal = legal_dice_bid(self.draft_quantity, self.draft_face, self.quantity, self.face)
        if not legal:
            await interaction.response.send_message(
                f"这一口不能低于或等于 **{self.quantity} 个 {self.face}**。请提高数量，或保持数量并提高点数。",
                ephemeral=True,
            )
            return
        self.quantity, self.face = self.draft_quantity, self.draft_face
        self.history.append(f"你：**{self.quantity} 个 {self.face}**")
        await self.dealer_turn(interaction)

    @discord.ui.button(label="开盅", emoji="💥", style=discord.ButtonStyle.danger, row=2)
    async def challenge(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        actual = sum(value in (1, self.face) for value in self.player + self.dealer)
        won = not dice_bid_holds(actual, self.quantity)
        await self.settle(interaction, won, f"开盅！实际共有 **{actual} 个 {self.face}**。{'晏先生这次说了大话。' if won else '这句叫点是真的。'}")

    @discord.ui.button(label="加倍赌注", emoji="🪙", style=discord.ButtonStyle.success, row=2)
    async def raise_stakes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.bet * 2 > MAX_ROUND_STAKE:
            await interaction.response.send_message("本局累计投入不能超过 3000 金币。", ephemeral=True)
            return
        if await self.wallet.place_bet(self.owner_id, self.bet) is None:
            await interaction.response.send_message("金币不足，无法继续加码。", ephemeral=True)
            return
        self.bet *= 2
        await interaction.response.edit_message(embed=self.game_embed("赌注翻倍。晏青川微笑着示意牌局继续。"), view=self, attachments=[self.picture()])


class DiceBluffTable(WagerTable):
    game_key = "dice"

    def table_embed(self) -> discord.Embed:
        return embed("骰子吹牛｜入局", f"下注：🪙 **{self.bet}**\n\n**新手玩法**：双方各摇五枚骰子，只看自己的五枚。叫点是猜双方十枚骰子合计有多少个某点数，例如“3 个 5”。下一口必须增加数量，或保持数量并提高点数；怀疑上一口是吹牛便开盅。\n\n**本桌带 1**：骰出的 **1 可以当作任何点数**。例如开盅数“5”时，所有 1 点和 5 点都会算作 5。\n\n基础净利润按原赔率的 50% 结算；3 连胜 +30%｜5 连胜 +80%｜7 连胜起 +100%。失败会按失败前档位追加扣款并将连胜归零。")

    @discord.ui.button(label="摇骰入局", style=discord.ButtonStyle.success, row=1)
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self.reserve(interaction): return
        game = DiceBluffGame(self.owner_id, self.wallet, self.bet)
        await interaction.response.edit_message(embed=game.game_embed(), view=game, attachments=[game.picture()])


class CasinoMenuView(discord.ui.View):
    def __init__(self, wallet: SharedGoldWallet) -> None:
        super().__init__(timeout=None)
        self.wallet = wallet

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        traceback.print_exception(type(error), error, error.__traceback__)
        message = "赌场入口暂时没有响应，错误已经记录。请稍后再试。"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label="比大小", style=discord.ButtonStyle.primary, custom_id="yan-casino:high-low")
    async def high_low(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        view = HighLowModeView(interaction.user.id, self.wallet)
        await interaction.response.send_message(
            embed=embed("比大小｜选择牌桌", "**新手玩法**：你与晏青川各抽一张牌，选择押自己的牌更大或更小，再同时开牌；点数从 2 到 A，A 最大。**双方同点时算庄家赢。**\n\n**普通桌**：下注 1–100 金币，一局定胜负。\n**三连桌**：下注 101–300 金币，必须连续赢三局。\n**五连桌**：下注 301–1000 金币，必须连续赢五局。\n\n连胜桌会保留每局开出的双方牌；途中输一局或双方同点，整笔下注归零。明赌先看自己的牌，原赔率 1:1；盲赌不看牌，原赔率 2:1。实际基础净利润按原赔率的 50% 结算，并叠加 3/5/7 连胜的 30%/80%/100% 奖励；失败按失败前档位追加扣款。"),
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Blackjack", style=discord.ButtonStyle.secondary, custom_id="yan-casino:blackjack")
    async def blackjack(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        table = BlackjackTable(interaction.user.id, self.wallet)
        await interaction.followup.send(embed=table.table_embed(), view=table, ephemeral=True)

    @discord.ui.button(label="骰子吹牛", style=discord.ButtonStyle.success, custom_id="yan-casino:liars-dice")
    async def liars_dice(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        table = DiceBluffTable(interaction.user.id, self.wallet)
        await interaction.response.send_message(embed=table.table_embed(), view=table, ephemeral=True)

    @discord.ui.button(label="我的金币", emoji="🪙", style=discord.ButtonStyle.secondary, custom_id="yan-casino:balance")
    async def balance(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(f"你现在有 🪙 **{await self.wallet.balance(interaction.user.id)}** 金币。", ephemeral=True)


def panel_embed(avatar_url: str | None = None) -> discord.Embed:
    result = embed(
        PANEL_TITLE,
        "> “落子无悔。诸位既然入席，便请守我的规矩。祝诸位赌运昌盛，满载而归。”\n\n"
        "请选择一张牌桌。进入后再决定下注与玩法，所有操作桌仅你可见。\n\n"
        "**比大小**｜一人一牌，与庄家定高低\n"
        "**Blackjack**｜要牌或停牌，逼近二十一点\n"
        "**骰子吹牛**｜藏骰叫点，不信便开盅\n\n"
        "金币与地下城、酒馆储值及金币商城实时共用。",
    )
    if avatar_url: result.set_thumbnail(url=avatar_url)
    result.set_footer(text="晏青川 · 愿赌服输")
    return result

