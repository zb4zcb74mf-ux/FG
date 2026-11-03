import io
import os
import re
import json
import time
import random
import asyncio
import platform
import datetime
import traceback
from typing import Literal, Optional

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
BOT_NAME = "Taqat"

COLOR = 0x2B8CFF
DATA_FILE = "data.json"
IMG_DIR = "images"

# ألوان موحّدة لرسائل الأوامر
C_OK = 0x3DDC84
C_ERR = 0xFF5555
C_WARN = 0xFFAA00
C_INFO = COLOR

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
START_TIME = datetime.datetime.now(datetime.timezone.utc)

STYLES = {
    "gray": discord.ButtonStyle.secondary,
    "blue": discord.ButtonStyle.primary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}

# أزرار لوحة التحكم داخل التذكرة (الافتراضي)
DEFAULT_BTN = {
    "claim": {"label": "استلام", "emoji": "🙋", "style": "gray"},
    "close": {"label": "إغلاق", "emoji": "❌", "style": "gray"},
    "more":  {"label": "إجراءات أخرى", "emoji": "⚙️", "style": "gray"},
}

# الرسالة الافتراضية داخل التذكرة (قابلة للتخصيص بالكامل)
DEFAULT_INSIDE = (
    "مرحبا بك في الدعم الفني ، يرجى عدم تجاهل التذكرة\n\n"
    "👤 **صاحب التذكرة**\n{user}\n\n"
    "📅 **التاريخ**\n{date}\n\n"
    "📝 **سبب التذكرة**\n{reason}"
)

PRIORITIES = {
    "low": ("🟢", "منخفضة"),
    "normal": ("🟡", "عادية"),
    "high": ("🟠", "عالية"),
    "urgent": ("🔴", "عاجلة"),
}

URL_RE = re.compile(r"(https?://|discord\.gg/|discord\.com/invite/|www\.)\S+", re.I)

# ---------------------------------------------------------------- التخزين
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)

DATA = load_data()

WELCOME_DESC = (
    "**Username :** {username}\n"
    "**Invited By :** {inviter}\n"
    "**You're Member :** #{number}"
)

