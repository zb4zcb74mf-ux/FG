"""الأوامر العامة: راتب، فلوسي، بخشيش، تحويل، نهب، توب، وقت، بروفايل، اعدادات، منح، اوامر، سوق."""
import random
import time

import discord

import config
import db
import market
import render
import util
from core import OwnerView, command, lock


def net_worth(u: dict) -> int:
    return u["balance"] + market.assets_value(u)


def win(u, won: bool):
    u["wins" if won else "losses"] += 1


# ------------------------------------------------------------------ قائمة الأوامر
@command("اوامر", "الاوامر", "مساعدة", "help")
async def cmd_menu(ctx):
    await ctx.card(render.menu_card)


# ------------------------------------------------------------------ راتب
@command("راتب")
async def cmd_salary(ctx):
    u = ctx.user
    left = db.cd_left(u, "salary", config.SALARY_COOLDOWN)
    if left:
        return await ctx.text(f"⏳ راتبك الجاي بعد {util.dur(left)}")
    amount = random.randint(*config.SALARY_RANGE)
    bonus = 1 + 0.05 * db.perk(u, "salary") + (config.MARRIED_SALARY_BONUS if u["spouse"] else 0)
    amount = int(amount * bonus)
    u["balance"] += amount
    db.cd_set(u, "salary")
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.amount_card, img, name, "راتب", f"+{util.full(amount)}", render.GREEN,
                   "تم استلام الراتب", render.GREEN, "check")


# ------------------------------------------------------------------ فلوسي
@command("فلوسي", "رصيد", "رصيدي")
async def cmd_balance(ctx):
    target = ctx.target or ctx.author
    u = db.get_user(target.id)
    name, img = await ctx.who(target)
    debt = f"عليك دين {util.full(u['debt'])}" if u["debt"] else None
    sign = "-" if u["balance"] < 0 else ""
    await ctx.card(render.balance_card, img, name, f"{sign}{util.full(u['balance'])}", debt)


# ------------------------------------------------------------------ بخشيش
@command("بخشيش")
async def cmd_tip(ctx):
    u = ctx.user
    left = db.cd_left(u, "tip", config.TIP_COOLDOWN)
    if left:
        return await ctx.text(f"⏳ البخشيش الجاي بعد {util.dur(left)}")
    amount = int(random.randint(*config.TIP_RANGE) * (1 + 0.10 * db.perk(u, "tip")))
    u["balance"] += amount
    db.cd_set(u, "tip")
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.amount_card, img, name, "بخشيش", f"+{util.full(amount)}", render.GREEN,
                   "جاك بخشيش", render.GREEN, "check")


# ------------------------------------------------------------------ تحويل
@command("تحويل")
async def cmd_transfer(ctx):
    t = ctx.target
    if not t or t.id == ctx.uid:
        return await ctx.text("اكتب: تحويل @الشخص المبلغ")
    u = ctx.user
    amount = ctx.amount_arg()
    if not amount or amount <= 0:
        return await ctx.text("اكتب المبلغ، مثال: تحويل @الشخص 5k")
    if amount > u["balance"]:
        return await ctx.text("رصيدك ما يكفي 💸")
    tax = int(amount * config.TRANSFER_TAX)
    other = db.get_user(t.id)
    u["balance"] -= amount
    other["balance"] += amount - tax
    db.save(u)
    db.save(other)
    n1, i1 = await ctx.me()
    n2, i2 = await ctx.who(t)
    await ctx.card(render.duel_card, i1, n1, i2, n2, f"-{util.full(amount)}", render.GREEN, "transfer")
    if tax:
        await ctx.text(f"🧾 الضريبة {util.full(tax)} — وصل للمستلم {util.full(amount - tax)}")


