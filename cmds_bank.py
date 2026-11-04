"""البنك والزواج والمتجر والبيركات: قرض، سداد، حماية، زواج، زواجي، طلاق، متجر، ممتلكات، شراء، بيع، صندوق، بيركات."""
import asyncio
import random
import time

import discord

import config
import db
import market
import render
import util
from cmds_general import net_worth
from core import OwnerView, command, lock


# ================================================================== البنك
@command("قرض")
async def cmd_loan(ctx):
    u = ctx.user
    if u["debt"]:
        return await ctx.text("عليك دين لازم تسدده اول")
    amount = config.LOAN_AMOUNT
    u["balance"] += amount
    u["debt"] += amount
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.amount_card, img, name, "قرض جديد", f"+{util.short(amount)}", render.GREEN,
                   "عليك دين", render.RED, "debt")


@command("سداد", "سدد")
async def cmd_repay(ctx):
    u = ctx.user
    if not u["debt"]:
        return await ctx.text("ماعليك دين ✅")
    want = ctx.amount_arg(u["debt"]) if ctx.args else u["debt"]
    if not want or want <= 0:
        return await ctx.text("اكتب مبلغ صحيح، أو اكتب `سداد` فقط لتسديد كل الدين")
    pay = min(want, u["debt"])
    if pay > u["balance"]:
        return await ctx.text(f"رصيدك ما يكفي — تحتاج {util.full(pay)}")
    u["balance"] -= pay
    u["debt"] -= pay
    db.save(u)
    name, img = await ctx.me()
    clear = u["debt"] == 0
    await ctx.card(render.amount_card, img, name, "تم السداد" if clear else "سداد جزئي", f"-{util.short(pay)}",
                   render.RED, "ماعليك دين" if clear else f"باقي {util.short(u['debt'])}",
                   render.GREEN if clear else render.ORANGE, "check")


@command("حماية", "حمايه")
async def cmd_shield(ctx):
    u = ctx.user
    name, img = await ctx.me()
    left = db.shield_left(u)
    if left:
        hours = max(1, round(left / 3600))
        return await ctx.card(render.shield_card, img, name, "لديك حماية حاليا", f"المتبقي : {hours} ساعة")
    hours = None
    if ctx.args:
        v = util.parse_amount(ctx.args[0])
        hours = v
    if not hours or not 1 <= hours <= config.SHIELD_MAX_HOURS:
        return await ctx.text(f"يمكنك تحديد عدد الساعات من 1 إلى {config.SHIELD_MAX_HOURS} فقط (مثال: `حماية 1` إلى `حماية {config.SHIELD_MAX_HOURS}`)\n"
                              f"السعر: {util.full(cost_per_hour(u))} للساعة")
    cost = cost_per_hour(u) * hours
    if u["balance"] < cost:
        return await ctx.text(f"رصيدك ما يكفي — تحتاج {util.full(cost)}")
    u["balance"] -= cost
    u["shield_until"] = time.time() + hours * 3600
    db.save(u)
    await ctx.card(render.shield_card, img, name, "لديك حماية حاليا", f"المتبقي : {hours} ساعة")


def cost_per_hour(u):
    return int(config.SHIELD_HOUR_COST * (1 - 0.05 * db.perk(u, "shield")))


# ================================================================== الزواج
class ProposalView(OwnerView):
    def __init__(self, ctx, target, mahr):
        super().__init__(target.id, timeout=90)
        self.ctx, self.target, self.mahr = ctx, target, mahr

    @discord.ui.button(label="موافقة 💍", style=discord.ButtonStyle.success)
    async def yes(self, interaction, button):
        a_id, b_id = self.ctx.uid, self.target.id
        lo, hi = sorted((a_id, b_id))
        async with lock(lo):
            async with lock(hi):
                a, b = db.get_user(a_id), db.get_user(b_id)
                if a["spouse"] or b["spouse"]:
                    return await interaction.response.edit_message(content="أحدكم تزوج قبل ❌", view=None)
                if a["balance"] < self.mahr:
                    return await interaction.response.edit_message(content="العريس ما عنده المهر ❌", view=None)
                a["balance"] -= self.mahr
                b["balance"] += self.mahr
                a["spouse"], b["spouse"] = b_id, a_id
                a["married_at"] = b["married_at"] = time.time()
                db.save(a)
                db.save(b)
        self.stop()
        n1, i1 = await self.ctx.me()
        n2, i2 = await self.ctx.who(self.target)
        img = await asyncio.to_thread(render.duel_card, i1, n1, i2, n2, "مبروك الزواج", (255, 110, 160), "heart")
        await interaction.response.edit_message(content=f"💍 المهر {util.full(self.mahr)}",
                                                attachments=[discord.File(render.to_bytes(img), "card.png")], view=None)

    @discord.ui.button(label="رفض 💔", style=discord.ButtonStyle.danger)
    async def no(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content="انرفض الطلب 💔", view=None)