def conf(guild_id: int) -> dict:
    g = DATA.setdefault(str(guild_id), {})
    g.setdefault("autorole", None)
    g.setdefault("warns", {})
    g.setdefault("tickets", {})
    g.setdefault("points", {})       # نقاط الدعم: {staff_id: {points, closed, rating_sum, rating_count}}
    ar = g.setdefault("autoreply", {})
    ar.setdefault("enabled", True)
    ar.setdefault("list", {})        # {مفتاح_مطبّع: {trigger, reply, mode}}

    w = g.setdefault("welcome", {})
    w.setdefault("channel", None)
    w.setdefault("content", "{user}")
    w.setdefault("author", "{name}")
    w.setdefault("desc", "Welcome To {server}")
    w.setdefault("footer", "{count}")
    w.setdefault("color", "E8352A")
    w.setdefault("thumb", True)
    w.setdefault("image", None)
    w.setdefault("title", "Welcome")
    w.setdefault("banner", None)         # الشريط السفلي (صورة تحت البطاقة)
    w.setdefault("style", "modern")      # modern = التصميم الجديد | classic = الإيمبد القديم
    if w.get("_v") != 2:                 # ترقية الإعدادات الافتراضية القديمة فقط (المخصص ما يتغير)
        if w["desc"] == "Welcome To {server}":
            w["desc"] = WELCOME_DESC
        if w["footer"] == "{count}":
            w["footer"] = "{date}"
        w["_v"] = 2

    lv = g.setdefault("leave", {})
    lv.setdefault("channel", None)
    lv.setdefault("msg", "👋 {name} غادر السيرفر")

    t = g.setdefault("ticket", {})
    t.setdefault("log_channel", None)
    t.setdefault("counter", 0)
    t.setdefault("type_counter", 0)
    t.setdefault("types", {})
    t.setdefault("max", 1)            # أقصى عدد تذاكر مفتوحة للعضو الواحد
    t.setdefault("blacklist", [])     # ممنوعين من فتح التذاكر
    t.setdefault("autoclose", 0)      # إغلاق تلقائي بعد X ساعات بدون نشاط (0 = معطل)
    t.setdefault("point_value", 1)    # نقاط المستلم عند إغلاق كل تذكرة

    p = g.setdefault("panel", {})
    p.setdefault("channel_id", None)
    p.setdefault("message_id", None)
    p.setdefault("title", "🎫 نظام التذاكر")
    p.setdefault("desc", (
        "• يرجى الالتزام الكامل بالقوانين داخل التذكرة.\n"
        "• جميع الرسائل محفوظة دائمًا لضمان النظام.\n"
        "• ممنوع تمامًا فتح تذكرة بلا سبب واضح.\n"
        "• في حال عدم الرد لمدة 6 ساعات يتم إغلاق التذكرة.\n"
        "• يرجى كتابة موضوعك مباشرة عند فتح التذكرة."))
    p.setdefault("footer", "سيتم فتح قناة خاصة للتواصل مع فريق الدعم")
    p.setdefault("color", "2B2D31")
    p.setdefault("image", None)
    p.setdefault("ticketmsg", "اكتب مشكلتك أو طلبك وراح يرد عليك الفريق قريباً.")

    # لوحة التحكم داخل التذكرة
    ins = g.setdefault("inside", {})
    ins.setdefault("content", "{user} {support}")
    ins.setdefault("author", "Staff")
    ins.setdefault("author_icon", None)
    ins.setdefault("desc", DEFAULT_INSIDE)
    ins.setdefault("footer", "يمكنك إغلاق التذكرة أو استلامها أو استخدام الإجراءات الأخرى")
    ins.setdefault("color", "2B2D31")
    ins.setdefault("thumb", False)
    ins.setdefault("image", None)
    ins.setdefault("ask_reason", True)
    ins.setdefault("btn", {k: dict(v) for k, v in DEFAULT_BTN.items()})

    r = g.setdefault("rules", {})
    r.setdefault("channel", None)
    r.setdefault("action", "ban")
    r.setdefault("exempt", [])

    a = g.setdefault("automod", {})
    a.setdefault("antilink", False)
    a.setdefault("badwords", [])

    g.setdefault("modlog", {}).setdefault("channel", None)

    # --- ميزات جديدة
    sc = g.setdefault("shortcuts", {})
    sc.setdefault("enabled", True)                 # الاختصارات العربية بدون بادئة

    ws = g.setdefault("warnsys", {})
    ws.setdefault("threshold", 0)                  # عقوبة تلقائية كل X تحذيرات (0 = معطل)
    ws.setdefault("action", "mute")
    ws.setdefault("minutes", 60)

    cs = g.setdefault("cases", {})
    cs.setdefault("counter", 0)
    cs.setdefault("list", [])

    # --- الأذكار / تيك توك / التحدث باسم البوت
    az = g.setdefault("azkar", {})
    az.setdefault("channel", None)
    az.setdefault("hours", 0)
    az.setdefault("last_dua", 0)
    az.setdefault("morning", {"on": True, "time": "05:30"})
    az.setdefault("evening", {"on": True, "time": "17:30"})
    az.setdefault("last", {})
    az.setdefault("custom", [])
    tk = g.setdefault("tiktok", {})
    tk.setdefault("user", None)
    tk.setdefault("channel", None)
    tk.setdefault("role", None)
    tk.setdefault("seen", [])
    rl = g.setdefault("relay", {})
    rl.setdefault("source", None)
    rl.setdefault("target", None)
    tvc = g.setdefault("tempvoice", {})
    tvc.setdefault("hub", None)
    tvc.setdefault("category", None)
    tvc.setdefault("name", "🔊 {name}")
    tvc.setdefault("rooms", {})
    tvc.setdefault("emoji", {})        # إيموجي مخصصة للأزرار {action: emoji}
    tvc.setdefault("image", None)      # الصورة اللي بنص اللوحة
    tvc.setdefault("title", "لوحة التحكم بالرومات المؤقتة")
    tvc.setdefault("desc", "تقدر تستخدم هذه اللوحة لإدارة رومك الصوتي المؤقت.\nادخل روم **➕ أنشئ رومك** وبيتسوّى لك روم خاص فيك.")
    tvc.setdefault("footer", "تقدر تستخدم هذه اللوحة بالضغط على الأزرار أدناه")

    # --- نظام التقديم
    ap = g.setdefault("apply", {})
    ap.setdefault("types", {})
    ap.setdefault("next", 1)
    ap.setdefault("subs", {})
    ap.setdefault("nsub", 0)
    # --- نظام الافتارات
    avt = g.setdefault("avt", {})
    avt.setdefault("servers", {"Respect": None, "MT": None})
    avt.setdefault("channel", None)
    avt.setdefault("title", "افتارات الشخصيات")
    avt.setdefault("desc", "اختر السيرفر من الأزرار تحت، وارفع افتار شخصيتك (والبنر اختياري) وبينزل في روم الافتارات.")
    avt.setdefault("top", None)
    avt.setdefault("bottom", None)
    avt.setdefault("color", "C9A66B")
    avt.setdefault("status", "dnd")
    # --- نظام الإجازات + النظام التعريفي
    ln = g.setdefault("line", {})
    ln.setdefault("image", None)
    ln.setdefault("text", "━━━━━━━━━━━━━━━━━━━━")
    vc = g.setdefault("vac", {})
    for k, val in vac_defaults().items():
        vc.setdefault(k, val)
    inf = g.setdefault("info", {})
    for k, val in info_defaults().items():
        inf.setdefault(k, val)
    return g

