"""الألعاب: استثمار، تداول، رهان، نرد، قمار، حجر، تحدي، فواكه، لون، حظ، برج."""
import random

import discord

import config
import db
import render
import util
from cmds_general import win
from core import OwnerView, command, lock


async def get_bet(ctx):
    """يقرأ المبلغ ويتحقق منه. يرجع (user, amount) أو None بعد إرسال الخطأ."""
    u = ctx.user
    amount = ctx.amount_arg(u["balance"])
    if not amount:
        await ctx.text("اكتب المبلغ، مثال: `5k` أو `نص` أو `كامل`")
        return None
    if amount < config.MIN_BET:
        await ctx.text(f"أقل مبلغ {util.full(config.MIN_BET)}")
        return None
    if amount > u["balance"]:
        await ctx.text("رصيدك ما يكفي 💸")
        return None
    return u, amount


def signed(n):
    return f"{'+' if n >= 0 else '-'}{util.full(n)}"


# ------------------------------------------------------------------ استثمار / تداول
async def _invest(ctx, title, win_p, win_rng, lose_rng, cd_key, cd_secs):
    got = await get_bet(ctx)
    if not got:
        return
    u, amount = got
    left = db.cd_left(u, cd_key, cd_secs)
    if left:
        return await ctx.text(f"⏳ انتظر {util.dur(left)}")
    won = random.random() < win_p + 0.005 * db.perk(u, "luck")
    pct = random.randint(*(win_rng if won else lose_rng))
    delta = int(amount * pct / 100) * (1 if won else -1)
    u["balance"] += delta
    win(u, won)
    db.cd_set(u, cd_key)
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.chart_card, img, name, title, pct, signed(delta), util.short(u["balance"]),
                   won, random.randint(0, 10 ** 6))


@command("استثمار")
async def cmd_invest(ctx):
    await _invest(ctx, "استثمار", 0.52, (5, 45), (5, 25), "invest", 20)


@command("تداول")
async def cmd_trade(ctx):
    await _invest(ctx, "تداول", 0.48, (8, 70), (8, 45), "trade", 20)


# ------------------------------------------------------------------ رهان (عملة)
@command("رهان")
async def cmd_bet(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    u, amount = got
    won = random.random() < 0.475 + 0.005 * db.perk(u, "luck")
    delta = amount if won else -amount
    u["balance"] += delta
    win(u, won)
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.amount_card, img, name, "رهان", signed(delta), render.GREEN if won else render.RED,
                   "كسبت" if won else "خسرت", render.GREEN if won else render.RED,
                   "check" if won else "debt")


# ------------------------------------------------------------------ نرد ضد البنك
@command("نرد")
async def cmd_dice(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    u, amount = got
    a, b = random.randint(1, 6), random.randint(1, 6)
    if random.random() < 0.01 * db.perk(u, "luck") and a <= b:
        a = min(6, b + 1)
    delta = amount if a > b else (-amount if a < b else 0)
    u["balance"] += delta
    if delta:
        win(u, delta > 0)
    db.save(u)
    name, img = await ctx.me()
    bank_img = render.BRAND["logo"] or render.placeholder("B")
    text = "تعادل" if not delta else signed(delta)
    await ctx.card(render.vs_card, img, name, bank_img, "Bank.", a, b, text,
                   render.LIGHT if not delta else (render.GREEN if delta > 0 else render.RED))


# ------------------------------------------------------------------ قمار (سلوت)
SLOT = ["cherry", "lemon", "grape", "star", "seven"]
SLOT_AR = {"cherry": "كرز", "lemon": "ليمون", "grape": "عنب", "star": "نجمة", "seven": "سبعة"}


@command("قمار")
async def cmd_slots(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    u, amount = got
    reels = [random.choice(SLOT) for _ in range(3)]
    if len(set(reels)) == 1:
        mult = 6
    elif len(set(reels)) == 2:
        mult = 1.5
    else:
        mult = 0
    delta = int(amount * mult) - amount
    u["balance"] += delta
    win(u, delta > 0)
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.slots_card, img, name, reels, [SLOT_AR[r] for r in reels],
                   signed(delta), render.GREEN if delta > 0 else render.RED, "قمار")


# ------------------------------------------------------------------ حظ (عجلة)
@command("حظ")
async def cmd_luck(ctx):
    u = ctx.user
    left = db.cd_left(u, "luck", config.LUCK_COOLDOWN)
    if left:
        return await ctx.text(f"⏳ العجلة تدور بعد {util.dur(left)}")
    prizes = config.WHEEL_PRIZES
    idx = random.choices(range(len(prizes)), weights=config.WHEEL_WEIGHTS)[0]
    prize = int(prizes[idx] * (1 + 0.05 * db.perk(u, "luck")))
    u["balance"] += prize
    db.cd_set(u, "luck")
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.wheel_card, img, name, prizes, idx, f"فزت بـ {util.short(prize)}")


