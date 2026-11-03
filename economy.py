"""
نظام اقتصاد فخم لبوت ديسكورد (discord.py 2.x) — أوامر بدون / وبدون بريفكس
بنك | نهب | استثمار (ربع / نص / كامل) | تداول
"""
import asyncio
import random
import sqlite3
import time
import discord
from discord.ext import commands, tasks

CUR = "ريال"
BANK_NAME = "🏦 بنك طاقات"
DB_FILE = "economy.db"
START_BALANCE = 1000
DAILY_RANGE = (500, 1500)
ROB_COOLDOWN = 3600
INVEST_COOLDOWN = 1800
ROB_CHANCE = 0.45
SELL_FEE = 0.01
ALLOWED_CHANNELS = set()

ASSETS = {
    "GOLD": ("🥇 ذهب", 2000, 0.03),
    "SILVER": ("🥈 فضة", 25, 0.04),
    "OIL": ("🛢️ نفط", 80, 0.05),
    "TAQAT": ("⚡ أسهم طاقات", 150, 0.06),
    "BTC": ("₿ بتكوين", 5000, 0.08),
}
ASSET_ALIASES = {
    "ذهب": "GOLD", "فضة": "SILVER", "نفط": "OIL",
    "طاقات": "TAQAT", "اسهم": "TAQAT", "أسهم": "TAQAT",
    "بتكوين": "BTC", "بيتكوين": "BTC",
}
FRACS = {"ربع": 25, "نص": 50, "نصف": 50, "كامل": 100, "الكل": 100}
INVEST_OUTCOMES = [
    (-0.50, 8, "📉 انهار السوق وخسرت نص المبلغ!"),
    (-0.20, 20, "😬 صفقة خاسرة"),
    (0.10, 27, "🙂 ربح بسيط"),
    (0.30, 25, "📈 صفقة ممتازة"),
    (0.60, 15, "🔥 صفقة ذهبية"),
    (1.00, 5, "💎 ضربة العمر! ضاعفت فلوسك"),
]

db = sqlite3.connect(DB_FILE)
db.row_factory = sqlite3.Row
db.executescript(
    """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    wallet INTEGER DEFAULT 0,
    bank INTEGER DEFAULT 0,
    last_daily REAL DEFAULT 0,
    last_rob REAL DEFAULT 0,
    last_invest REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS assets(symbol TEXT PRIMARY KEY, price REAL, prev REAL);
CREATE TABLE IF NOT EXISTS holdings(
    user_id INTEGER, symbol TEXT, qty REAL,
    PRIMARY KEY(user_id, symbol)
);
"""
)

def user(uid):
    db.execute("INSERT OR IGNORE INTO users(user_id, wallet) VALUES(?, ?)", (uid, START_BALANCE))
    db.commit()
    return db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def add(uid, wallet=0, bank=0):
    db.execute("UPDATE users SET wallet=wallet+?, bank=bank+? WHERE user_id=?", (wallet, bank, uid))
    db.commit()

def set_field(uid, field, value):
    db.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, uid))
    db.commit()

def price_of(sym):
    return db.execute("SELECT price FROM assets WHERE symbol=?", (sym,)).fetchone()["price"]

def holding(uid, sym):
    r = db.execute("SELECT qty FROM holdings WHERE user_id=? AND symbol=?", (uid, sym)).fetchone()
    return r["qty"] if r else 0.0

def set_holding(uid, sym, qty):
    if qty <= 1e-9:
        db.execute("DELETE FROM holdings WHERE user_id=? AND symbol=?", (uid, sym))
    else:
        db.execute("INSERT OR REPLACE INTO holdings VALUES(?, ?, ?)", (uid, sym, qty))
    db.commit()

def portfolio_value(uid):
    r = db.execute(
        "SELECT COALESCE(SUM(h.qty * a.price), 0) AS v FROM holdings h "
        "JOIN assets a ON a.symbol=h.symbol WHERE h.user_id=?",
        (uid,),
    ).fetchone()
    return r["v"]

def fmt(n):
    return f"{int(n):,}"

def emb(title, desc="", color=0x7B2FF7):
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text=BANK_NAME)
    return e