# ---------------------------------------------------------------- أدوات مساعدة
def embed(title=None, desc=None, color=COLOR):
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text=BOT_NAME)
    return e

def parse_color(s) -> int:
    try:
        return int(str(s).lstrip("#"), 16)
    except ValueError:
        return COLOR

def valid_color(s: str) -> bool:
    return bool(re.fullmatch(r"#?[0-9a-fA-F]{6}", s.strip()))

def nl(text: str) -> str:
    """يحول \\n المكتوبة إلى سطر جديد (للأوامر السلاش)."""
    return text.replace("\\n", "\n")

def fmt(text: str, member: discord.Member, extra: dict | None = None) -> str:
    out = ((text or "")
           .replace("{user}", member.mention)
           .replace("{name}", member.name)
           .replace("{server}", member.guild.name)
           .replace("{count}", str(member.guild.member_count)))
    for k, v in (extra or {}).items():
        out = out.replace(k, v)
    return out

async def store_image(guild_id: int, kind: str, attachment, url):
    """يحفظ الصورة: مرفق (ينحفظ محلياً) أو رابط."""
    if attachment is not None:
        if not (attachment.content_type or "").startswith("image/"):
            raise ValueError("المرفق لازم يكون صورة.")
        os.makedirs(IMG_DIR, exist_ok=True)
        ext = os.path.splitext(attachment.filename)[1] or ".png"
        path = f"{IMG_DIR}/{guild_id}_{kind}{ext}"
        await attachment.save(path)
        return {"path": path}
    if url:
        if not url.startswith("http"):
            raise ValueError("الرابط لازم يبدأ بـ http.")
        return {"url": url}
    raise ValueError("أرفق صورة أو حط رابط.")

def apply_image(e: discord.Embed, img, name: str):
    """يضيف الصورة السفلية للإيمبد، ويرجع File إذا كانت محلية."""
    if not img:
        return None
    if img.get("path") and os.path.exists(img["path"]):
        fname = f"{name}{os.path.splitext(img['path'])[1]}"
        e.set_image(url=f"attachment://{fname}")
        return discord.File(img["path"], filename=fname)
    if img.get("url"):
        e.set_image(url=img["url"])
    return None

def can_act(ctx, member: discord.Member) -> str | None:
    if member == ctx.author:
        return "ما تقدر تنفذ هذا على نفسك."
    if member == ctx.guild.owner:
        return "ما تقدر على مالك السيرفر."
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return "رتبة العضو أعلى منك أو تساويك."
    if member.top_role >= ctx.guild.me.top_role:
        return "رتبة العضو أعلى من رتبة البوت."
    return None