# ------------------------------------------------------------------ حجر ورقة مقص
RPS = {"rock": "🪨 حجر", "paper": "📄 ورقة", "scissors": "✂️ مقص"}
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


class RPSView(OwnerView):
    def __init__(self, ctx, amount):
        super().__init__(ctx.uid, timeout=45)
        self.ctx, self.amount = ctx, amount
        for k, label in RPS.items():
            b = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            b.callback = self.make(k)
            self.add_item(b)

    def make(self, mine):
        async def cb(interaction):
            async with lock(self.owner_id):
                u = db.get_user(self.owner_id)
                if u["balance"] < self.amount:
                    return await interaction.response.edit_message(content="رصيدك ما يكفي", view=None)
                theirs = random.choice(list(RPS))
                if mine == theirs:
                    delta, msg = 0, "تعادل 🤝"
                elif BEATS[mine] == theirs:
                    delta, msg = self.amount, "فزت 🎉"
                else:
                    delta, msg = -self.amount, "خسرت 😢"
                u["balance"] += delta
                if delta:
                    win(u, delta > 0)
                db.save(u)
            self.stop()
            await interaction.response.edit_message(
                content=f"{RPS[mine]}  ضد  {RPS[theirs]}\n**{msg}** {signed(delta) if delta else ''}", view=None)
        return cb