def parse_amt(txt, avail):
    if txt is None:
        return None
    txt = txt.strip().replace(",", "")
    if txt in ("الكل", "كامل", "all"):
        return int(avail)
    if txt in ("نص", "نصف"):
        return int(avail // 2)
    if txt == "ربع":
        return int(avail // 4)
    return int(txt) if txt.isdigit() else None

def left(sec):
    m, s = divmod(int(sec), 60)
    return f"{m} دقيقة و {s} ثانية" if m else f"{s} ثانية"

async def send(m, embed=None, view=None):
    return await m.reply(embed=embed, view=view, mention_author=False)

async def err(m, text):
    await m.reply(f"❌ {text}", mention_author=False)

def plain_args(args):
    return [a for a in args if not a.startswith("<@")]

class InvestView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=60)
        self.uid = uid

    async def interaction_check(self, i: discord.Interaction):
        if i.user.id != self.uid:
            await i.response.send_message("هذي مو لوحتك 😅 اكتب: استثمار", ephemeral=True)
            return False
        return True

    async def run(self, i: discord.Interaction, frac: float, label: str):
        u = user(self.uid)
        wait = u["last_invest"] + INVEST_COOLDOWN - time.time()
        if wait > 0:
            return await i.response.send_message(f"⏳ انتظر **{left(wait)}** قبل الاستثمار الجاي", ephemeral=True)
        amount = int(u["wallet"] * frac)
        if amount < 100:
            return await i.response.send_message(f"❌ لازم تستثمر 100 {CUR} على الأقل (من المحفظة)", ephemeral=True)
        set_field(self.uid, "last_invest", time.time())
        add(self.uid, wallet=-amount)
        await i.response.edit_message(
            embed=emb("📊 جاري الاستثمار...", f"تم ضخ **{fmt(amount)}** {CUR} ({label}) في السوق ⏳"),
            view=None,
        )
        await asyncio.sleep(2.5)
        pct, _, text = random.choices(INVEST_OUTCOMES, weights=[o[1] for o in INVEST_OUTCOMES])[0]
        result = int(amount * (1 + pct))
        add(self.uid, wallet=result)
        diff = result - amount
        e = emb("📊 نتيجة الاستثمار", text, 0x2ECC71 if diff >= 0 else 0xE74C3C)
        e.add_field(name="المستثمر", value=f"{fmt(amount)} {CUR}")
        e.add_field(name="النتيجة", value=f"{fmt(result)} {CUR}")
        e.add_field(name="الربح / الخسارة", value=f"{'+' if diff >= 0 else ''}{fmt(diff)} ({int(pct * 100):+d}%)")
        await i.edit_original_response(embed=e)

    @discord.ui.button(label="ربع", emoji="🌱", style=discord.ButtonStyle.secondary)
    async def quarter(self, i: discord.Interaction, b: discord.ui.Button):
        await self.run(i, 0.25, "ربع")

    @discord.ui.button(label="نص", emoji="⚖️", style=discord.ButtonStyle.primary)
    async def half(self, i: discord.Interaction, b: discord.ui.Button):
        await self.run(i, 0.50, "نص")

    @discord.ui.button(label="كامل", emoji="🔥", style=discord.ButtonStyle.danger)
    async def full(self, i: discord.Interaction, b: discord.ui.Button):
        await self.run(i, 1.0, "كامل")

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        for k, (_, base, _) in ASSETS.items():
            db.execute("INSERT OR IGNORE INTO assets VALUES(?, ?, ?)", (k, base, base))
        db.commit()
        self.routes = {
            "رصيد": self.balance, "فلوسي": self.balance,
            "ايداع": self.deposit, "إيداع": self.deposit,
            "سحب": self.withdraw, "تحويل": self.transfer,
            "راتب": self.daily, "نهب": self.rob, "استثمار": self.invest,
            "سوق": self.market, "شراء": self.buy, "بيع": self.sell,
            "محفظتي": self.portfolio,
            "متصدرين": self.top, "الاغنياء": self.top,
            "اوامر": self.help, "الاوامر": self.help, "الأوامر": self.help,
        }
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    @tasks.loop(minutes=5)
    async def tick(self):
        for k, (_, base, vol) in ASSETS.items():
            old = price_of(k)
            new = old * (1 + random.gauss(0, vol)) + (base - old) * 0.02
            new = min(max(new, base * 0.3), base * 3)
            db.execute("UPDATE assets SET prev=?, price=? WHERE symbol=?", (old, new, k))
        db.commit()

    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        if m.author.bot or not m.guild or not m.content:
            return
        if ALLOWED_CHANNELS and m.channel.id not in ALLOWED_CHANNELS:
            return
        parts = m.content.split()
        handler = self.routes.get(parts[0])
        if handler:
            try:
                await handler(m, parts[1:])
            except Exception as ex:
                print("economy error:", ex)
                await err(m, "صار خطأ غير متوقع")

    async def help(self, m, args):
        e = emb("📖 أوامر البنك",
            "**🏦 البنك**\nرصيد [@عضو] · ايداع [مبلغ] · سحب [مبلغ] · تحويل @عضو [مبلغ] · راتب\n\n"
            "**🥷 النهب**\nنهب @عضو\n\n"
            "**📊 الاستثمار**\nاستثمار ← أزرار ربع / نص / كامل\n\n"
            "**📈 التداول**\nسوق · شراء ذهب 500 · بيع ذهب نص · محفظتي\n"
            "الأصول: ذهب، فضة، نفط، طاقات، بتكوين\n\n"
            "**👑** متصدرين\n\n"
            "💡 المبلغ يقبل رقم أو: ربع / نص / كامل")
        await send(m, e)

    async def balance(self, m, args):
        t = m.mentions[0] if m.mentions else m.author
        u = user(t.id)
        inv = portfolio_value(t.id)
        e = emb("🏦 كشف الحساب", f"حساب {t.mention}")
        e.add_field(name="💵 المحفظة", value=f"**{fmt(u['wallet'])}** {CUR}")
        e.add_field(name="🏛️ البنك", value=f"**{fmt(u['bank'])}** {CUR}")
        e.add_field(name="📈 التداول", value=f"**{fmt(inv)}** {CUR}")
        e.add_field(name="💎 الثروة الكلية", value=f"**{fmt(u['wallet'] + u['bank'] + inv)}** {CUR}", inline=False)
        e.set_thumbnail(url=t.display_avatar.url)
        await send(m, e)

    async def deposit(self, m, args):
        u = user(m.author.id)
        rest = plain_args(args)
        a = parse_amt(rest[0] if rest else None, u["wallet"])
        if not a or a <= 0 or a > u["wallet"]:
            return await err(m, "مبلغ غير صحيح. مثال: ايداع 500 أو ايداع نص")
        add(m.author.id, -a, a)
        await send(m, emb("✅ تم الإيداع", f"أودعت **{fmt(a)}** {CUR} في البنك 🔒", 0x2ECC71))

    async def withdraw(self, m, args):
        u = user(m.author.id)
        rest = plain_args(args)
        a = parse_amt(rest[0] if rest else None, u["bank"])
        if not a or a <= 0 or a > u["bank"]:
            return await err(m, "مبلغ غير صحيح. مثال: سحب 500 أو سحب كامل")
        add(m.author.id, a, -a)
        await send(m, emb("✅ تم السحب", f"سحبت **{fmt(a)}** {CUR} للمحفظة 💵", 0x2ECC71))

    async def transfer(self, m, args):
        if not m.mentions:
            return await err(m, "منشن العضو. مثال: تحويل @فلان 500")
        t = m.mentions[0]
        u = user(m.author.id)
        rest = plain_args(args)
        a = parse_amt(rest[0] if rest else None, u["wallet"])
        if t.bot or t.id == m.author.id:
            return await err(m, "ما تقدر تحول لهذا الحساب")
        if not a or a <= 0 or a > u["wallet"]:
            return await err(m, "مبلغ غير صحيح أو رصيدك ما يكفي")
        user(t.id)
        add(m.author.id, -a)
        add(t.id, a)
        await send(m, emb("💸 تحويل ناجح", f"{m.author.mention} ➜ {t.mention}\nالمبلغ: **{fmt(a)}** {CUR}", 0x3498DB))

    async def daily(self, m, args):
        u = user(m.author.id)
        wait = u["last_daily"] + 86400 - time.time()
        if wait > 0:
            return await err(m, f"راتبك الجاي بعد **{left(wait)}**")
        amt = random.randint(*DAILY_RANGE)
        add(m.author.id, amt)
        set_field(m.author.id, "last_daily", time.time())
        await send(m, emb("🎁 الراتب اليومي", f"استلمت **{fmt(amt)}** {CUR}!", 0xF1C40F))

    async def rob(self, m, args):
        if not m.mentions:
            return await err(m, "منشن الضحية. مثال: نهب @فلان")
        t = m.mentions[0]
        me, victim = user(m.author.id), user(t.id)
        if t.bot or t.id == m.author.id:
            return await err(m, "ما تقدر تنهب هذا الحساب")
        wait = me["last_rob"] + ROB_COOLDOWN - time.time()
        if wait > 0:
            return await err(m, f"الشرطة تلاحقك! انتظر **{left(wait)}**")
        if me["wallet"] < 200:
            return await err(m, f"لازم يكون معك 200 {CUR} على الأقل (غرامة لو انمسكت)")
        if victim["wallet"] < 500:
            return await err(m, "الضحية مفلس، ما يستاهل المخاطرة 😂")
        set_field(m.author.id, "last_rob", time.time())
        if random.random() < ROB_CHANCE:
            loot = int(victim["wallet"] * random.uniform(0.10, 0.30))
            add(t.id, -loot)
            add(m.author.id, loot)
            e = emb("🥷 نهب ناجح!", f"{m.author.mention} نهب **{fmt(loot)}** {CUR} من {t.mention} وهرب 💨", 0x2ECC71)
        else:
            fine = max(100, int(me["wallet"] * 0.15))
            add(m.author.id, -fine)
            add(t.id, fine)
            e = emb("🚔 انمسكت!", f"{m.author.mention} حاول ينهب {t.mention} وانمسك!\nالغرامة: **{fmt(fine)}** {CUR} راحت للضحية", 0xE74C3C)
        await send(m, e)

    async def invest(self, m, args):
        u = user(m.author.id)
        e = emb("📊 مركز الاستثمار",
            "اختر كم تبغى تستثمر من **محفظتك**:\n\n"
            "🌱 **ربع** — مخاطرة خفيفة\n⚖️ **نص** — متوازن\n🔥 **كامل** — كله أو لا شي!\n\n"
            "النتيجة تتراوح من **-50%** إلى **+100%**")
        e.add_field(name="💵 محفظتك", value=f"{fmt(u['wallet'])} {CUR}")
        e.add_field(name="⏳ الانتظار بين كل استثمار", value=f"{INVEST_COOLDOWN // 60} دقيقة")
        await send(m, e, InvestView(m.author.id))

    async def market(self, m, args):
        e = emb("📈 سوق التداول", "الأسعار تتحدث كل 5 دقايق")
        for r in db.execute("SELECT * FROM assets").fetchall():
            ch = (r["price"] - r["prev"]) / r["prev"] * 100
            arrow = "🟢 ▲" if ch >= 0 else "🔴 ▼"
            e.add_field(name=ASSETS[r["symbol"]][0], value=f"**{r['price']:,.2f}** {CUR}\n{arrow} {ch:+.2f}%")
        await send(m, e)

    async def buy(self, m, args):
        if len(args) < 2 or args[0] not in ASSET_ALIASES:
            return await err(m, "مثال: شراء ذهب 500 أو شراء بتكوين نص")
        sym = ASSET_ALIASES[args[0]]
        u = user(m.author.id)
        a = parse_amt(args[1], u["wallet"])
        if not a or a <= 0 or a > u["wallet"]:
            return await err(m, "مبلغ غير صحيح")
        p = price_of(sym)
        qty = a / p
        add(m.author.id, -a)
        set_holding(m.author.id, sym, holding(m.author.id, sym) + qty)
        await send(m, emb("🛒 تمت عملية الشراء", f"اشتريت **{qty:,.4f}** من {ASSETS[sym][0]}\nبسعر **{p:,.2f}** — إجمالي **{fmt(a)}** {CUR}", 0x2ECC71))

    async def sell(self, m, args):
        if len(args) < 2 or args[0] not in ASSET_ALIASES or args[1] not in FRACS:
            return await err(m, "مثال: بيع ذهب ربع أو بيع نفط كامل")
        sym = ASSET_ALIASES[args[0]]
        have = holding(m.author.id, sym)
        if have <= 0:
            return await err(m, "ما تملك من هذا الأصل")
        qty = have * FRACS[args[1]] / 100
        net = int(qty * price_of(sym) * (1 - SELL_FEE))
        set_holding(m.author.id, sym, have - qty)
        add(m.author.id, net)
        await send(m, emb("💰 تمت عملية البيع",
            f"بعت {args[1]} من {ASSETS[sym][0]} ({qty:,.4f})\nالصافي بعد عمولة {int(SELL_FEE * 100)}%: **{fmt(net)}** {CUR}",
            0xF1C40F))

    async def portfolio(self, m, args):
        rows = db.execute(
            "SELECT h.symbol, h.qty, a.price FROM holdings h JOIN assets a ON a.symbol=h.symbol WHERE h.user_id=?",
            (m.author.id,),
        ).fetchall()
        if not rows:
            return await err(m, "محفظتك فاضية، ابدأ بـ شراء ذهب 500")
        e = emb("💼 محفظة التداول")
        total = 0
        for r in rows:
            v = r["qty"] * r["price"]
            total += v
            e.add_field(name=ASSETS[r["symbol"]][0], value=f"{r['qty']:,.4f}\n≈ **{fmt(v)}** {CUR}")
        e.add_field(name="الإجمالي", value=f"**{fmt(total)}** {CUR}", inline=False)
        await send(m, e)

    async def top(self, m, args):
        rows = db.execute(
            "SELECT u.user_id, u.wallet + u.bank + COALESCE(SUM(h.qty * a.price), 0) AS t "
            "FROM users u LEFT JOIN holdings h ON h.user_id=u.user_id "
            "LEFT JOIN assets a ON a.symbol=h.symbol GROUP BY u.user_id ORDER BY t DESC LIMIT 10"
        ).fetchall()
        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        lines = [f"{medals[n]} <@{r['user_id']}> — **{fmt(r['t'])}** {CUR}" for n, r in enumerate(rows)]
        await send(m, emb("👑 قائمة الأثرياء", "\n".join(lines) or "لا أحد بعد"))

async def setup(bot):
    await bot.add_cog(Economy(bot))