async def modlog(guild: discord.Guild, e: discord.Embed):
    cid = conf(guild.id)["modlog"]["channel"]
    ch = guild.get_channel(cid) if cid else None
    if ch:
        try:
            await ch.send(embed=e)
        except discord.HTTPException:
            pass

# ---------------------------------------------------------------- التصميم الموحّد للأوامر
def fancy(title=None, desc=None, color=COLOR, footer=None) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color,
                      timestamp=discord.utils.utcnow())
    e.set_footer(text=footer or BOT_NAME)
    return e

def ok_e(title, desc=None):
    return fancy(f"✅ {title}", desc, C_OK)

def err_e(desc, title="تعذّر تنفيذ الأمر"):
    return fancy(f"❌ {title}", desc, C_ERR)

def warn_e(title, desc=None):
    return fancy(f"⚠️ {title}", desc, C_WARN)

def info_e(title, desc=None):
    return fancy(title, desc, C_INFO)

async def send_err(ctx, desc, title="تعذّر تنفيذ الأمر"):
    await ctx.send(embed=err_e(desc, title), ephemeral=True)

def add_case(guild_id: int, action: str, target_id: int, mod_id: int, reason: str) -> int:
    cs = conf(guild_id)["cases"]
    cs["counter"] += 1
    cs["list"].append({"id": cs["counter"], "action": action, "target": target_id, "mod": mod_id,
                       "reason": reason,
                       "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    del cs["list"][:-1000]
    save_data()
    return cs["counter"]

def mod_embed(emoji, title, target, mod, reason, color, case=None, extra=None) -> discord.Embed:
    e = fancy(f"{emoji} {title}", color=color,
              footer=f"{BOT_NAME} • حالة #{case}" if case else None)
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="👤 العضو", value=f"{target.mention}\n`{target.id}`")
    e.add_field(name="🛡️ المسؤول", value=f"{mod.mention}\n`{mod.id}`")
    for n, v in (extra or []):
        e.add_field(name=n, value=v)
    e.add_field(name="📝 السبب", value=(reason or "بدون سبب")[:1000], inline=False)
    return e

async def finish_mod(ctx, emoji, title, target, reason, color, extra=None) -> int:
    """يسجل الحالة، يرسل النتيجة للشات، وينسخها للوق السيرفر."""
    case = add_case(ctx.guild.id, title, target.id, ctx.author.id, reason)
    e = mod_embed(emoji, title, target, ctx.author, reason, color, case, extra)
    await ctx.send(embed=e)
    cid = conf(ctx.guild.id)["modlog"]["channel"]
    if cid and cid != ctx.channel.id:
        await modlog(ctx.guild, e)
    return case

async def notify(target, guild: discord.Guild, emoji, title, reason, color, extra=None):
    """رسالة خاصة للعضو يعرف فيها وش صار."""
    e = fancy(f"{emoji} {title}", color=color)
    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    e.add_field(name="🏠 السيرفر", value=guild.name)
    for n, v in (extra or []):
        e.add_field(name=n, value=v)
    e.add_field(name="📝 السبب", value=(reason or "بدون سبب")[:1000], inline=False)
    try:
        await target.send(embed=e)
    except (discord.Forbidden, discord.HTTPException):
        pass

DUR_RE = re.compile(r"^(\d+)\s*(m|h|d|د|س|ي)?$", re.I)
DUR_UNITS = {"m": 1, "h": 60, "d": 1440, "د": 1, "س": 60, "ي": 1440}

def parse_duration(s: str) -> int | None:
    """30 / 30m / 2h / 1d / 30د / 2س / 1ي  ->  دقائق"""
    m = DUR_RE.match((s or "").strip())
    if not m:
        return None
    return int(m[1]) * DUR_UNITS[(m[2] or "m").lower()]

def human_minutes(mins: int) -> str:
    d, r = divmod(mins, 1440)
    h, m = divmod(r, 60)
    parts = []
    if d:
        parts.append(f"{d} يوم")
    if h:
        parts.append(f"{h} ساعة")
    if m:
        parts.append(f"{m} دقيقة")
    return " و ".join(parts) or "0 دقيقة"

class ConfirmView(discord.ui.View):
    """تأكيد للأوامر الخطيرة."""
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id, self.value = author_id, None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ هذا الزر مو لك.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="تأكيد", emoji="✅", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="إلغاء", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()

# ---------------------------------------------------------------- الأحداث
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | {BOT_NAME}"))
    print(f"✅ {bot.user} شغّال على {len(bot.guilds)} سيرفر")

@bot.event
async def setup_hook():
    bot.add_dynamic_items(TicketButton)
    bot.add_view(TicketControls())
    bot.add_view(TVPanel())
    if not autoclose_loop.is_running():
        autoclose_loop.start()
    if not scheduled_close_loop.is_running():
        scheduled_close_loop.start()
    if not azkar_loop.is_running():
        azkar_loop.start()
    if not tiktok_loop.is_running():
        tiktok_loop.start()
    if not vac_loop.is_running():
        vac_loop.start()
    await bot.tree.sync()

def welcome_vars(member: discord.Member, inviter_id, classic: bool = False) -> dict:
    """متغيرات الترحيب الإضافية: {username} {inviter} {inviter_name} {number} {date}"""
    now = discord.utils.utcnow()
    inv = member.guild.get_member(inviter_id) if inviter_id else None
    return {
        "{username}": member.name,
        "{inviter}": f"<@{inviter_id}>" if inviter_id else "غير معروف",
        "{inviter_name}": inv.name if inv else "غير معروف",
        "{number}": str(member.guild.member_count),
        "{date}": now.strftime("%A, %B %d, %Y at %I:%M %p") if classic
                  else f"<t:{int(now.timestamp())}:F>",
    }

def build_welcome(member: discord.Member, inviter_id=None):
    """الإيمبد الكلاسيكي (التصميم القديم) — يُستخدم عند welcomestyle classic."""
    w = conf(member.guild.id)["welcome"]
    v = welcome_vars(member, inviter_id, classic=True)
    e = discord.Embed(description=fmt(w["desc"], member, v), color=parse_color(w["color"]))
    e.set_author(name=fmt(w["author"], member, v), icon_url=member.display_avatar.url)
    if w["thumb"]:
        e.set_thumbnail(url=member.display_avatar.url)
    if w["footer"]:
        e.set_footer(text=fmt(w["footer"], member, v))
    f = apply_image(e, w["image"], "welcome")
    return fmt(w["content"], member, v) or None, e, f

def _media(img, name: str):
    """(رابط للعرض, ملف محلي أو None) لصورة محفوظة."""
    if not img:
        return None, None
    if img.get("path") and os.path.exists(img["path"]):
        fn = f"{name}{os.path.splitext(img['path'])[1]}"
        return f"attachment://{fn}", discord.File(img["path"], filename=fn)
    if img.get("url"):
        return img["url"], None
    return None, None

def welcome_modern(member: discord.Member, inviter_id=None) -> dict:
    """بطاقة الترحيب الجديدة: صورة فوق + نص + صورة العضو على الجنب + سطر تاريخ + شريط سفلي."""
    ui = discord.ui
    w = conf(member.guild.id)["welcome"]
    v = welcome_vars(member, inviter_id)
    ft = lambda s: fmt(s, member, v)
    top, f1 = _media(w["image"], "welcome_top")
    banner, f2 = _media(w.get("banner"), "welcome_banner")

    parts = []
    if w.get("title"):
        parts.append(f"# {ft(w['title'])}")
    if w["desc"]:
        parts.append(ft(w["desc"]))
    text = "\n".join(parts) or "​"

    items = []
    if top:
        items += [ui.MediaGallery(discord.MediaGalleryItem(top)), ui.Separator()]
    if w["thumb"]:
        items.append(ui.Section(ui.TextDisplay(text), accessory=ui.Thumbnail(member.display_avatar.url)))
    else:
        items.append(ui.TextDisplay(text))
    if w["footer"]:
        items += [ui.Separator(), ui.TextDisplay(ft(w["footer"]))]

    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(*items, accent_colour=discord.Colour(parse_color(w["color"]))))
    if banner:
        view.add_item(ui.MediaGallery(discord.MediaGalleryItem(banner)))
    return {"view": view, "files": [f for f in (f1, f2) if f],
            "allowed_mentions": discord.AllowedMentions.none()}