# ------------------------------------------------------------------ نهب
@command("نهب")
async def cmd_steal(ctx):
    t = ctx.target
    if not t or t.id == ctx.uid:
        return await ctx.text("اكتب: نهب @الشخص")
    u = ctx.user
    left = db.cd_left(u, "steal", config.STEAL_COOLDOWN)
    if left:
        return await ctx.text(f"⏳ تقدر تنهب بعد {util.dur(left)}")
    v = db.get_user(t.id)
    if db.shield_left(v):
        return await ctx.text(f"🛡️ {t.display_name} عنده حماية — باقي {util.dur(db.shield_left(v))}")
    if v["balance"] < config.STEAL_MIN_VICTIM:
        return await ctx.text("هذا مفلس، ما فيه شي ينهب 😂")
    db.cd_set(u, "steal")
    chance = config.STEAL_BASE_CHANCE + 0.02 * db.perk(u, "steal")
    n1, i1 = await ctx.me()
    n2, i2 = await ctx.who(t)
    if random.random() < chance:
        amount = min(config.STEAL_MAX, int(v["balance"] * random.uniform(*config.STEAL_PERCENT)))
        v["balance"] -= amount
        u["balance"] += amount
        win(u, True)
        db.save(u)
        db.save(v)
        await ctx.card(render.duel_card, i2, n2, i1, n1, f"+{util.full(amount)}", render.GREEN, "steal")
    else:
        fine = min(u["balance"], random.randint(*config.STEAL_FINE))
        u["balance"] -= fine
        v["balance"] += fine
        win(u, False)
        db.save(u)
        db.save(v)
        await ctx.card(render.duel_card, i2, n2, i1, n1, f"-{util.full(fine)}", render.RED, "steal")
        await ctx.text("🚨 انمسكت! دفعت غرامة للضحية.")


# ------------------------------------------------------------------ توب
class TopView(OwnerView):
    def __init__(self, ctx):
        super().__init__(ctx.uid, timeout=90)
        self.ctx = ctx
        sel = discord.ui.Select(placeholder="الترتيب", options=[
            discord.SelectOption(label="الاغنياء", value="rich", emoji="💰"),
            discord.SelectOption(label="الاكثر ديون", value="debt", emoji="📉"),
            discord.SelectOption(label="الاكثر فوزاً", value="wins", emoji="🏆"),
        ])
        sel.callback = self.pick
        self.add_item(sel)

    async def pick(self, interaction: discord.Interaction):
        mode = interaction.data["values"][0]
        await interaction.response.defer()
        img, _ = await build_top(self.ctx, mode)
        import discord as d
        await interaction.message.edit(attachments=[d.File(render.to_bytes(img), "card.png")], view=self)


async def build_top(ctx, mode):
    users = [x for x in db.all_users() if not x["settings"].get("hide_top")]
    if mode == "debt":
        key, title = (lambda x: x["debt"]), "الاكثر ديون"
        users = [x for x in users if x["debt"] > 0]
    elif mode == "wins":
        key, title = (lambda x: x["wins"]), "الاكثر فوزاً"
        users = [x for x in users if x["wins"] > 0]
    else:
        key, title = net_worth, "الاغنياء"
    users.sort(key=key, reverse=True)
    entries = []
    for x in users[:5]:
        name, img = await ctx.who(x["id"])
        val = util.short(key(x)) if mode != "wins" else f"{x['wins']} فوز"
        entries.append((img, name, val))
    if not entries:
        entries = [(render.placeholder("?"), "لا أحد بعد", "-")]
    import asyncio
    return await asyncio.to_thread(render.leaderboard_card, entries, title), title


@command("توب", "الاغنياء")
async def cmd_top(ctx):
    img, _ = await build_top(ctx, "rich")
    import discord as d
    view = TopView(ctx)
    msg = await ctx._send(file=d.File(render.to_bytes(img), "card.png"), view=view)
    view.message = msg