@command("حجر")
async def cmd_rps(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    view = RPSView(ctx, got[1])
    view.message = await ctx.text(f"اختر يا بطل — الرهان {util.full(got[1])}", view=view)


# ------------------------------------------------------------------ تحدي بين لاعبين
class DuelView(OwnerView):
    def __init__(self, ctx, target, amount):
        super().__init__(target.id, timeout=60)
        self.ctx, self.target, self.amount = ctx, target, amount

    @discord.ui.button(label="قبول ✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        a_id, b_id = self.ctx.uid, self.target.id
        first, second = sorted((a_id, b_id))
        async with lock(first):
            async with lock(second) if second != first else lock(-1):
                a, b = db.get_user(a_id), db.get_user(b_id)
                if a["balance"] < self.amount or b["balance"] < self.amount:
                    return await interaction.response.edit_message(content="أحدكم رصيده ما يكفي ❌", view=None)
                da = random.randint(1, 6) + random.randint(1, 6)
                db_ = random.randint(1, 6) + random.randint(1, 6)
                if da == db_:
                    delta = 0
                else:
                    delta = self.amount if da > db_ else -self.amount
                a["balance"] += delta
                b["balance"] -= delta
                if delta:
                    win(a, delta > 0)
                    win(b, delta < 0)
                db.save(a)
                db.save(b)
        self.stop()
        n1, i1 = await self.ctx.me()
        n2, i2 = await self.ctx.who(self.target)
        import asyncio
        d1, d2 = max(1, min(6, da // 2)), max(1, min(6, db_ // 2))
        winner = n1 if delta > 0 else n2
        text = "تعادل" if not delta else f"فاز {winner} {util.full(self.amount)}"
        img = await asyncio.to_thread(render.vs_card, i1, n1, i2, n2, d1, d2, text,
                                      render.LIGHT if not delta else render.GREEN)
        await interaction.response.edit_message(content=f"المجموع: {da} ضد {db_}",
                                                attachments=[discord.File(render.to_bytes(img), "card.png")], view=None)

    @discord.ui.button(label="رفض ❌", style=discord.ButtonStyle.danger)
    async def decline(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content="انرفض التحدي 🏳️", view=None)


@command("تحدي")
async def cmd_duel(ctx):
    t = ctx.target
    if not t or t.id == ctx.uid:
        return await ctx.text("اكتب: تحدي @الشخص المبلغ")
    got = await get_bet(ctx)
    if not got:
        return
    if db.get_user(t.id)["balance"] < got[1]:
        return await ctx.text("رصيده ما يكفي للتحدي")
    view = DuelView(ctx, t, got[1])
    view.message = await ctx.text(f"{t.mention} 🎲 {ctx.author.display_name} يتحداك على {util.full(got[1])}!", view=view)


# ------------------------------------------------------------------ فواكه (اختر ثمرة)
FRUITS = [("apple", "تفاح"), ("lemon", "ليمون"), ("grape", "عنب")]


class FruitView(OwnerView):
    def __init__(self, ctx, amount):
        super().__init__(ctx.uid, timeout=45)
        self.ctx, self.amount = ctx, amount
        self.rotten = random.randrange(3)
        for i, (_, label) in enumerate(FRUITS):
            b = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
            b.callback = self.make(i)
            self.add_item(b)

    def make(self, i):
        async def cb(interaction):
            import asyncio
            async with lock(self.owner_id):
                u = db.get_user(self.owner_id)
                if u["balance"] < self.amount:
                    return await interaction.response.edit_message(content="رصيدك ما يكفي", view=None)
                won = i != self.rotten
                delta = int(self.amount * 0.4) if won else -self.amount
                u["balance"] += delta
                win(u, won)
                db.save(u)
            self.stop()
            kinds = [("rotten" if j == self.rotten else FRUITS[j][0]) for j in range(3)]
            labels = ["فاسدة" if j == self.rotten else FRUITS[j][1] for j in range(3)]
            name, img = await self.ctx.me()
            card = await asyncio.to_thread(render.slots_card, img, name, kinds, labels, signed(delta),
                                           render.GREEN if won else render.RED, "فواكه")
            await interaction.response.edit_message(content=None,
                                                    attachments=[discord.File(render.to_bytes(card), "card.png")], view=None)
        return cb


@command("فواكه")
async def cmd_fruits(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    view = FruitView(ctx, got[1])
    view.message = await ctx.text("🍎🍋🍇 وحدة منهم فاسدة! اختر ثمرة (الربح +40%)", view=view)


# ------------------------------------------------------------------ لون
COLORS = [("🔴 احمر", discord.ButtonStyle.danger), ("🟢 اخضر", discord.ButtonStyle.success),
          ("🔵 ازرق", discord.ButtonStyle.primary), ("⚪ رمادي", discord.ButtonStyle.secondary)]


class ColorView(OwnerView):
    def __init__(self, ctx, amount):
        super().__init__(ctx.uid, timeout=45)
        self.amount = amount
        self.answer = random.randrange(4)
        for i, (label, style) in enumerate(COLORS):
            b = discord.ui.Button(label=label, style=style)
            b.callback = self.make(i)
            self.add_item(b)

    def make(self, i):
        async def cb(interaction):
            async with lock(self.owner_id):
                u = db.get_user(self.owner_id)
                if u["balance"] < self.amount:
                    return await interaction.response.edit_message(content="رصيدك ما يكفي", view=None)
                won = i == self.answer
                delta = int(self.amount * 2.8) if won else -self.amount
                u["balance"] += delta
                win(u, won)
                db.save(u)
            self.stop()
            await interaction.response.edit_message(
                content=f"اللون كان {COLORS[self.answer][0]}\n**{'فزت 🎉' if won else 'خسرت 😢'}** {signed(delta)}", view=None)
        return cb


@command("لون")
async def cmd_color(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    view = ColorView(ctx, got[1])
    view.message = await ctx.text("خمّن اللون! الربح ×3.8 🎨", view=view)


# ------------------------------------------------------------------ برج
TOWER_LEVELS = 6
TOWER_STEP = 1.45


class TowerView(OwnerView):
    def __init__(self, ctx, amount):
        super().__init__(ctx.uid, timeout=90)
        self.amount, self.level = amount, 0
        self.bombs = [random.randrange(3) for _ in range(TOWER_LEVELS)]
        for i in range(3):
            b = discord.ui.Button(label=f"باب {i + 1}", style=discord.ButtonStyle.primary, row=0)
            b.callback = self.door(i)
            self.add_item(b)
        self.cash = discord.ui.Button(label="سحب 💰", style=discord.ButtonStyle.success, row=1, disabled=True)
        self.cash.callback = self.cashout
        self.add_item(self.cash)

    def payout(self):
        return int(self.amount * TOWER_STEP ** self.level)

    async def _finish(self, interaction, delta, msg):
        async with lock(self.owner_id):
            u = db.get_user(self.owner_id)
            u["balance"] += delta
            win(u, delta > 0)
            db.save(u)
        self.stop()
        await interaction.response.edit_message(content=msg, view=None)

    def door(self, i):
        async def cb(interaction):
            if i == self.bombs[self.level]:
                return await self._finish(interaction, -self.amount, f"💥 بوم! الباب {i + 1} فيه قنبلة — خسرت {util.full(self.amount)}")
            self.level += 1
            if self.level >= TOWER_LEVELS:
                return await self._finish(interaction, self.payout() - self.amount,
                                          f"🏆 وصلت القمة! ربحت {util.full(self.payout() - self.amount)}")
            self.cash.disabled = False
            await interaction.response.edit_message(
                content=f"🧱 الطابق {self.level + 1}/{TOWER_LEVELS} — السحب الحين {util.full(self.payout())}", view=self)
        return cb

    async def cashout(self, interaction):
        await self._finish(interaction, self.payout() - self.amount,
                           f"💰 سحبت {util.full(self.payout())} (ربح {util.full(self.payout() - self.amount)})")


@command("برج")
async def cmd_tower(ctx):
    got = await get_bet(ctx)
    if not got:
        return
    view = TowerView(ctx, got[1])
    view.message = await ctx.text(f"🧱 الطابق 1/{TOWER_LEVELS} — اختر باب، واحد فيه قنبلة!", view=view)