def welcome_payload(member: discord.Member, inviter_id=None) -> dict:
    w = conf(member.guild.id)["welcome"]
    if w.get("style", "modern") == "modern" and hasattr(discord.ui, "LayoutView"):
        try:
            return welcome_modern(member, inviter_id)
        except Exception:
            traceback.print_exc()
    content, e, f = build_welcome(member, inviter_id)
    return {"content": content, "embed": e, "file": f}

async def send_welcome(dest, member: discord.Member, inviter_id=None):
    try:
        return await dest.send(**welcome_payload(member, inviter_id))
    except discord.Forbidden:
        return None
    except discord.HTTPException:
        content, e, f = build_welcome(member, inviter_id)
        try:
            return await dest.send(content=content, embed=e, file=f)
        except discord.HTTPException:
            return None

# ---- تتبع الدعوات (لمعرفة من دعا العضو: Invited By)
INVITES: dict[int, dict[str, tuple]] = {}   # guild -> code -> (uses, inviter_id, max_uses)

async def cache_invites(guild: discord.Guild):
    try:
        INVITES[guild.id] = {i.code: (i.uses or 0, i.inviter.id if i.inviter else None, i.max_uses or 0)
                             for i in await guild.invites()}
    except discord.HTTPException:
        pass

async def detect_inviter(guild: discord.Guild):
    old = INVITES.get(guild.id)
    try:
        invs = await guild.invites()
    except discord.HTTPException:
        return None
    new = {i.code: (i.uses or 0, i.inviter.id if i.inviter else None, i.max_uses or 0) for i in invs}
    INVITES[guild.id] = new
    if old is None:
        return None
    for code, (uses, inv, _) in new.items():
        if uses > old.get(code, (0,))[0]:
            return inv
    # دعوة محدودة الاستخدام انحذفت بعد آخر استخدام
    gone = [(c, t) for c, t in old.items() if c not in new and t[2] and t[0] + 1 == t[2]]
    return gone[0][1][1] if len(gone) == 1 else None