@command("زواج")
async def cmd_marry(ctx):
    t = ctx.target
    if not t or t.id == ctx.uid:
        return await ctx.text("اكتب: زواج @الشخص [المهر]")
    u, v = ctx.user, db.get_user(t.id)
    if u["spouse"]:
        return await ctx.text("انت متزوج أصلاً 😅")
    if v["spouse"]:
        return await ctx.text("هذا الشخص متزوج")
    mahr = config.MARRY_DEFAULT_MAHR
    if ctx.args:
        parsed = util.parse_amount(ctx.args[0], u["balance"])
        if parsed:
            mahr = parsed
    if u["balance"] < mahr:
        return await ctx.text(f"ما يكفي رصيدك للمهر ({util.full(mahr)})")
    view = ProposalView(ctx, t, mahr)
    view.message = await ctx.text(f"💍 {t.mention} {ctx.author.display_name} يطلب يدك — المهر {util.full(mahr)}", view=view)


@command("زواجي")
async def cmd_my_marriage(ctx):
    u = ctx.user
    name, img = await ctx.me()
    if not u["spouse"]:
        return await ctx.text("انت اعزب 🕊️ — جرب `زواج @شخص`")
    sname, simg = await ctx.who(u["spouse"])
    days = int((time.time() - (u["married_at"] or time.time())) // 86400)
    rows = [("الشريك", sname), ("مدة الزواج", f"{days} يوم"),
            ("بونص الراتب", f"+{int(config.MARRIED_SALARY_BONUS * 100)}%", render.GREEN)]
    await ctx.card(render.info_card, img, name, "زواجي", rows)


class DivorceView(OwnerView):
    def __init__(self, uid):
        super().__init__(uid, timeout=30)

    @discord.ui.button(label="تأكيد الطلاق", style=discord.ButtonStyle.danger)
    async def ok(self, interaction, button):
        async with lock(self.owner_id):
            u = db.get_user(self.owner_id)
            if not u["spouse"]:
                return await interaction.response.edit_message(content="انت اعزب أصلاً", view=None)
            if u["balance"] < config.DIVORCE_FEE:
                return await interaction.response.edit_message(
                    content=f"رصيدك ما يكفي لرسوم الطلاق {util.full(config.DIVORCE_FEE)}", view=None)
            sp = db.get_user(u["spouse"])
            u["balance"] -= config.DIVORCE_FEE
            u["spouse"], u["married_at"] = None, None
            sp["spouse"], sp["married_at"] = None, None
            db.save(u)
            db.save(sp)
        self.stop()
        await interaction.response.edit_message(content="💔 تم الطلاق", view=None)

    @discord.ui.button(label="تراجع", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content="الحمدلله رجعت المياه لمجاريها 🕊️", view=None)


@command("طلاق")
async def cmd_divorce(ctx):
    if not ctx.user["spouse"]:
        return await ctx.text("انت اعزب أصلاً")
    view = DivorceView(ctx.uid)
    view.message = await ctx.text(f"متأكد؟ رسوم الطلاق {util.full(config.DIVORCE_FEE)}", view=view)


# ================================================================== المتجر
def find_asset(word: str):
    """يرجع (اسم, نوع) حيث النوع metal أو item."""
    w = util.norm(word)
    for k in market.METALS:
        if util.norm(k) == w:
            return k, "metal"
    for k in config.STORE_ITEMS:
        if util.norm(k) == w:
            return k, "item"
    return None, None


def asset_price(name, kind):
    return market.price(name) if kind == "metal" else config.STORE_ITEMS[name]["price"]


@command("متجر", "المتجر")
async def cmd_store(ctx):
    market.maybe_tick()
    name, img = await ctx.me()
    rows = [(k, util.full(v["price"])) for k, v in config.STORE_ITEMS.items()]
    await ctx.card(render.info_card, img, name, "المتجر", rows, "اشتري: شراء <الاسم> [الكمية]  •  المعادن في أمر سوق")


@command("ممتلكات", "ممتلكاتي")
async def cmd_assets(ctx):
    market.maybe_tick()
    u = ctx.user
    name, img = await ctx.me()
    rows = []
    for k, q in sorted(u["inv"].items()):
        if q <= 0:
            continue
        kind = "metal" if k in market.METALS else "item"
        if k not in market.METALS and k not in config.STORE_ITEMS:
            continue
        rows.append((f"{k} × {q}", util.full(asset_price(k, kind) * q)))
    if not rows:
        return await ctx.text("ما عندك ممتلكات بعد — جرب `متجر` أو `سوق`")
    rows = rows[:8]
    rows.append(("المجموع", util.full(market.assets_value(u)), render.GREEN))
    await ctx.card(render.info_card, img, name, "ممتلكاتي", rows)


def _qty(ctx, idx, default=1, maximum=None):
    if len(ctx.args) <= idx:
        return default
    word = ctx.args[idx]
    if word in ("كل", "الكل", "كامل", "all") and maximum is not None:
        return maximum
    v = util.parse_amount(word)
    return v


@command("شراء", "اشتري")
async def cmd_buy(ctx):
    market.maybe_tick()
    if not ctx.args:
        return await ctx.text("اكتب: شراء <الاسم> [الكمية] — مثال: `شراء ذهب 2`")
    key, kind = find_asset(ctx.args[0])
    if not key:
        return await ctx.text("ما لقيت هذا الاسم — شوف `متجر` و `سوق`")
    qty = _qty(ctx, 1)
    if not qty or qty <= 0:
        return await ctx.text("الكمية غير صحيحة")
    u = ctx.user
    price = asset_price(key, kind)
    total = price * qty
    if u["balance"] < total:
        return await ctx.text(f"رصيدك ما يكفي — تحتاج {util.full(total)}")
    u["balance"] -= total
    u["inv"][key] = u["inv"].get(key, 0) + qty
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.trade_card, img, name, "عملية شراء",
                   [f"الكمية : {qty}", "العملية : شراء", f"{'المعدن' if kind == 'metal' else 'الغرض'} : {key}"],
                   f"-{util.full(total)}", render.RED)