# ------------------------------------------------------------------ وقت
@command("وقت", "الوقت")
async def cmd_time(ctx):
    u = ctx.user
    rows = []
    for label, key, secs in (("الراتب", "salary", config.SALARY_COOLDOWN), ("البخشيش", "tip", config.TIP_COOLDOWN),
                             ("النهب", "steal", config.STEAL_COOLDOWN), ("عجلة الحظ", "luck", config.LUCK_COOLDOWN)):
        left = db.cd_left(u, key, secs)
        rows.append((label, util.dur(left) if left else "جاهز ✅", render.WHITE if left else render.GREEN))
    sh = db.shield_left(u)
    rows.append(("الحماية", util.dur(sh) if sh else "لا يوجد", render.GREEN if sh else render.LIGHT))
    name, img = await ctx.me()
    await ctx.card(render.info_card, img, name, "المؤقتات", rows)


# ------------------------------------------------------------------ بروفايل
@command("بروفايل", "ملف")
async def cmd_profile(ctx):
    target = ctx.target or ctx.author
    u = db.get_user(target.id)
    name, img = await ctx.who(target)
    users = sorted(db.all_users(), key=net_worth, reverse=True)
    rank = next((i + 1 for i, x in enumerate(users) if x["id"] == target.id), "-")
    spouse = "اعزب"
    if u["spouse"]:
        spouse = (await ctx.who(u["spouse"]))[0]
    rows = [("الرصيد", util.full(u["balance"]), render.GREEN),
            ("الثروة الكلية", util.full(net_worth(u))),
            ("الترتيب", f"#{rank}"),
            ("الدين", util.full(u["debt"]), render.RED if u["debt"] else render.WHITE),
            ("الفوز / الخسارة", f"{u['wins']} / {u['losses']}"),
            ("الحالة", spouse)]
    await ctx.card(render.info_card, img, name, "البروفايل", rows)


# ------------------------------------------------------------------ اعدادات
class SettingsView(OwnerView):
    def __init__(self, uid):
        super().__init__(uid, timeout=90)
        self.refresh()

    def refresh(self):
        u = db.get_user(self.owner_id)
        self.toggle.label = "إظهار اسمي في التوب" if u["settings"].get("hide_top") else "إخفاء اسمي من التوب"
        self.toggle.style = discord.ButtonStyle.success if u["settings"].get("hide_top") else discord.ButtonStyle.secondary

    @discord.ui.button(label="...", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button):
        u = db.get_user(self.owner_id)
        u["settings"]["hide_top"] = not u["settings"].get("hide_top", False)
        db.save(u)
        self.refresh()
        await interaction.response.edit_message(view=self)


@command("اعدادات", "إعدادات")
async def cmd_settings(ctx):
    u = ctx.user
    hidden = u["settings"].get("hide_top")
    name, img = await ctx.me()
    view = SettingsView(ctx.uid)
    rows = [("الظهور في التوب", "مخفي" if hidden else "ظاهر")]
    img_card = await __import__("asyncio").to_thread(render.info_card, img, name, "الاعدادات", rows)
    msg = await ctx._send(file=discord.File(render.to_bytes(img_card), "card.png"), view=view)
    view.message = msg


# ------------------------------------------------------------------ منح (للمميزين)
@command("منح")
async def cmd_grant(ctx):
    if not ctx.is_admin():
        return await ctx.text("🔒 الأمر للمميزين فقط")
    t = ctx.target
    amount = ctx.amount_arg(balance=0)
    if not t or not amount:
        return await ctx.text("اكتب: منح @الشخص المبلغ")
    if t.id == ctx.uid:  # القفل ممسوك أصلاً
        v = db.get_user(t.id)
        v["balance"] += amount
        db.save(v)
    else:
        async with lock(t.id):
            v = db.get_user(t.id)
            v["balance"] += amount
            db.save(v)
    name, img = await ctx.who(t)
    await ctx.card(render.amount_card, img, name, "منحة", f"+{util.full(amount)}", render.GREEN,
                   "تم المنح", render.GREEN, "check")


# ------------------------------------------------------------------ سوق
@command("سوق", "اسعار", "معادن")
async def cmd_market(ctx):
    market.maybe_tick()
    left = market.seconds_left()
    _, img = await ctx.me()
    await ctx.card(render.market_card, img, market.snapshot(), f"{left // 60:02d}:{left % 60:02d}")