@bot.listen("on_ready")
async def _invites_ready():
    for g in bot.guilds:
        await cache_invites(g)

@bot.listen("on_guild_join")
async def _invites_guild_join(guild: discord.Guild):
    await cache_invites(guild)

@bot.listen("on_invite_create")
async def _invites_create(invite: discord.Invite):
    if invite.guild:
        INVITES.setdefault(invite.guild.id, {})[invite.code] = (
            invite.uses or 0, invite.inviter.id if invite.inviter else None, invite.max_uses or 0)

@bot.event
async def on_member_join(member: discord.Member):
    c = conf(member.guild.id)
    if c["autorole"]:
        role = member.guild.get_role(c["autorole"])
        if role:
            try:
                await member.add_roles(role, reason="Auto role")
            except discord.Forbidden:
                pass
    inviter_id = await detect_inviter(member.guild)
    cid = c["welcome"]["channel"]
    ch = member.guild.get_channel(cid) if cid else None
    if ch:
        await send_welcome(ch, member, inviter_id)

@bot.event
async def on_member_remove(member: discord.Member):
    lv = conf(member.guild.id)["leave"]
    ch = member.guild.get_channel(lv["channel"]) if lv["channel"] else None
    if ch:
        text = fmt(lv["msg"], member).replace(member.mention, str(member))
        await ch.send(embed=embed(None, text, 0xFF5555))

PERM_AR = {
    "administrator": "مدير (Administrator)",
    "kick_members": "طرد الأعضاء",
    "ban_members": "حظر الأعضاء",
    "moderate_members": "إدارة الأعضاء (Timeout)",
    "manage_messages": "إدارة الرسائل",
    "manage_channels": "إدارة الرومات",
    "manage_guild": "إدارة السيرفر",
    "manage_roles": "إدارة الرتب",
    "manage_nicknames": "إدارة الألقاب",
}