@command("بيع", "بيع")
async def cmd_sell(ctx):
    market.maybe_tick()
    if not ctx.args:
        return await ctx.text("اكتب: بيع <الاسم> [الكمية|كل]")
    key, kind = find_asset(ctx.args[0])
    u = ctx.user
    if not key or u["inv"].get(key, 0) <= 0:
        return await ctx.text("ما تملك هذا الشي")
    have = u["inv"][key]
    qty = _qty(ctx, 1, default=1, maximum=have)
    if not qty or qty <= 0 or qty > have:
        return await ctx.text(f"الكمية غير صحيحة — عندك {have}")
    price = asset_price(key, kind)
    if kind == "item":
        price = int(price * config.ITEM_SELL_RATIO)
    total = price * qty
    u["inv"][key] = have - qty
    if u["inv"][key] <= 0:
        del u["inv"][key]
    u["balance"] += total
    db.save(u)
    name, img = await ctx.me()
    await ctx.card(render.trade_card, img, name, "عملية بيع",
                   [f"الكمية : {qty}", "العملية : بيع", f"{'المعدن' if kind == 'metal' else 'الغرض'} : {key}"],
                   f"+{util.full(total)}", render.GREEN)


# ================================================================== البيركات
PERKS = {
    "salary": ("زيادة الراتب", "+5% لكل مستوى"),
    "tip": ("بخشيش اكبر", "+10% لكل مستوى"),
    "steal": ("نهب اقوى", "+2% نجاح لكل مستوى"),
    "shield": ("حماية ارخص", "-5% لكل مستوى"),
    "luck": ("حظ", "يحسّن العجلة والألعاب"),
}


@command("صندوق", "الصندوق")
async def cmd_box(ctx):
    u = ctx.user
    if u["balance"] < config.PERK_BOX_COST:
        return await ctx.text(f"الصندوق بـ {util.full(config.PERK_BOX_COST)} — رصيدك ما يكفي")
    u["balance"] -= config.PERK_BOX_COST
    key = random.choice(list(PERKS))
    lvl = db.perk(u, key)
    name, img = await ctx.me()
    if lvl >= config.PERK_MAX_LEVEL:
        refund = config.PERK_BOX_COST // 2
        u["balance"] += refund
        db.save(u)
        return await ctx.text(f"طلع لك **{PERKS[key][0]}** وهو بأعلى مستوى — رجعنا لك {util.full(refund)}")
    u["perks"][key] = lvl + 1
    db.save(u)
    rows = [("البيرك", PERKS[key][0], render.GREEN), ("المستوى", f"{lvl + 1} / {config.PERK_MAX_LEVEL}"),
            ("التأثير", PERKS[key][1])]
    await ctx.card(render.info_card, img, name, "صندوق البيركات", rows)


@command("بيركات", "بيركاتي")
async def cmd_perks(ctx):
    u = ctx.user
    name, img = await ctx.me()
    rows = [(PERKS[k][0], f"{db.perk(u, k)} / {config.PERK_MAX_LEVEL}",
             render.GREEN if db.perk(u, k) else render.LIGHT) for k in PERKS]
    await ctx.card(render.info_card, img, name, "البيركات", rows,
                   f"افتح صندوق بـ {util.full(config.PERK_BOX_COST)}: اكتب صندوق")