@bot.event
async def on_command_error(ctx, error):
    error = getattr(error, "original", error)
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        perms = "، ".join(f"`{PERM_AR.get(p, p)}`" for p in error.missing_permissions)
        return await send_err(ctx, f"تحتاج الصلاحية: {perms}", "ما عندك صلاحية")
    if isinstance(error, commands.BotMissingPermissions):
        perms = "، ".join(f"`{PERM_AR.get(p, p)}`" for p in error.missing_permissions)
        return await send_err(ctx, f"البوت يحتاج الصلاحية: {perms}", "البوت ما عنده صلاحية")
    if isinstance(error, commands.MissingRequiredArgument):
        usage = f"{PREFIX}{ctx.command.qualified_name} {ctx.command.signature}".strip()
        return await send_err(ctx, f"ناقصك: `{error.param.name}`\n**الاستخدام:** `{usage}`",
                              "بيانات ناقصة")
    if isinstance(error, commands.MemberNotFound):
        return await send_err(ctx, "ما لقيت هذا العضو. استخدم المنشن أو الآيدي.", "عضو غير موجود")
    if isinstance(error, (commands.UserNotFound,)):
        return await send_err(ctx, "ما لقيت هذا المستخدم.", "مستخدم غير موجود")
    if isinstance(error, (commands.BadArgument, commands.BadLiteralArgument,
                          commands.BadUnionArgument)):
        usage = f"{PREFIX}{ctx.command.qualified_name} {ctx.command.signature}".strip() if ctx.command else ""
        return await send_err(ctx, f"مدخلات غير صحيحة.\n**الاستخدام:** `{usage}`", "مدخلات خاطئة")
    if isinstance(error, commands.NoPrivateMessage):
        return await send_err(ctx, "هذا الأمر يشتغل داخل السيرفر فقط.")
    if isinstance(error, commands.CommandOnCooldown):
        return await send_err(ctx, f"انتظر **{error.retry_after:.0f}** ثانية.", "على مهلك")
    if isinstance(error, commands.CheckFailure):
        return await send_err(ctx, "ما تقدر تستخدم هذا الأمر.", "غير مسموح")
    if isinstance(error, discord.Forbidden):
        return await send_err(ctx, "البوت ما يقدر ينفذ هذا (رتبته أو صلاحياته ما تكفي).",
                              "صلاحيات البوت")
    traceback.print_exception(type(error), error, error.__traceback__)
    await send_err(ctx, "صار خطأ غير متوقع، حاول مرة ثانية.", "خطأ غير متوقع")

# ---------------------------------------------------------------- الاختصارات العربية (بدون بادئة)
# الكلمة: (الأمر, الصلاحية المطلوبة, النوع)   النوع: chan = روم / target = عضو / num = رقم
SHORTCUTS = {
    "قفل": ("lock", "manage_channels", "chan"),
    "فتح": ("unlock", "manage_channels", "chan"),
    "اخفاء": ("hide", "manage_channels", "chan"),
    "اظهار": ("unhide", "manage_channels", "chan"),
    "اسكت": ("mute", "moderate_members", "target"),
    "كتم": ("mute", "moderate_members", "target"),
    "تكلم": ("unmute", "moderate_members", "target"),
    "فك كتم": ("unmute", "moderate_members", "target"),
    "باند": ("ban", "ban_members", "target"),
    "حظر": ("ban", "ban_members", "target"),
    "فك باند": ("unban", "ban_members", "target"),
    "فك حظر": ("unban", "ban_members", "target"),
    "تحذير": ("warn", "manage_messages", "target"),
    "انذار": ("warn", "manage_messages", "target"),
    "تحذيرات": ("warnings", "manage_messages", "target"),
    "طرد": ("kick", "kick_members", "target"),
    "مسح": ("clear", "manage_messages", "num"),
    "سلو": ("slowmode", "manage_channels", "num"),
}

SHORTCUT_DOC = [
    ("🔒 قفل / فتح", "قفل أو فتح الشات الحالي (أو `قفل #روم`)"),
    ("🙈 اخفاء / اظهار", "إخفاء أو إظهار الشات الحالي"),
    ("🔇 اسكت / كتم", "`اسكت @عضو 30 السبب` — المدة اختيارية (30 / 2h / 1d / 30د / 2س / 1ي)"),
    ("🔊 تكلم / فك كتم", "`تكلم @عضو`"),
    ("🔨 باند / حظر", "`باند @عضو السبب`"),
    ("✅ فك باند / فك حظر", "`فك باند 123456789` بآيدي المحظور"),
    ("⚠️ تحذير / انذار", "`تحذير @عضو السبب`"),
    ("📋 تحذيرات", "`تحذيرات @عضو`"),
    ("👢 طرد", "`طرد @عضو السبب`"),
    ("🧹 مسح", "`مسح 20` أو `مسح 20 @عضو`"),
    ("🐢 سلو", "`سلو 5` (0 للإلغاء)"),
]

def _norm(s: str) -> str:
    # استبدال حرف بحرف عشان تبقى المواضع نفسها
    return s.translate(str.maketrans("أإآة", "اااه"))

SHORTCUT_PATTERNS = [
    (kw, re.compile(r"^" + r"\s+".join(re.escape(p) for p in kw.split()) + r"(?:\s+(.*))?$", re.S))
    for kw in sorted(SHORTCUTS, key=len, reverse=True)
]

def _resolve_target(message: discord.Message, rest: str):
    m = re.match(r"^<@!?(\d{15,22})>\s*(.*)$", rest, re.S)
    if m:
        return int(m[1]), m[2].strip()
    m = re.match(r"^(\d{15,22})\s*(.*)$", rest, re.S)
    if m:
        return int(m[1]), m[2].strip()
    ref = message.reference
    if ref and isinstance(ref.resolved, discord.Message):
        return ref.resolved.author.id, rest.strip()
    return None, rest.strip()

async def run_shortcut(message: discord.Message) -> bool:
    """يرجع True إذا الرسالة كانت اختصار وانتعاملت."""
    if (message.author.bot or not message.guild or not message.content
            or len(message.content) > 300 or not isinstance(message.author, discord.Member)):
        return False
    if not conf(message.guild.id)["shortcuts"]["enabled"]:
        return False

    text = message.content.strip()
    norm = _norm(text)
    hit = None
    for kw, pat in SHORTCUT_PATTERNS:
        m = pat.match(norm)
        if m:
            hit = (kw, text[m.start(1):].strip() if m.group(1) else "")
            break
    if not hit:
        return False
    kw, rest = hit
    cmd, perm, kind = SHORTCUTS[kw]

    # بدون صلاحية → نتجاهل بصمت عشان ما نتعارض مع الكلام العادي
    if not getattr(message.author.guild_permissions, perm, False):
        return False

    if kind == "chan":
        if rest and not rest.startswith("<#"):
            return False
        line = f"{cmd} {rest}".strip()
    elif kind == "target":
        tid, reason = _resolve_target(message, rest)
        if tid is None:
            if rest:           # جملة عادية فيها الكلمة، مو أمر
                return False
            await message.channel.send(embed=err_e(
                f"حدد العضو: `{kw} @العضو [السبب]`\nأو رد على رسالته بكلمة `{kw}`.",
                "ما حددت العضو"), delete_after=8)
            return True
        if cmd == "mute":
            first = reason.split(None, 1)[0] if reason else ""
            if not DUR_RE.match(first):
                reason = f"10m {reason}".strip()
        line = f"{cmd} {tid} {reason}".strip()
    else:  # num
        m = re.match(r"^(\d{1,4})(?:\s+(.*))?$", rest, re.S)
        if not m:
            if rest:
                return False
            await message.channel.send(embed=err_e(
                f"اكتب الرقم: `{kw} 10`", "ما حددت الرقم"), delete_after=8)
            return True
        line = f"{cmd} {rest}".strip()

    # نحوّل الاختصار لأمر حقيقي — فتنطبق عليه نفس الصلاحيات والحماية
    orig = message.content
    message.content = f"{PREFIX}{line}"
    try:
        ctx = await bot.get_context(message)
    finally:
        message.content = orig
    if not ctx.valid:
        return False
    await bot.invoke(ctx)
    return True

@bot.event
async def on_message(message: discord.Message):
    if await run_shortcut(message):
        return
    await bot.process_commands(message)

