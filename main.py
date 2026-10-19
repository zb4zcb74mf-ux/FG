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

    # --- نظام الإجازات
    vc = g.setdefault("vac", {})
    vc.setdefault("channel", None)
    vc.setdefault("role", None)          # رتبة الإجازة
    vc.setdefault("staffrole", None)     # تنسحب عند قبول الاستقالة
    vc.setdefault("reviewers", None)
    vc.setdefault("max", 14)
    vc.setdefault("gap", 7)
    vc.setdefault("title", "نظام الإجازات")
    vc.setdefault("desc", (
        "مرحباً بك في نظام الإجازات، يرجى قراءة الشروط جيداً قبل التقديم:\n\n"
        "1️⃣ **المدة:** الحد الأقصى للإجازة هو **{max} يوم فقط** ولا يمكن زيادتها.\n"
        "2️⃣ **التفاعل:** يمنع منعاً باتاً طلب إجازة إذا كنت غير متفاعل (سيتم رفض طلبك).\n"
        "3️⃣ **التكرار:** يمنع طلب إجازات متتالية (يجب أن تمارس مهامك بين كل إجازة والأخرى).\n\n"
        "ملاحظة: بالضغط على \"طلب إجازة\" أنت تقر بموافقتك على الشروط أعلاه."))
    vc.setdefault("image", None)
    vc.setdefault("color", "5865F2")
    vc.setdefault("btn_req", "طلب إجازة")
    vc.setdefault("btn_res", "استقالة")
    vc.setdefault("subs", {})
    vc.setdefault("n", 0)
    vc.setdefault("active", {})
    vc.setdefault("last", {})
    # --- النظام التعريفي
    inf = g.setdefault("info", {})
    inf.setdefault("title", "النظام التعريفي")
    inf.setdefault("desc", (
        "مرحبا بكم في النظام التعريفي للإدارة.\n\nيمكنكم معرفة:\n"
        "• المهام الإدارية\n• الرتب الإدارية\n• القوانين الإدارية\n• الرومات الإدارية\n"
        "• جدول المخالفات الخاص بالشات\n\nعن طريق الأزرار بالأسفل"))
    inf.setdefault("footer", "يرجى مراجعة النظام باستمرار تحسباً لأي تحديث")
    inf.setdefault("image", None)
    inf.setdefault("color", "FFFFFF")
    if "sections" not in inf:
        inf["sections"] = {str(i): {"name": n, "content": "لم يُضف محتوى بعد."}
                           for i, n in enumerate(("الرتب", "القوانين", "الرومات", "المهام", "المخالفات"), 1)}
        inf["next"] = 6
    inf.setdefault("next", 6)
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
    text = "\n".join(parts) or "\u200b"

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

@bot.hybrid_command(name="shortcuts", aliases=["اختصارات"], description="عرض / تشغيل / إيقاف الاختصارات العربية")
@commands.guild_only()
async def shortcuts_cmd(ctx, action: Literal["list", "on", "off"] = "list"):
    s = conf(ctx.guild.id)["shortcuts"]
    if action != "list":
        if not ctx.author.guild_permissions.manage_guild:
            return await send_err(ctx, "تحتاج الصلاحية: `إدارة السيرفر`", "ما عندك صلاحية")
        s["enabled"] = action == "on"
        save_data()
        return await ctx.send(embed=ok_e("الاختصارات", "✅ **مفعّلة**" if s["enabled"] else "⏸️ **متوقفة**"))
    e = fancy("⚡ الاختصارات العربية", color=C_INFO,
              desc=f"اكتبها في الشات **بدون بادئة** — الحالة: {'🟢 مفعّلة' if s['enabled'] else '🔴 متوقفة'}")
    for n, v in SHORTCUT_DOC:
        e.add_field(name=n, value=v, inline=False)
    e.add_field(name="🛡️ الحماية", inline=False, value=(
        "• تشتغل فقط لمن عنده **نفس صلاحية الأمر الأصلي**.\n"
        "• غير المخوّل يُتجاهل بصمت — ما تتعارض مع كلام الأعضاء.\n"
        "• أوامر الأعضاء لازم **منشن / آيدي / رد** على الرسالة.\n"
        "• نفس فحص الرتب والهرمية مثل أوامر السلاش."))
    await ctx.send(embed=e)

# ---------------------------------------------------------------- القائمة (Help)
HELP_CATS = [
    ("home", "🏠", "الرئيسية"), ("general", "🌐", "عامة"), ("mod", "🛡️", "إدارية"),
    ("prot", "🔰", "الحماية والسجلات"), ("welcome", "👋", "الترحيب"),
    ("tickets", "🎫", "التذاكر"), ("inside", "🎛️", "تخصيص التذكرة"), ("short", "⚡", "الاختصارات"),
    ("extras", "🕌", "أذكار وإضافات"),
    ("vac", "🏖️", "الإجازات"), ("info", "📘", "النظام التعريفي"),
]

def help_embed(key: str) -> discord.Embed:
    P = PREFIX
    e = fancy(color=C_INFO)
    e.set_author(name=f"{BOT_NAME} • قائمة الأوامر", icon_url=bot.user.display_avatar.url if bot.user else None)
    if key == "home":
        e.description = (
            f"أهلاً بك في **{BOT_NAME}** 👋\n"
            "كل الأوامر تشتغل بالبادئة `" + P + "` أو بالسلاش `/`\n"
            "واختر القسم من القائمة تحت.\n\n"
            "🌐 **عامة** — معلومات وأدوات\n🛡️ **إدارية** — عقوبات وإدارة الرومات\n"
            "🔰 **الحماية** — القوانين، الروابط، السجلات\n👋 **الترحيب**\n🎫 **التذاكر**\n"
            "⚡ **الاختصارات** — `قفل` `فتح` `اسكت` `باند` ... بدون بادئة")
        e.add_field(name="💡 متغيرات النصوص", inline=False,
                    value="`{user}` `{name}` `{server}` `{count}`\nداخل التذكرة: `{date}` `{reason}` "
                          "`{type}` `{ticket}` `{support}` `{claimed}`\nللسطر الجديد في السلاش اكتب `\\n`")
    elif key == "general":
        e.title = "🌐 الأوامر العامة"
        e.description = (
            f"`{P}ping` `{P}avatar` `{P}banner` `{P}userinfo` `{P}serverinfo`\n"
            f"`{P}botinfo` `{P}roleinfo` `{P}membercount` `{P}say`\n"
            f"`{P}poll` `{P}announce` `{P}roll` `{P}coinflip` `{P}snipe`")
    elif key == "mod":
        e.title = "🛡️ الأوامر الإدارية"
        e.add_field(name="👥 الأعضاء", inline=False, value=(
            f"`{P}kick` `{P}ban` `{P}unban` `{P}mute` `{P}unmute`\n"
            f"`{P}warn` `{P}unwarn` `{P}warnings` `{P}clearwarns` `{P}warnsystem`\n"
            f"`{P}nick` `{P}addrole` `{P}removerole` `{P}history` `{P}case`"))
        e.add_field(name="💬 الرومات", inline=False, value=(
            f"`{P}clear` `{P}lock` `{P}unlock` `{P}hide` `{P}unhide`\n"
            f"`{P}nuke` `{P}slowmode`"))
    elif key == "prot":
        e.title = "🔰 الحماية والسجلات"
        e.description = (f"`{P}rulesguard` `{P}rulesoff` `{P}rulesexempt`\n"
                         f"`{P}antilink` `{P}badword` `{P}setmodlog`\n"
                         f"**💬 الردود التلقائية:** `{P}replyadd` `{P}replydel` `{P}replymode` "
                         f"`{P}replylist` `{P}replytoggle`")
    elif key == "welcome":
        e.title = "👋 الترحيب والمغادرة"
        e.description = (f"`{P}setwelcome` `{P}welcomeset` `{P}welcomeimage` `{P}welcomebanner` `{P}welcomethumb`\n"
                         f"`{P}welcomestyle` `{P}welcomereset` `{P}testwelcome`\n"
                         f"`{P}setleave` `{P}leavemsg` `{P}autorole`\n"
                         "متغيرات الترحيب: `{username}` `{inviter}` `{number}` `{date}` `{user}` `{name}` `{server}` `{count}`")
    elif key == "tickets":
        e.title = "🎫 التذاكر"
        e.description = (
            f"`{P}ticketpanel` `{P}panelset` `{P}panelimage`\n"
            f"`{P}ticketadd` `{P}ticketdel` `{P}ticketlist` `{P}ticketlog`\n"
            f"`{P}tadd` `{P}tremove` `{P}tclose` `{P}tclaim` `{P}tunclaim`\n"
            f"`{P}trename` `{P}tpriority` `{P}tlock` `{P}tunlock`\n"
            f"`{P}ttranscript` `{P}tblacklist` `{P}tmax` `{P}tautoclose` `{P}tstats`\n"
            f"`{P}points` `{P}topstaff` `{P}pointsadmin` `{P}pointsvalue` `{P}pointsreset`")
    elif key == "inside":
        e.title = "🎛️ تخصيص داخل التذكرة"
        e.description = (
            f"`{P}insideset` `{P}insideimage` `{P}insideimageoff` `{P}insidethumb`\n"
            f"`{P}insidebtn` `{P}insidereason` `{P}insidepreview`")
    elif key == "extras":
        e.title = "🕌 الأذكار وتيك توك والتحدث باسم البوت"
        e.add_field(name="🕌 الأذكار", inline=False, value=(
            f"`{P}azkarchannel` `{P}azkarinterval` `{P}azkarsession`\n"
            f"`{P}azkaradd` `{P}azkarnow`"))
        e.add_field(name="🎬 تيك توك", inline=False, value=f"`{P}tiktokset` `{P}tiktokoff`")
        e.add_field(name="🗣️ التحدث باسم البوت", inline=False, value=f"`{P}relayset` `{P}relayoff`")
        e.add_field(name="📥 تحميل تيك توك", inline=False, value=f"`{P}tt` + رابط المقطع (بدون علامة مائية)")
        e.add_field(name="📝 نظام التقديم", inline=False,
                    value=f"`{P}apply` ← new / channel / questions / role / reviewers / text / image / color / open / close / panel / list / show / delete")
        e.add_field(name="🖼️ الافتارات (Respect / MT)", inline=False,
                    value=f"`{P}avtset` ← servers / channel / text / image / color / status / panel / show\nللأعضاء: `/avt`")
        e.add_field(name="🎙️ الرومات الصوتية المؤقتة", inline=False,
                    value=f"`{P}tempvoice` `{P}tempvoicepanel` `{P}tempvoicename` `{P}tempvoiceoff`\n`{P}tempvoiceemoji` `{P}tempvoiceimage` `{P}tempvoicetext`")
    elif key == "vac":
        e.title = "🏖️ نظام الإجازات"
        e.description = VAC_HELP.replace("@@", P)
    elif key == "info":
        e.title = "📘 النظام التعريفي"
        e.description = INFO_HELP.replace("@@", P)
    else:
        e.title = "⚡ الاختصارات العربية"
        e.description = f"اكتبها بدون بادئة — اكتب `{P}shortcuts` للتفاصيل."
        for n, v in SHORTCUT_DOC:
            e.add_field(name=n, value=v, inline=False)
    return e

class HelpSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="📂 اختر القسم...", options=[
            discord.SelectOption(label=name, value=k, emoji=em) for k, em, name in HELP_CATS])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.owner_id:
            return await interaction.response.send_message("❌ هذي القائمة مو لك، اكتب الأمر بنفسك.", ephemeral=True)
        await interaction.response.edit_message(embed=help_embed(self.values[0]), view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.add_item(HelpSelect())

# ---------------------------------------------------------------- الأوامر العامة
@bot.hybrid_command(name="help", aliases=["مساعدة", "اوامر"], description="قائمة الأوامر")
async def help_cmd(ctx):
    await ctx.send(embed=help_embed("home"), view=HelpView(ctx.author.id))

@bot.hybrid_command(name="ping", aliases=["بنق"], description="سرعة البوت")
async def ping(ctx):
    t0 = time.perf_counter()
    msg = await ctx.send(embed=info_e("🏓 جاري القياس..."))
    api = round((time.perf_counter() - t0) * 1000)
    e = info_e("🏓 Pong!")
    e.add_field(name="📡 الاتصال", value=f"`{round(bot.latency * 1000)}ms`")
    e.add_field(name="⏱️ الاستجابة", value=f"`{api}ms`")
    await msg.edit(embed=e)

@bot.hybrid_command(name="avatar", aliases=["افتار"], description="صورة العضو")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = fancy(f"🖼️ صورة {member.display_name}", color=member.color.value or C_INFO)
    e.set_image(url=member.display_avatar.url)
    view = discord.ui.View()
    for fm in ("png", "jpg", "webp"):
        view.add_item(discord.ui.Button(label=fm.upper(), url=member.display_avatar.with_format(fm).url))
    await ctx.send(embed=e, view=view)

@bot.hybrid_command(name="banner", aliases=["بنر"], description="بنر العضو")
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if not user.banner:
        return await send_err(ctx, f"{member.mention} ما عنده بنر.", "ما فيه بنر")
    e = fancy(f"🎨 بنر {member.display_name}", color=user.accent_color.value if user.accent_color else C_INFO)
    e.set_image(url=user.banner.url)
    await ctx.send(embed=e)

BADGES = {
    "staff": "🛠️ طاقم ديسكورد", "partner": "🤝 شريك", "hypesquad": "🎉 HypeSquad",
    "bug_hunter": "🐛 صائد ثغرات", "hypesquad_bravery": "🟣 Bravery",
    "hypesquad_brilliance": "🟠 Brilliance", "hypesquad_balance": "🟢 Balance",
    "early_supporter": "💎 داعم مبكر", "verified_bot_developer": "🤖 مطور بوتات",
    "active_developer": "👨‍💻 مطور نشط", "discord_certified_moderator": "🛡️ مشرف معتمد",
}

@bot.hybrid_command(name="userinfo", aliases=["معلومات", "ui"], description="معلومات عضو")
@commands.guild_only()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]
    badges = [v for k, v in BADGES.items() if getattr(member.public_flags, k, False)]
    pos = sorted(ctx.guild.members, key=lambda m: m.joined_at or discord.utils.utcnow()).index(member) + 1
    warns = len(conf(ctx.guild.id)["warns"].get(str(member.id), []))
    e = fancy(f"👤 {member}", color=member.color.value or C_INFO)
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="🆔 الآيدي", value=f"`{member.id}`")
    e.add_field(name="📛 الاسم", value=member.display_name)
    e.add_field(name="🔢 ترتيب الدخول", value=f"#{pos}")
    e.add_field(name="📅 إنشاء الحساب", value=discord.utils.format_dt(member.created_at, "D") + "\n" + discord.utils.format_dt(member.created_at, "R"))
    e.add_field(name="📥 دخول السيرفر", value=discord.utils.format_dt(member.joined_at, "D") + "\n" + discord.utils.format_dt(member.joined_at, "R"))
    e.add_field(name="⚠️ التحذيرات", value=str(warns))
    flags = []
    if member.guild_permissions.administrator:
        flags.append("👑 مدير")
    if member.is_timed_out():
        flags.append("🔇 مكتوم")
    if member.premium_since:
        flags.append("💜 بوستر")
    if member.bot:
        flags.append("🤖 بوت")
    if flags or badges:
        e.add_field(name="🏅 الحالة والشارات", value=" • ".join(flags + badges), inline=False)
    e.add_field(name=f"🎭 الرتب ({len(roles)})", value=" ".join(roles[:15]) or "لا يوجد", inline=False)
    await ctx.send(embed=e)

@bot.hybrid_command(name="serverinfo", aliases=["سيرفر", "si"], description="معلومات السيرفر")
@commands.guild_only()
async def serverinfo(ctx):
    g = ctx.guild
    bots = sum(1 for m in g.members if m.bot)
    e = fancy(f"🏠 {g.name}")
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    if g.banner:
        e.set_image(url=g.banner.url)
    e.add_field(name="👑 المالك", value=g.owner.mention if g.owner else "؟")
    e.add_field(name="🆔 الآيدي", value=f"`{g.id}`")
    e.add_field(name="📅 الإنشاء", value=discord.utils.format_dt(g.created_at, "D"))
    e.add_field(name="👥 الأعضاء", value=f"**{g.member_count}**\n👤 {g.member_count - bots} • 🤖 {bots}")
    e.add_field(name="💬 الرومات", value=f"📝 {len(g.text_channels)} • 🔊 {len(g.voice_channels)}\n📁 {len(g.categories)}")
    e.add_field(name="🎭 الرتب", value=str(len(g.roles)))
    e.add_field(name="😀 الإيموجي", value=str(len(g.emojis)))
    e.add_field(name="💜 البوست", value=f"{g.premium_subscription_count} (لفل {g.premium_tier})")
    e.add_field(name="🔐 التحقق", value=str(g.verification_level).title())
    await ctx.send(embed=e)

@bot.hybrid_command(name="membercount", aliases=["اعضاء"], description="عدد الأعضاء")
@commands.guild_only()
async def membercount(ctx):
    g = ctx.guild
    bots = sum(1 for m in g.members if m.bot)
    e = fancy("👥 أعضاء السيرفر", f"# {g.member_count}")
    e.add_field(name="👤 أعضاء", value=str(g.member_count - bots))
    e.add_field(name="🤖 بوتات", value=str(bots))
    await ctx.send(embed=e)

@bot.hybrid_command(name="roleinfo", aliases=["رتبة"], description="معلومات رتبة")
@commands.guild_only()
async def roleinfo(ctx, role: discord.Role):
    keys = [PERM_AR[p] for p in PERM_AR if getattr(role.permissions, p, False)]
    e = fancy(f"🎭 {role.name}", color=role.color.value or C_INFO)
    e.add_field(name="🆔 الآيدي", value=f"`{role.id}`")
    e.add_field(name="👥 الأعضاء", value=str(len(role.members)))
    e.add_field(name="🎨 اللون", value=f"`{role.color}`")
    e.add_field(name="📶 الترتيب", value=str(role.position))
    e.add_field(name="📌 منفصلة", value="نعم" if role.hoist else "لا")
    e.add_field(name="🔔 قابلة للمنشن", value="نعم" if role.mentionable else "لا")
    e.add_field(name="📅 الإنشاء", value=discord.utils.format_dt(role.created_at, "D"))
    if keys:
        e.add_field(name="🔑 صلاحيات مهمة", value="، ".join(keys), inline=False)
    await ctx.send(embed=e)

@bot.hybrid_command(name="botinfo", aliases=["بوت"], description="معلومات البوت")
async def botinfo(ctx):
    up = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    d, rem = divmod(int(up.total_seconds()), 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    e = fancy(f"🤖 {BOT_NAME}")
    e.set_thumbnail(url=bot.user.display_avatar.url)
    e.add_field(name="🏠 السيرفرات", value=str(len(bot.guilds)))
    e.add_field(name="👥 المستخدمين", value=str(sum(g.member_count for g in bot.guilds)))
    e.add_field(name="⌨️ الأوامر", value=str(len(bot.commands)))
    e.add_field(name="⏳ مدة التشغيل", value=f"{d}ي {h}س {m}د {s}ث")
    e.add_field(name="📡 البنق", value=f"`{round(bot.latency * 1000)}ms`")
    e.add_field(name="🐍 Python", value=platform.python_version())
    e.add_field(name="📚 discord.py", value=discord.__version__)
    await ctx.send(embed=e)

@bot.hybrid_command(name="say", aliases=["قول"], description="البوت يكرر كلامك")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def say(ctx, *, text: str):
    if ctx.interaction:
        await ctx.send(embed=ok_e("تم الإرسال"), ephemeral=True)
        await ctx.channel.send(text, allowed_mentions=discord.AllowedMentions.none())
    else:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())

@bot.hybrid_command(name="poll", aliases=["تصويت"], description="تصويت — الخيارات مفصولة بـ |")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def poll(ctx, question: str, *, options: str):
    opts = [o.strip() for o in options.split("|") if o.strip()]
    if not 2 <= len(opts) <= 10:
        return await send_err(ctx, "من 2 إلى 10 خيارات مفصولة بـ `|`\nمثال: `poll \"سؤالك\" خيار1 | خيار2`", "خيارات غير صحيحة")
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    e = fancy(f"📊 {question}", "\n\n".join(f"{nums[i]}  {o}" for i, o in enumerate(opts)))
    e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    msg = await ctx.channel.send(embed=e)
    for i in range(len(opts)):
        await msg.add_reaction(nums[i])
    if ctx.interaction:
        await ctx.send(embed=ok_e("تم إنشاء التصويت"), ephemeral=True)

@bot.hybrid_command(name="announce", aliases=["اعلان"], description="إرسال إعلان في روم")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def announce(ctx, channel: discord.TextChannel, *, text: str):
    e = fancy("📢 إعلان", nl(text))
    e.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
    await channel.send(embed=e)
    await ctx.send(embed=ok_e("تم نشر الإعلان", channel.mention), ephemeral=True)

@bot.hybrid_command(name="roll", aliases=["نرد"], description="رمي نرد")
async def roll(ctx, sides: int = 6):
    if not 2 <= sides <= 1000:
        return await send_err(ctx, "الأوجه من 2 إلى 1000.", "رقم غير صحيح")
    await ctx.send(embed=info_e("🎲 النرد", f"طلع لك **{random.randint(1, sides)}** من {sides}"))

@bot.hybrid_command(name="coinflip", aliases=["عملة"], description="صورة أو كتابة")
async def coinflip(ctx):
    await ctx.send(embed=info_e("🪙 العملة", random.choice(["**صورة**", "**كتابة**"])))

# آخر رسالة انحذفت في كل روم (للأمر snipe)
SNIPES: dict[int, dict] = {}

@bot.listen("on_message_delete")
async def snipe_store(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    if not message.content and not message.attachments:
        return
    SNIPES[message.channel.id] = {
        "author": message.author, "content": message.content or "",
        "files": [a.url for a in message.attachments], "time": discord.utils.utcnow()}

@bot.hybrid_command(name="snipe", aliases=["سنايب"], description="آخر رسالة انحذفت في الروم")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def snipe(ctx):
    s = SNIPES.get(ctx.channel.id)
    if not s:
        return await send_err(ctx, "ما فيه رسائل محذوفة حديثة في هذا الروم.", "ما فيه شي")
    e = fancy("🕵️ آخر رسالة محذوفة", s["content"][:2000] or "—", C_WARN)
    e.set_author(name=str(s["author"]), icon_url=s["author"].display_avatar.url)
    if s["files"]:
        e.add_field(name="📎 مرفقات", value="\n".join(s["files"][:5]), inline=False)
    e.add_field(name="🕐 انحذفت", value=discord.utils.format_dt(s["time"], "R"))
    await ctx.send(embed=e)

# ---------------------------------------------------------------- الأوامر الإدارية: العقوبات
@bot.hybrid_command(name="kick", aliases=["طرد"], description="طرد عضو")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
@commands.guild_only()
async def kick(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await send_err(ctx, err)
    await notify(member, ctx.guild, "👢", "تم طردك من السيرفر", reason, C_WARN)
    await member.kick(reason=f"{ctx.author}: {reason}")
    await finish_mod(ctx, "👢", "تم الطرد", member, reason, C_WARN)

@bot.hybrid_command(name="ban", aliases=["باند", "حظر"], description="حظر عضو (أو آيدي مستخدم)")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
@commands.guild_only()
async def ban(ctx, user: discord.User, *, reason: str = "بدون سبب"):
    member = ctx.guild.get_member(user.id)
    if member:
        err = can_act(ctx, member)
        if err:
            return await send_err(ctx, err)
        await notify(member, ctx.guild, "🔨", "تم حظرك من السيرفر", reason, C_ERR)
    elif user.id == ctx.author.id:
        return await send_err(ctx, "ما تقدر تنفذ هذا على نفسك.")
    await ctx.guild.ban(user, reason=f"{ctx.author}: {reason}")
    await finish_mod(ctx, "🔨", "تم الحظر", user, reason, C_ERR)

@bot.hybrid_command(name="unban", aliases=["فكباند", "فك_باند"], description="فك الحظر بالآيدي")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
@commands.guild_only()
async def unban(ctx, user_id: str, *, reason: str = "بدون سبب"):
    digits = re.sub(r"\D", "", user_id)
    if not digits:
        return await send_err(ctx, "اكتب آيدي المحظور.", "آيدي غير صحيح")
    try:
        user = await bot.fetch_user(int(digits))
        await ctx.guild.fetch_ban(user)
    except discord.NotFound:
        return await send_err(ctx, "هذا الشخص مو محظور أو الآيدي غلط.", "ما لقيت الحظر")
    await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
    await finish_mod(ctx, "✅", "تم فك الحظر", user, reason, C_OK)

@bot.hybrid_command(name="mute", aliases=["اسكت", "كتم"], description="كتم عضو (تايم أوت) — المدة مثل 30 أو 2h أو 1d")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.guild_only()
async def mute(ctx, member: discord.Member, duration: str = "10m", *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await send_err(ctx, err)
    minutes = parse_duration(duration)
    if minutes is None:
        return await send_err(ctx, "المدة غير صحيحة. أمثلة: `30` `30m` `2h` `1d` `30د` `2س` `1ي`", "مدة غير صحيحة")
    if not 1 <= minutes <= 40320:
        return await send_err(ctx, "المدة من دقيقة إلى 28 يوم.", "مدة غير مسموحة")
    until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
    await member.timeout(datetime.timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
    await notify(member, ctx.guild, "🔇", "تم كتمك", reason, C_WARN, [("⏳ المدة", human_minutes(minutes))])
    await finish_mod(ctx, "🔇", "تم الكتم", member, reason, C_WARN, [
        ("⏳ المدة", human_minutes(minutes)),
        ("🔓 ينتهي", discord.utils.format_dt(until, "R"))])

@bot.hybrid_command(name="unmute", aliases=["تكلم"], description="فك الكتم")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
@commands.guild_only()
async def unmute(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    if not member.is_timed_out():
        return await send_err(ctx, f"{member.mention} مو مكتوم.", "العضو مو مكتوم")
    await member.timeout(None, reason=f"{ctx.author}: {reason}")
    await finish_mod(ctx, "🔊", "تم فك الكتم", member, reason, C_OK)

@bot.hybrid_command(name="warn", aliases=["تحذير", "انذار"], description="تحذير عضو")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def warn(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await send_err(ctx, err)
    c = conf(ctx.guild.id)
    lst = c["warns"].setdefault(str(member.id), [])
    lst.append({"reason": reason, "mod": ctx.author.id,
                "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save_data()
    extra = [("📊 إجمالي التحذيرات", f"**{len(lst)}**")]
    await notify(member, ctx.guild, "⚠️", "وصلك تحذير", reason, C_WARN, extra)

    ws = c["warnsys"]
    auto = None
    if ws["threshold"] and len(lst) % ws["threshold"] == 0:
        try:
            if ws["action"] == "mute":
                await member.timeout(datetime.timedelta(minutes=ws["minutes"]), reason="تحذيرات متراكمة")
                auto = f"كتم {human_minutes(ws['minutes'])}"
            elif ws["action"] == "kick":
                await member.kick(reason="تحذيرات متراكمة")
                auto = "طرد"
            elif ws["action"] == "ban":
                await member.ban(reason="تحذيرات متراكمة")
                auto = "حظر"
        except discord.HTTPException:
            auto = None
    if auto:
        extra.append(("⚡ عقوبة تلقائية", auto))
    await finish_mod(ctx, "⚠️", "تم التحذير", member, reason, C_WARN, extra)

@bot.hybrid_command(name="warnsystem", aliases=["نظام_التحذيرات"], description="عقوبة تلقائية كل X تحذيرات (0 للإيقاف)")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def warnsystem(ctx, threshold: int, action: Literal["mute", "kick", "ban"] = "mute", minutes: int = 60):
    if not 0 <= threshold <= 20:
        return await send_err(ctx, "العدد من 0 إلى 20 (0 = إيقاف).", "رقم غير صحيح")
    if not 1 <= minutes <= 40320:
        return await send_err(ctx, "مدة الكتم من 1 إلى 40320 دقيقة.", "رقم غير صحيح")
    ws = conf(ctx.guild.id)["warnsys"]
    ws.update(threshold=threshold, action=action, minutes=minutes)
    save_data()
    if not threshold:
        return await ctx.send(embed=ok_e("العقوبة التلقائية", "⏸️ تم الإيقاف"))
    detail = f"كتم {human_minutes(minutes)}" if action == "mute" else ("طرد" if action == "kick" else "حظر")
    await ctx.send(embed=ok_e("العقوبة التلقائية", f"كل **{threshold}** تحذيرات → **{detail}**"))

@bot.hybrid_command(name="warnings", aliases=["تحذيرات"], description="عرض تحذيرات عضو")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def warnings(ctx, member: discord.Member):
    lst = conf(ctx.guild.id)["warns"].get(str(member.id), [])
    if not lst:
        return await ctx.send(embed=ok_e("سجل نظيف", f"{member.mention} ما عنده تحذيرات."))
    lines = []
    for i, w in enumerate(lst[-15:], max(1, len(lst) - 14)):
        try:
            ts = f"<t:{int(datetime.datetime.fromisoformat(w['time']).timestamp())}:R>"
        except (KeyError, ValueError):
            ts = ""
        lines.append(f"**#{i}** {ts}\n└ {w['reason']} — <@{w['mod']}>")
    e = warn_e(f"تحذيرات {member.display_name}", "\n".join(lines))
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="📊 الإجمالي", value=str(len(lst)))
    await ctx.send(embed=e)

@bot.hybrid_command(name="unwarn", aliases=["حذف_تحذير"], description="حذف تحذير واحد من عضو (برقمه)")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def unwarn(ctx, member: discord.Member, number: int = 1):
    lst = conf(ctx.guild.id)["warns"].get(str(member.id), [])
    if not 1 <= number <= len(lst):
        return await send_err(ctx, f"رقم التحذير غير صحيح. عنده **{len(lst)}** تحذير.", "رقم غير صحيح")
    removed = lst.pop(number - 1)
    save_data()
    await finish_mod(ctx, "🧽", "تم حذف تحذير", member, removed["reason"], C_OK,
                     [("📊 المتبقي", f"**{len(lst)}**")])

@bot.hybrid_command(name="clearwarns", aliases=["مسح_التحذيرات"], description="مسح كل تحذيرات عضو")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def clearwarns(ctx, member: discord.Member):
    old = conf(ctx.guild.id)["warns"].pop(str(member.id), [])
    save_data()
    await finish_mod(ctx, "🧹", "تم مسح التحذيرات", member, "مسح كامل", C_OK,
                     [("🗑️ انمسح", f"**{len(old)}**")])

@bot.hybrid_command(name="history", aliases=["سجل"], description="سجل العقوبات على عضو")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def history(ctx, member: discord.User):
    cs = [x for x in conf(ctx.guild.id)["cases"]["list"] if x["target"] == member.id]
    if not cs:
        return await ctx.send(embed=ok_e("سجل نظيف", f"{member.mention} ما عليه أي حالات."))
    lines = []
    for x in cs[-15:][::-1]:
        ts = int(datetime.datetime.fromisoformat(x["time"]).timestamp())
        lines.append(f"**#{x['id']}** {x['action']} • <t:{ts}:R>\n└ {x['reason'][:80]} — <@{x['mod']}>")
    e = info_e(f"📁 سجل {member.display_name}", "\n".join(lines))
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="📊 إجمالي الحالات", value=str(len(cs)))
    await ctx.send(embed=e)

@bot.hybrid_command(name="case", aliases=["حالة"], description="عرض حالة عقوبة برقمها")
@commands.has_permissions(manage_messages=True)
@commands.guild_only()
async def case_cmd(ctx, number: int):
    x = next((c for c in conf(ctx.guild.id)["cases"]["list"] if c["id"] == number), None)
    if not x:
        return await send_err(ctx, "ما لقيت حالة بهذا الرقم.", "حالة غير موجودة")
    ts = discord.utils.format_dt(datetime.datetime.fromisoformat(x["time"]), "F")
    e = info_e(f"📁 حالة #{x['id']} — {x['action']}")
    e.add_field(name="👤 العضو", value=f"<@{x['target']}>\n`{x['target']}`")
    e.add_field(name="🛡️ المسؤول", value=f"<@{x['mod']}>")
    e.add_field(name="🕐 الوقت", value=ts)
    e.add_field(name="📝 السبب", value=x["reason"][:1000], inline=False)
    await ctx.send(embed=e)

# ---------------------------------------------------------------- الأوامر الإدارية: الرومات والأعضاء
@bot.hybrid_command(name="clear", aliases=["مسح"], description="مسح رسائل (مع إمكانية تحديد عضو)")
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
@commands.guild_only()
async def clear(ctx, amount: int, member: Optional[discord.Member] = None):
    if not 1 <= amount <= 100:
        return await send_err(ctx, "العدد من 1 إلى 100.", "عدد غير صحيح")
    if ctx.interaction:
        await ctx.defer(ephemeral=True)
    else:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
    count = 0

    def check(m: discord.Message) -> bool:
        nonlocal count
        if m.pinned or count >= amount:
            return False
        if member and m.author.id != member.id:
            return False
        count += 1
        return True

    deleted = await ctx.channel.purge(limit=100 if member else amount, check=check)
    e = ok_e("تم مسح الرسائل")
    e.add_field(name="🗑️ العدد", value=f"**{len(deleted)}**")
    e.add_field(name="💬 الروم", value=ctx.channel.mention)
    e.add_field(name="🛡️ بواسطة", value=ctx.author.mention)
    if member:
        e.add_field(name="🎯 رسائل", value=member.mention)
    if ctx.interaction:
        await ctx.send(embed=e, ephemeral=True)
    else:
        await ctx.send(embed=e, delete_after=5)
    cid = conf(ctx.guild.id)["modlog"]["channel"]
    if cid and cid != ctx.channel.id:
        await modlog(ctx.guild, e)

def _chan_embed(emoji, title, ch, mod, reason, color):
    e = fancy(f"{emoji} {title}", color=color)
    e.add_field(name="💬 الروم", value=ch.mention)
    e.add_field(name="🛡️ بواسطة", value=mod.mention)
    e.add_field(name="📝 السبب", value=reason or "بدون سبب", inline=False)
    return e

@bot.hybrid_command(name="lock", aliases=["قفل"], description="قفل الروم")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
@commands.guild_only()
async def lock(ctx, channel: Optional[discord.TextChannel] = None, *, reason: str = "بدون سبب"):
    ch = channel or ctx.channel
    ow = ch.overwrites_for(ctx.guild.default_role)
    if ow.send_messages is False:
        return await send_err(ctx, f"{ch.mention} مقفل من قبل.", "الروم مقفل أصلاً")
    ow.send_messages = False
    await ch.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"{ctx.author}: {reason}")
    e = _chan_embed("🔒", "تم قفل الروم", ch, ctx.author, reason, C_ERR)
    await ctx.send(embed=e)
    await modlog(ctx.guild, e)

@bot.hybrid_command(name="unlock", aliases=["فتح"], description="فتح الروم")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
@commands.guild_only()
async def unlock(ctx, channel: Optional[discord.TextChannel] = None, *, reason: str = "بدون سبب"):
    ch = channel or ctx.channel
    ow = ch.overwrites_for(ctx.guild.default_role)
    if ow.send_messages is not False:
        return await send_err(ctx, f"{ch.mention} مو مقفل.", "الروم مفتوح أصلاً")
    ow.send_messages = None
    await ch.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"{ctx.author}: {reason}")
    e = _chan_embed("🔓", "تم فتح الروم", ch, ctx.author, reason, C_OK)
    await ctx.send(embed=e)
    await modlog(ctx.guild, e)

@bot.hybrid_command(name="hide", aliases=["اخفاء", "إخفاء"], description="إخفاء الروم عن الجميع")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
@commands.guild_only()
async def hide(ctx, channel: Optional[discord.TextChannel] = None, *, reason: str = "بدون سبب"):
    ch = channel or ctx.channel
    ow = ch.overwrites_for(ctx.guild.default_role)
    if ow.view_channel is False:
        return await send_err(ctx, f"{ch.mention} مخفي من قبل.", "الروم مخفي أصلاً")
    ow.view_channel = False
    await ch.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"{ctx.author}: {reason}")
    e = _chan_embed("🙈", "تم إخفاء الروم", ch, ctx.author, reason, C_WARN)
    try:
        await ctx.send(embed=e)
    except discord.HTTPException:
        pass
    await modlog(ctx.guild, e)

@bot.hybrid_command(name="unhide", aliases=["اظهار", "إظهار"], description="إظهار الروم")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
@commands.guild_only()
async def unhide(ctx, channel: Optional[discord.TextChannel] = None, *, reason: str = "بدون سبب"):
    ch = channel or ctx.channel
    ow = ch.overwrites_for(ctx.guild.default_role)
    if ow.view_channel is not False:
        return await send_err(ctx, f"{ch.mention} ظاهر أصلاً.", "الروم ظاهر أصلاً")
    ow.view_channel = None
    await ch.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"{ctx.author}: {reason}")
    e = _chan_embed("👁️", "تم إظهار الروم", ch, ctx.author, reason, C_OK)
    await ctx.send(embed=e)
    await modlog(ctx.guild, e)

@bot.hybrid_command(name="slowmode", aliases=["سلو", "بطيء"], description="وضع البطيء بالثواني (0 للإلغاء)")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
@commands.guild_only()
async def slowmode(ctx, seconds: int):
    if not 0 <= seconds <= 21600:
        return await send_err(ctx, "من 0 إلى 21600 ثانية.", "رقم غير صحيح")
    await ctx.channel.edit(slowmode_delay=seconds)
    if seconds:
        e = fancy("🐢 تم تفعيل الوضع البطيء", color=C_WARN)
        e.add_field(name="⏱️ المدة", value=f"**{seconds}** ثانية")
    else:
        e = ok_e("تم إلغاء الوضع البطيء")
    e.add_field(name="💬 الروم", value=ctx.channel.mention)
    e.add_field(name="🛡️ بواسطة", value=ctx.author.mention)
    await ctx.send(embed=e)

@bot.hybrid_command(name="nick", aliases=["لقب"], description="تغيير لقب عضو")
@commands.has_permissions(manage_nicknames=True)
@commands.bot_has_permissions(manage_nicknames=True)
@commands.guild_only()
async def nick(ctx, member: discord.Member, *, nickname: str = None):
    err = can_act(ctx, member) if member != ctx.author else None
    if err:
        return await send_err(ctx, err)
    old = member.display_name
    await member.edit(nick=nickname, reason=f"{ctx.author}")
    e = ok_e("تم تغيير اللقب")
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 العضو", value=member.mention)
    e.add_field(name="قبل", value=old)
    e.add_field(name="بعد", value=nickname or "الاسم الأصلي")
    await ctx.send(embed=e)

def _role_err(ctx, role: discord.Role) -> str | None:
    if role.managed or role == ctx.guild.default_role:
        return "هذي الرتبة ما تنعطى يدوياً."
    if role >= ctx.guild.me.top_role or (role >= ctx.author.top_role and ctx.author != ctx.guild.owner):
        return "هذي الرتبة أعلى من رتبتك أو رتبة البوت."
    return None

@bot.hybrid_command(name="addrole", aliases=["اعطاء_رتبة"], description="إعطاء رتبة لعضو")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
@commands.guild_only()
async def addrole(ctx, member: discord.Member, role: discord.Role):
    err = _role_err(ctx, role)
    if err:
        return await send_err(ctx, err)
    if role in member.roles:
        return await send_err(ctx, f"{member.mention} عنده {role.mention} من قبل.", "الرتبة موجودة")
    await member.add_roles(role, reason=f"{ctx.author}")
    e = ok_e("تمت إضافة الرتبة")
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 العضو", value=member.mention)
    e.add_field(name="🎭 الرتبة", value=role.mention)
    e.add_field(name="🛡️ بواسطة", value=ctx.author.mention)
    await ctx.send(embed=e)

@bot.hybrid_command(name="removerole", aliases=["سحب_رتبة"], description="سحب رتبة من عضو")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
@commands.guild_only()
async def removerole(ctx, member: discord.Member, role: discord.Role):
    err = _role_err(ctx, role)
    if err:
        return await send_err(ctx, err)
    if role not in member.roles:
        return await send_err(ctx, f"{member.mention} ما عنده {role.mention}.", "الرتبة مو موجودة")
    await member.remove_roles(role, reason=f"{ctx.author}")
    e = ok_e("تم سحب الرتبة")
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 العضو", value=member.mention)
    e.add_field(name="🎭 الرتبة", value=role.mention)
    e.add_field(name="🛡️ بواسطة", value=ctx.author.mention)
    await ctx.send(embed=e)

@bot.hybrid_command(name="nuke", aliases=["تنظيف"], description="مسح كل رسائل الروم (يعيد إنشاءه)")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_channels=True)
@commands.guild_only()
async def nuke(ctx):
    ch = ctx.channel
    if str(ch.id) in conf(ctx.guild.id)["tickets"]:
        return await send_err(ctx, "ما تقدر تسوي nuke لروم تذكرة. استخدم أمر الإغلاق.", "روم تذكرة")
    view = ConfirmView(ctx.author.id)
    msg = await ctx.send(embed=warn_e("تأكيد التنظيف",
                                      f"راح تنحذف **كل** رسائل {ch.mention} ويُعاد إنشاء الروم.\nما ينفع التراجع!"),
                         view=view)
    await view.wait()
    if not view.value:
        return await msg.edit(embed=err_e("تم إلغاء العملية.", "ملغي"), view=None)
    await msg.edit(embed=info_e("💥 جاري التنظيف..."), view=None)
    new = await ch.clone(reason=f"Nuke by {ctx.author}")
    await new.edit(position=ch.position)
    await ch.delete()
    e = fancy("💥 تم تنظيف الروم", color=C_OK)
    e.add_field(name="🛡️ بواسطة", value=ctx.author.mention)
    await new.send(embed=e)

# ---------------------------------------------------------------- إعدادات الترحيب
@bot.hybrid_command(name="setwelcome", description="تحديد روم الترحيب")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: discord.TextChannel):
    conf(ctx.guild.id)["welcome"]["channel"] = channel.id
    save_data()
    await ctx.send(embed=embed("✅ روم الترحيب", channel.mention))

@bot.hybrid_command(name="welcomeset", description="تعديل نص الترحيب (المتغيرات: {user} {name} {server} {count})")
@commands.has_permissions(manage_guild=True)
async def welcomeset(ctx, item: Literal["title", "desc", "footer", "color", "content", "author"], *, value: str):
    """title=العنوان الكبير | desc=النص (المتغيرات: {username} {inviter} {number} {date} {user} {name} {server} {count}) | footer=السطر الأخير | color=لون الخط الجانبي | content/author=للتصميم الكلاسيكي فقط"""
    w = conf(ctx.guild.id)["welcome"]
    if item == "color":
        if not valid_color(value):
            return await ctx.send("❌ اللون لازم يكون HEX مثل `E8352A`.")
        w["color"] = value.strip().lstrip("#")
    else:
        w[item] = nl(value)
    save_data()
    await ctx.send(embed=embed("✅ تم الحفظ", f"**{item}** ← {value}\nجرّب `{PREFIX}testwelcome`"))

@bot.hybrid_command(name="welcomeimage", description="تغيير الصورة السفلية للترحيب (صورة مرفقة أو رابط)")
@commands.has_permissions(manage_guild=True)
async def welcomeimage(ctx, image: discord.Attachment = None, url: str = None):
    if image is None and url and url.strip().lower() in ("off", "none", "-", "بدون", "لا"):
        conf(ctx.guild.id)["welcome"]["image"] = None
        save_data()
        return await ctx.send(embed=embed("✅ تمت إزالة صورة الترحيب"))
    try:
        conf(ctx.guild.id)["welcome"]["image"] = await store_image(ctx.guild.id, "welcome", image, url)
    except ValueError as err:
        return await ctx.send(f"❌ {err}")
    save_data()
    await ctx.send(embed=embed("✅ تم تغيير صورة الترحيب", f"جرّب `{PREFIX}testwelcome`"))

@bot.hybrid_command(name="welcomethumb", description="إظهار/إخفاء صورة العضو الصغيرة")
@commands.has_permissions(manage_guild=True)
async def welcomethumb(ctx, enabled: bool):
    conf(ctx.guild.id)["welcome"]["thumb"] = enabled
    save_data()
    await ctx.send(embed=embed("✅ تم", "تظهر" if enabled else "مخفية"))

@bot.hybrid_command(name="welcomebanner", description="الشريط السفلي تحت بطاقة الترحيب (صورة مرفقة أو رابط — اكتب off للإزالة)")
@commands.has_permissions(manage_guild=True)
async def welcomebanner(ctx, image: discord.Attachment = None, url: str = None):
    if image is None and url and url.strip().lower() in ("off", "none", "-", "بدون", "لا"):
        conf(ctx.guild.id)["welcome"]["banner"] = None
        save_data()
        return await ctx.send(embed=embed("✅ تمت إزالة الشريط السفلي"))
    try:
        conf(ctx.guild.id)["welcome"]["banner"] = await store_image(ctx.guild.id, "welcomebanner", image, url)
    except ValueError as err:
        return await ctx.send(f"❌ {err}")
    save_data()
    await ctx.send(embed=embed("✅ تم تغيير الشريط السفلي", f"جرّب `{PREFIX}testwelcome`"))

@bot.hybrid_command(name="welcomestyle", description="شكل الترحيب: modern (الجديد) أو classic (الإيمبد القديم)")
@commands.has_permissions(manage_guild=True)
async def welcomestyle(ctx, style: Literal["modern", "classic"]):
    conf(ctx.guild.id)["welcome"]["style"] = style
    save_data()
    await ctx.send(embed=embed("✅ تم", f"شكل الترحيب: **{style}**\nجرّب `{PREFIX}testwelcome`"))

@bot.hybrid_command(name="welcomereset", description="إرجاع نص الترحيب للتصميم الجديد الافتراضي")
@commands.has_permissions(manage_guild=True)
async def welcomereset(ctx):
    w = conf(ctx.guild.id)["welcome"]
    w.update(title="Welcome", desc=WELCOME_DESC, footer="{date}", style="modern")
    save_data()
    await ctx.send(embed=embed("✅ تم إرجاع التصميم الافتراضي", f"جرّب `{PREFIX}testwelcome`"))

@bot.hybrid_command(name="testwelcome", description="تجربة رسالة الترحيب")
@commands.has_permissions(manage_guild=True)
async def testwelcome(ctx):
    await send_welcome(ctx, ctx.author, ctx.author.id)

@bot.hybrid_command(name="setleave", description="تحديد روم المغادرة")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: discord.TextChannel):
    conf(ctx.guild.id)["leave"]["channel"] = channel.id
    save_data()
    await ctx.send(embed=embed("✅ روم المغادرة", channel.mention))

@bot.hybrid_command(name="leavemsg", description="تغيير رسالة المغادرة")
@commands.has_permissions(manage_guild=True)
async def leavemsg(ctx, *, message: str):
    conf(ctx.guild.id)["leave"]["msg"] = nl(message)
    save_data()
    await ctx.send(embed=embed("✅ تم حفظ رسالة المغادرة", message))

@bot.hybrid_command(name="autorole", description="رتبة تلقائية للأعضاء الجدد")
@commands.has_permissions(manage_guild=True)
async def autorole(ctx, role: discord.Role = None):
    conf(ctx.guild.id)["autorole"] = role.id if role else None
    save_data()
    await ctx.send(embed=embed("✅ الرتبة التلقائية", role.mention if role else "تم الإلغاء"))

# ---------------------------------------------------------------- نظام التذاكر
def is_staff(member: discord.Member, info: dict | None = None) -> bool:
    if member.guild_permissions.manage_channels:
        return True
    role_id = (info or {}).get("role")
    return bool(role_id) and any(r.id == role_id for r in member.roles)

async def ticket_log(guild: discord.Guild, e: discord.Embed, file: discord.File = None):
    cid = conf(guild.id)["ticket"]["log_channel"]
    ch = guild.get_channel(cid) if cid else None
    if ch:
        try:
            await ch.send(embed=e, file=file)
        except discord.Forbidden:
            pass

async def build_transcript(channel: discord.TextChannel) -> bytes:
    lines = []
    async for m in channel.history(limit=None, oldest_first=True):
        content = m.content or ""
        if m.attachments:
            content += " " + " ".join(a.url for a in m.attachments)
        lines.append(f"[{m.created_at:%Y-%m-%d %H:%M}] {m.author} : {content}")
    return ("\n".join(lines) or "لا توجد رسائل").encode("utf-8")

class RatingView(discord.ui.View):
    """تقييم الدعم — يوصل لصاحب التذكرة في الخاص بعد الإغلاق."""
    def __init__(self, guild: discord.Guild, ticket_name: str, staff_id):
        super().__init__(timeout=86400)
        self.guild, self.ticket_name, self.staff_id = guild, ticket_name, staff_id

    @discord.ui.select(placeholder="⭐ قيّم الدعم", options=[
        discord.SelectOption(label=f"{i} من 5", value=str(i), emoji="⭐") for i in range(5, 0, -1)])
    async def rate(self, interaction: discord.Interaction, select: discord.ui.Select):
        n = int(select.values[0])
        if self.staff_id:
            record_rating(self.guild.id, self.staff_id, n)
        e = embed("⭐ تقييم جديد", color=0xFFD700)
        e.add_field(name="التذكرة", value=self.ticket_name)
        e.add_field(name="التقييم", value="⭐" * n)
        e.add_field(name="المقيّم", value=interaction.user.mention)
        if self.staff_id:
            e.add_field(name="المستلم", value=f"<@{self.staff_id}>")
        await ticket_log(self.guild, e)
        await interaction.response.edit_message(content="شكراً لتقييمك 💙", view=None)

async def close_ticket(channel: discord.TextChannel, closer: discord.Member, reason: str = None):
    guild = channel.guild
    c = conf(guild.id)
    info = c["tickets"].get(str(channel.id))
    if not info:
        return
    data = await build_transcript(channel)
    owner = guild.get_member(info["owner"])

    # نقاط المستلم — تنحسب تلقائياً عند الإغلاق
    earned = 0
    claimer = info.get("claimed")
    if claimer and claimer != info["owner"]:
        earned = c["ticket"]["point_value"]
        award_points(guild.id, claimer, earned)

    e = embed("🔒 تذكرة مغلقة", color=0xFF5555)
    e.add_field(name="التذكرة", value=channel.name)
    e.add_field(name="النوع", value=info.get("type", "—"))
    e.add_field(name="صاحبها", value=f"<@{info['owner']}>")
    e.add_field(name="أغلقها", value=closer.mention)
    e.add_field(name="استلمها", value=f"<@{info['claimed']}>" if info.get("claimed") else "لا أحد")
    if earned:
        e.add_field(name="🏆 النقاط", value=f"<@{claimer}> **+{earned}**")
    e.add_field(name="فُتحت", value=discord.utils.format_dt(datetime.datetime.fromisoformat(info["opened"]), "f"))
    if info.get("reason"):
        e.add_field(name="سبب الفتح", value=info["reason"][:300], inline=False)
    if reason:
        e.add_field(name="سبب الإغلاق", value=reason[:300], inline=False)
    await ticket_log(guild, e, discord.File(io.BytesIO(data), filename=f"{channel.name}.txt"))

    if owner:
        try:
            await owner.send(f"🔒 تم إغلاق تذكرتك في **{guild.name}**."
                             + (f"\nالسبب: {reason}" if reason else "") + "\nهذا سجل المحادثة:",
                             file=discord.File(io.BytesIO(data), filename=f"{channel.name}.txt"))
            await owner.send("كيف كانت تجربتك مع الدعم؟",
                             view=RatingView(guild, channel.name, info.get("claimed")))
        except discord.Forbidden:
            pass

    c["tickets"].pop(str(channel.id), None)
    save_data()
    await asyncio.sleep(3)
    await channel.delete(reason=f"Ticket closed by {closer}")

# ---------- رسالة التحكم داخل التذكرة (قابلة للتخصيص بالكامل)
def fmt_ticket(text: str, user, channel, info: dict, support) -> str:
    claimed = f"<@{info['claimed']}>" if info.get("claimed") else "لا أحد"
    opened = datetime.datetime.fromisoformat(info["opened"])
    return ((text or "")
            .replace("{user}", user.mention)
            .replace("{name}", user.name)
            .replace("{server}", user.guild.name)
            .replace("{date}", discord.utils.format_dt(opened, "F"))
            .replace("{reason}", info.get("reason") or "—")
            .replace("{type}", info.get("type", "—"))
            .replace("{ticket}", channel.mention)
            .replace("{support}", support.mention if support else "")
            .replace("{claimed}", claimed))

def build_inside(guild: discord.Guild, user: discord.Member, channel, info: dict):
    ins = conf(guild.id)["inside"]
    support = guild.get_role(info["role"]) if info.get("role") else None
    ft = lambda s: fmt_ticket(s, user, channel, info, support)
    e = discord.Embed(description=ft(ins["desc"]), color=parse_color(ins["color"]))
    if ins["author"]:
        e.set_author(name=ft(ins["author"]), icon_url=ins["author_icon"] or None)
    if ins["thumb"]:
        e.set_thumbnail(url=user.display_avatar.url)
    if ins["footer"]:
        e.set_footer(text=ft(ins["footer"]))
    f = apply_image(e, ins["image"], "ticketinside")
    return (ft(ins["content"]).strip() or None), e, f

async def open_ticket(interaction: discord.Interaction, key: str, reason: str):
    guild, user = interaction.guild, interaction.user
    c = conf(guild.id)
    t = c["ticket"]["types"].get(key)
    if not t:
        return await interaction.response.send_message("❌ هذا النوع انحذف.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    category = guild.get_channel(t["category"]) if t.get("category") else None
    support = guild.get_role(t["role"]) if t.get("role") else None
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                          attach_files=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                              manage_channels=True, read_message_history=True),
    }
    if support:
        ow[support] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                  attach_files=True, read_message_history=True)
    c["ticket"]["counter"] += 1
    slug = re.sub(r"[^a-z0-9]+", "-", t["label"].lower()).strip("-") or "ticket"
    channel = await guild.create_text_channel(
        f"{slug}-{c['ticket']['counter']:04d}", category=category, overwrites=ow,
        topic=f"{t['label']} — {user} ({user.id})")
    info = {
        "owner": user.id, "claimed": None, "type": t["label"], "role": t.get("role"),
        "reason": reason, "priority": "normal",
        "opened": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    c["tickets"][str(channel.id)] = info
    save_data()

    content, e, f = build_inside(guild, user, channel, info)
    msg = await channel.send(content=content, embed=e, file=f, view=TicketControls(guild.id))
    info["msg"] = msg.id
    save_data()
    try:
        await msg.pin()
    except discord.HTTPException:
        pass
    await interaction.followup.send(f"✅ تم فتح تذكرتك: {channel.mention}", ephemeral=True)

    le = embed("🎫 تذكرة جديدة", color=0x55FF88)
    le.add_field(name="التذكرة", value=channel.mention)
    le.add_field(name="النوع", value=t["label"])
    le.add_field(name="صاحبها", value=user.mention)
    le.add_field(name="السبب", value=reason[:300], inline=False)
    await ticket_log(guild, le)

class ReasonModal(discord.ui.Modal):
    def __init__(self, key: str):
        super().__init__(title="سبب التذكرة")
        self.key = key
        self.reason = discord.ui.TextInput(label="اكتب سبب فتح التذكرة",
                                           style=discord.TextStyle.paragraph,
                                           max_length=1000, required=True)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await open_ticket(interaction, self.key, str(self.reason))

class TicketButton(discord.ui.DynamicItem[discord.ui.Button], template=r"taqat:tk:(?P<key>[0-9]+)"):
    """زر فتح تذكرة — كل نوع تذكرة له زر، ويشتغل حتى بعد إعادة تشغيل البوت."""

    def __init__(self, key: str, label: str = None, emoji: str = None,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style,
                                           custom_id=f"taqat:tk:{key}"))
        self.key = key

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["key"])

    async def callback(self, interaction: discord.Interaction):
        guild, user = interaction.guild, interaction.user
        c = conf(guild.id)
        t = c["ticket"]["types"].get(self.key)
        if not t:
            return await interaction.response.send_message("❌ هذا النوع انحذف.", ephemeral=True)

        if user.id in c["ticket"]["blacklist"]:
            return await interaction.response.send_message(
                "❌ أنت ممنوع من فتح التذاكر.", ephemeral=True)

        mine = [cid for cid, i in c["tickets"].items()
                if i["owner"] == user.id and guild.get_channel(int(cid))]
        if len(mine) >= c["ticket"]["max"]:
            return await interaction.response.send_message(
                f"❌ عندك تذكرة مفتوحة: <#{mine[0]}>", ephemeral=True)

        if c["inside"]["ask_reason"]:
            return await interaction.response.send_modal(ReasonModal(self.key))
        await open_ticket(interaction, self.key, "لم يُذكر سبب")

# ---------- دوال مشتركة بين الأزرار والأوامر
async def claim_ticket(channel, user: discord.Member, info: dict) -> str | None:
    if info.get("claimed"):
        return f"مستلمها <@{info['claimed']}>"
    info["claimed"] = user.id
    save_data()
    await channel.send(embed=embed(None, f"تم استلام التذكرة من قبل {user.mention} ✅", 0x3DDC84))
    await refresh_controls(channel, info)
    le = embed("🙋 استلام تذكرة", color=0xFFAA00)
    le.add_field(name="التذكرة", value=channel.mention)
    le.add_field(name="المستلم", value=user.mention)
    await ticket_log(channel.guild, le)
    return None

async def unclaim_ticket(channel, user: discord.Member, info: dict):
    info["claimed"] = None
    save_data()
    await channel.send(embed=embed("↩️ إلغاء الاستلام", f"{user.mention} حرر التذكرة."))
    await refresh_controls(channel, info)

async def refresh_controls(channel, info: dict):
    """يحدّث رسالة التحكم (الأزرار + المحتوى) بعد استلام / تحويل."""
    guild = channel.guild
    msg = None
    try:
        if info.get("msg"):
            msg = await channel.fetch_message(info["msg"])
        else:
            async for m in channel.history(limit=50, oldest_first=True):
                if m.author.id == guild.me.id and m.components:
                    msg = m
                    info["msg"] = m.id
                    save_data()
                    break
    except discord.HTTPException:
        return
    if not msg:
        return
    claimed = bool(info.get("claimed"))
    owner = guild.get_member(info["owner"])
    try:
        if owner:
            content, e, f = build_inside(guild, owner, channel, info)
            kw = {"content": content, "embed": e, "view": TicketControls(guild.id, claimed)}
            if f:
                kw["attachments"] = [f]
            await msg.edit(**kw)
        else:
            await msg.edit(view=TicketControls(guild.id, claimed))
    except discord.HTTPException:
        pass

async def set_priority(channel, info: dict, level: str):
    emoji, name = PRIORITIES[level]
    info["priority"] = level
    save_data()
    base = re.sub(r"^(?:🟢|🟡|🟠|🔴)-", "", channel.name)
    new = base if level == "normal" else f"{emoji}-{base}"
    try:
        await channel.edit(name=new)
    except discord.HTTPException:
        pass
    await channel.send(embed=embed("🚦 أولوية التذكرة", f"{emoji} **{name}**"))
    return emoji, name

async def set_lock(channel, info: dict, locked: bool):
    owner = channel.guild.get_member(info["owner"])
    if owner:
        await channel.set_permissions(owner, view_channel=True, read_message_history=True,
                                      attach_files=not locked,
                                      send_messages=False if locked else True)
    await channel.send(embed=embed("🔒 تم قفل التذكرة" if locked else "🔓 تم فتح التذكرة",
                                   "صاحب التذكرة ما يقدر يكتب." if locked else "صاحب التذكرة يقدر يكتب."))

def info_embed(channel, info: dict) -> discord.Embed:
    emoji, pname = PRIORITIES.get(info.get("priority", "normal"), PRIORITIES["normal"])
    e = embed("ℹ️ معلومات التذكرة")
    e.add_field(name="التذكرة", value=channel.mention)
    e.add_field(name="النوع", value=info.get("type", "—"))
    e.add_field(name="صاحبها", value=f"<@{info['owner']}>")
    e.add_field(name="المستلم", value=f"<@{info['claimed']}>" if info.get("claimed") else "لا أحد")
    e.add_field(name="الأولوية", value=f"{emoji} {pname}")
    e.add_field(name="فُتحت", value=discord.utils.format_dt(datetime.datetime.fromisoformat(info["opened"]), "R"))
    e.add_field(name="السبب", value=(info.get("reason") or "—")[:500], inline=False)
    return e

# ---------- المودالات والقوائم (إجراءات أخرى)
class RenameModal(discord.ui.Modal, title="إعادة تسمية التذكرة"):
    name = discord.ui.TextInput(label="الاسم الجديد", max_length=90)

    async def on_submit(self, interaction: discord.Interaction):
        new = re.sub(r"\s+", "-", str(self.name).strip().lower())
        try:
            await interaction.channel.edit(name=new)
        except discord.HTTPException:
            return await interaction.response.send_message("❌ ما قدرت أغيّر الاسم.", ephemeral=True)
        await interaction.response.send_message(embed=embed("✏️ تمت إعادة التسمية", new))

class NoteModal(discord.ui.Modal, title="ملاحظة داخلية للفريق"):
    note = discord.ui.TextInput(label="الملاحظة (تنرسل للوق فقط)",
                                style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        le = embed("🗒️ ملاحظة على تذكرة", str(self.note), 0x8888FF)
        le.add_field(name="التذكرة", value=interaction.channel.mention)
        le.add_field(name="بواسطة", value=interaction.user.mention)
        await ticket_log(interaction.guild, le)
        await interaction.response.send_message("✅ انحفظت الملاحظة في اللوق.", ephemeral=True)

class CloseModal(discord.ui.Modal, title="إغلاق التذكرة"):
    reason = discord.ui.TextInput(label="سبب الإغلاق", style=discord.TextStyle.paragraph,
                                  max_length=300, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 جاري الإغلاق وحفظ السجل...")
        await close_ticket(interaction.channel, interaction.user, str(self.reason) or None)

class PriorityView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(placeholder="اختر الأولوية", options=[
        discord.SelectOption(label=name, value=k, emoji=emoji)
        for k, (emoji, name) in PRIORITIES.items()])
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.edit_message(content="❌ هذي مو تذكرة.", view=None)
        await interaction.response.edit_message(content="✅ تم تحديث الأولوية.", view=None)
        await set_priority(interaction.channel, info, select.values[0])

class PickUserView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=120)
        self.action = action

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="اختر العضو")
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        member = select.values[0]
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.edit_message(content="❌ العضو مو بالسيرفر.", view=None)
        ch = interaction.channel
        info = conf(interaction.guild.id)["tickets"].get(str(ch.id))
        if not info:
            return await interaction.response.edit_message(content="❌ هذي مو تذكرة.", view=None)

        if self.action == "add":
            await ch.set_permissions(member, view_channel=True, send_messages=True,
                                     attach_files=True, read_message_history=True)
            note = embed("➕ تمت الإضافة", member.mention)
        elif self.action == "remove":
            if member.id == info["owner"]:
                return await interaction.response.edit_message(content="❌ ما تقدر تشيل صاحب التذكرة.", view=None)
            await ch.set_permissions(member, overwrite=None)
            note = embed("➖ تمت الإزالة", member.mention)
        else:  # transfer
            if not is_staff(member, info):
                return await interaction.response.edit_message(content="❌ هذا العضو مو من الفريق.", view=None)
            info["claimed"] = member.id
            save_data()
            note = embed("🔁 تحويل الاستلام", f"{member.mention} صار هو المستلم.")
        await interaction.response.edit_message(content="✅ تم.", view=None)
        await ch.send(embed=note)

class ScheduleModal(discord.ui.Modal, title="إغلاق مجدول"):
    when = discord.ui.TextInput(label="بعد كم؟ مثال: 30m أو 2h أو 1d (0 للإلغاء)", max_length=10)
    reason = discord.ui.TextInput(label="السبب (اختياري)", style=discord.TextStyle.paragraph,
                                  max_length=200, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.send_message("❌ هذي مو تذكرة.", ephemeral=True)
        val = str(self.when).strip().lower()
        if val in ("0", "الغاء", "إلغاء", "cancel"):
            if not info.get("close_at"):
                return await interaction.response.send_message("❌ ما فيه إغلاق مجدول.", ephemeral=True)
            for k in ("close_at", "close_reason", "close_by"):
                info.pop(k, None)
            save_data()
            return await interaction.response.send_message(
                embed=embed("✅ تم إلغاء الإغلاق المجدول", f"بواسطة {interaction.user.mention}", 0x3DDC84))
        mins = parse_duration(val)
        if mins is None or not 1 <= mins <= 10080:
            return await interaction.response.send_message(
                "❌ مدة غير صحيحة. أمثلة: `30m` `2h` `1d` (حد أقصى 7 أيام).", ephemeral=True)
        at = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
        info["close_at"] = at.isoformat()
        info["close_reason"] = str(self.reason) or None
        info["close_by"] = interaction.user.id
        save_data()
        e = embed("⏰ إغلاق مجدول", f"راح تنغلق هذي التذكرة {discord.utils.format_dt(at, 'R')}", 0xFFAA00)
        e.add_field(name="بواسطة", value=interaction.user.mention)
        if info["close_reason"]:
            e.add_field(name="السبب", value=info["close_reason"], inline=False)
        e.set_footer(text="لإلغائه: إجراءات أخرى ← إغلاق مجدول ← اكتب 0")
        await interaction.response.send_message(embed=e)

class MoveView(discord.ui.View):
    """اختيار القسم الجديد لتحويل التذكرة."""
    def __init__(self, guild: discord.Guild, current_label: str):
        super().__init__(timeout=120)
        types = conf(guild.id)["ticket"]["types"]
        options = [discord.SelectOption(label=t["label"][:100], value=k, emoji=t.get("emoji") or None)
                   for k, t in types.items() if t["label"] != current_label][:25]
        self.select = discord.ui.Select(placeholder="🔀 اختر القسم الجديد", options=options)
        self.select.callback = self.on_pick
        self.add_item(self.select)

    async def on_pick(self, interaction: discord.Interaction):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.edit_message(content="❌ هذي مو تذكرة.", view=None)
        await interaction.response.edit_message(content="✅ جاري التحويل...", view=None)
        await move_ticket(interaction.channel, info, self.select.values[0], interaction.user)

STAFF_OPTS = [
    ("add", "إضافة عضو", "➕", "إضافة شخص للتذكرة"),
    ("remove", "إزالة عضو", "➖", "إزالة شخص من التذكرة"),
    ("rename", "إعادة تسمية", "✏️", "تغيير اسم روم التذكرة"),
    ("schedule", "إغلاق مجدول", "⏰", "إغلاق التذكرة بعد مدة"),
    ("ping_owner", "تذكير", "🔔", "منشن + رسالة خاصة لصاحب التذكرة"),
    ("move", "تحويل التذكرة", "🔀", "نقل التذكرة لقسم ثاني"),
    ("transfer", "تحويل الاستلام", "🔁", "تحويل التذكرة لعضو من الفريق"),
    ("unclaim", "إلغاء الاستلام", "↩️", "تحرير التذكرة ليستلمها غيرك"),
    ("priority", "تغيير الأولوية", "🚦", "منخفضة / عادية / عالية / عاجلة"),
    ("lock", "قفل الكتابة", "🔒", "منع صاحب التذكرة من الكتابة"),
    ("unlock", "فتح الكتابة", "🔓", "السماح لصاحب التذكرة بالكتابة"),
    ("note", "ملاحظة داخلية", "🗒️", "تنحفظ في اللوق فقط"),
    ("transcript", "سجل المحادثة", "📜", "ملف نصي بكل الرسائل"),
    ("info", "معلومات التذكرة", "ℹ️", "تفاصيل التذكرة"),
    ("close_reason", "إغلاق مع سبب", "🔐", "يوصل السبب لصاحب التذكرة"),
]
OWNER_OPTS = [
    ("ping_staff", "استدعاء الفريق", "🔔", "منشن لرتبة الدعم"),
    ("transcript", "سجل المحادثة", "📜", "ملف نصي بكل الرسائل"),
    ("info", "معلومات التذكرة", "ℹ️", "تفاصيل التذكرة"),
    ("close_reason", "إغلاق مع سبب", "🔐", "إغلاق التذكرة"),
]
OWNER_ALLOWED = {o[0] for o in OWNER_OPTS}

async def handle_action(interaction: discord.Interaction, action: str):
    guild, ch, user = interaction.guild, interaction.channel, interaction.user
    info = conf(guild.id)["tickets"].get(str(ch.id))
    if not info:
        return await interaction.response.edit_message(content="❌ هذي مو تذكرة.", view=None)
    staff = is_staff(user, info)
    if not staff and not (user.id == info["owner"] and action in OWNER_ALLOWED):
        return await interaction.response.edit_message(content="❌ ما عندك صلاحية.", view=None)

    if action in ("add", "remove", "transfer"):
        return await interaction.response.edit_message(content="👤 اختر العضو:", view=PickUserView(action))
    if action == "rename":
        return await interaction.response.send_modal(RenameModal())
    if action == "note":
        return await interaction.response.send_modal(NoteModal())
    if action == "close_reason":
        return await interaction.response.send_modal(CloseModal())
    if action == "priority":
        return await interaction.response.edit_message(content="🚦 اختر الأولوية:", view=PriorityView())
    if action == "schedule":
        return await interaction.response.send_modal(ScheduleModal())
    if action == "move":
        others = [t for t in conf(guild.id)["ticket"]["types"].values() if t["label"] != info.get("type")]
        if not others:
            return await interaction.response.edit_message(content="❌ ما فيه أقسام ثانية للتحويل.", view=None)
        return await interaction.response.edit_message(
            content="🔀 اختر القسم الجديد:", view=MoveView(guild, info.get("type")))

    if action in ("lock", "unlock"):
        await interaction.response.edit_message(content="✅ تم.", view=None)
        return await set_lock(ch, info, action == "lock")
    if action == "unclaim":
        if not info.get("claimed"):
            return await interaction.response.edit_message(content="❌ التذكرة مو مستلمة.", view=None)
        await interaction.response.edit_message(content="✅ تم.", view=None)
        return await unclaim_ticket(ch, user, info)
    if action == "ping_owner":
        await interaction.response.edit_message(content="✅ تم التنبيه.", view=None)
        await ch.send(f"🔔 <@{info['owner']}> الفريق ينتظر ردك هنا.")
        owner = guild.get_member(info["owner"])
        if owner:
            try:
                await owner.send(f"🔔 فريق **{guild.name}** ينتظر ردك في تذكرتك: {ch.mention}")
            except discord.Forbidden:
                pass
        return
    if action == "ping_staff":
        role = guild.get_role(info["role"]) if info.get("role") else None
        await interaction.response.edit_message(content="✅ تم الاستدعاء.", view=None)
        return await ch.send(f"🔔 {role.mention if role else '@here'} صاحب التذكرة يحتاج مساعدة.",
                             allowed_mentions=discord.AllowedMentions(roles=True, everyone=True))
    if action == "transcript":
        await interaction.response.edit_message(content="📜 جاري التجهيز...", view=None)
        data = await build_transcript(ch)
        return await interaction.followup.send(
            file=discord.File(io.BytesIO(data), filename=f"{ch.name}.txt"), ephemeral=True)
    if action == "info":
        return await interaction.response.edit_message(content=None, embed=info_embed(ch, info), view=None)

class MoreView(discord.ui.View):
    """لوحة الإجراءات: أزرار بدل القائمة."""
    def __init__(self, staff: bool):
        super().__init__(timeout=120)
        for action, label, emoji, _ in (STAFF_OPTS if staff else OWNER_OPTS):
            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)
            b.callback = self._make(action)
            self.add_item(b)

    @staticmethod
    def _make(action: str):
        async def cb(interaction: discord.Interaction):
            await handle_action(interaction, action)
        return cb

class TicketControls(discord.ui.View):
    """أزرار لوحة التحكم داخل التذكرة — الاسم والإيموجي واللون قابلة للتخصيص (insidebtn)."""
    def __init__(self, guild_id: int = None, claimed: bool = False):
        super().__init__(timeout=None)
        saved = conf(guild_id)["inside"]["btn"] if guild_id else {}
        handlers = {"claim": self.on_claim, "close": self.on_close, "more": self.on_more}
        for k in ("claim", "close", "more"):
            d = {**DEFAULT_BTN[k], **saved.get(k, {})}
            if k == "claim" and claimed:
                d = {"label": "إلغاء الاستلام", "emoji": "↩️", "style": d.get("style", "gray")}
            b = discord.ui.Button(label=d["label"], emoji=d.get("emoji") or None,
                                  style=STYLES.get(d["style"], discord.ButtonStyle.secondary),
                                  custom_id=f"taqat:ticket_{k}")
            b.callback = handlers[k]
            self.add_item(b)

    async def on_claim(self, interaction: discord.Interaction):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.send_message("❌ هذي مو تذكرة.", ephemeral=True)
        if not is_staff(interaction.user, info):
            return await interaction.response.send_message("❌ للفريق فقط.", ephemeral=True)
        if info.get("claimed"):
            # الزر صار "إلغاء الاستلام": للمستلم أو لمن عنده إدارة السيرفر
            if info["claimed"] != interaction.user.id and not interaction.user.guild_permissions.manage_guild:
                return await interaction.response.send_message(
                    f"❌ مستلمها <@{info['claimed']}>", ephemeral=True)
            await interaction.response.defer()
            return await unclaim_ticket(interaction.channel, interaction.user, info)
        await interaction.response.defer()
        await claim_ticket(interaction.channel, interaction.user, info)

    async def on_close(self, interaction: discord.Interaction):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.send_message("❌ هذي مو تذكرة.", ephemeral=True)
        if interaction.user.id != info["owner"] and not is_staff(interaction.user, info):
            return await interaction.response.send_message("❌ ما تقدر تغلقها.", ephemeral=True)
        await interaction.response.send_message("🔒 جاري الإغلاق وحفظ السجل...")
        await close_ticket(interaction.channel, interaction.user)

    async def on_more(self, interaction: discord.Interaction):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.send_message("❌ هذي مو تذكرة.", ephemeral=True)
        staff = is_staff(interaction.user, info)
        if not staff and interaction.user.id != info["owner"]:
            return await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        await interaction.response.send_message("⚙️ اختر الإجراء المطلوب:", view=MoreView(staff), ephemeral=True)

# ---------- إغلاق تلقائي عند عدم النشاط
@tasks.loop(minutes=10)
async def autoclose_loop():
    now = datetime.datetime.now(datetime.timezone.utc)
    for guild in bot.guilds:
        c = conf(guild.id)
        hrs = c["ticket"]["autoclose"]
        for cid in list(c["tickets"]):
            ch = guild.get_channel(int(cid))
            if not ch:
                c["tickets"].pop(cid, None)
                save_data()
                continue
            if not hrs:
                continue
            last = discord.utils.snowflake_time(ch.last_message_id) if ch.last_message_id else ch.created_at
            if now - last > datetime.timedelta(hours=hrs):
                try:
                    await ch.send(embed=embed("⏰ إغلاق تلقائي", f"لا يوجد نشاط منذ {hrs} ساعة.", 0xFFAA00))
                    await close_ticket(ch, guild.me, f"إغلاق تلقائي لعدم النشاط ({hrs} ساعة)")
                except discord.HTTPException:
                    pass

@autoclose_loop.before_loop
async def _before_autoclose():
    await bot.wait_until_ready()

# ---------- إغلاق مجدول
@tasks.loop(seconds=30)
async def scheduled_close_loop():
    now = datetime.datetime.now(datetime.timezone.utc)
    for guild in bot.guilds:
        c = conf(guild.id)
        for cid, info in list(c["tickets"].items()):
            at = info.get("close_at")
            if not at:
                continue
            try:
                due = now >= datetime.datetime.fromisoformat(at)
            except ValueError:
                info.pop("close_at", None)
                continue
            if not due:
                continue
            ch = guild.get_channel(int(cid))
            if not ch:
                continue
            reason = info.pop("close_reason", None) or "إغلاق مجدول"
            closer = guild.get_member(info.pop("close_by", 0)) or guild.me
            info.pop("close_at", None)
            save_data()
            try:
                await ch.send(embed=embed("⏰ إغلاق مجدول", "حان وقت إغلاق التذكرة.", 0xFFAA00))
                await close_ticket(ch, closer, reason)
            except discord.HTTPException:
                pass

@scheduled_close_loop.before_loop
async def _before_scheduled_close():
    await bot.wait_until_ready()

# ---------- تحويل التذكرة لقسم ثاني
async def move_ticket(channel, info: dict, key: str, mover: discord.Member):
    guild = channel.guild
    c = conf(guild.id)
    t = c["ticket"]["types"].get(key)
    if not t:
        return await channel.send("❌ هذا القسم انحذف.")
    old_label = info.get("type", "—")
    old_t = next((x for x in c["ticket"]["types"].values() if x["label"] == old_label), {})
    old_role = guild.get_role(info["role"]) if info.get("role") else None
    new_role = guild.get_role(t["role"]) if t.get("role") else None
    category = guild.get_channel(t["category"]) if t.get("category") else None

    try:
        if old_role and old_role != new_role:
            await channel.set_permissions(old_role, overwrite=None)
        if new_role:
            await channel.set_permissions(new_role, view_channel=True, send_messages=True,
                                          attach_files=True, read_message_history=True)
        if category and channel.category_id != category.id:
            await channel.edit(category=category)
    except discord.HTTPException:
        return await channel.send(embed=embed("❌ تعذّر التحويل", "ما قدرت أعدّل الصلاحيات أو الكاتيجوري.", 0xFF5555))

    had_claim = bool(info.get("claimed"))
    info["type"] = t["label"]
    info["role"] = t.get("role")
    info["claimed"] = None
    save_data()

    def tag(x: dict, label: str) -> str:
        return f"{x.get('emoji') or '🎫'} {label}"

    e = fancy("🔀 تم تحويل التذكرة",
              f"تم نقل هذه التذكرة إلى قسم **{t['label']}** بواسطة {mover.mention}",
              C_INFO,
              footer="تم إلغاء الاستلام السابق تلقائياً" if had_claim else None)
    e.add_field(name="القسم السابق", value=tag(old_t, old_label), inline=False)
    e.add_field(name="القسم الجديد", value=tag(t, t["label"]), inline=False)
    await channel.send(content=new_role.mention if new_role else None, embed=e,
                       allowed_mentions=discord.AllowedMentions(roles=True))
    await refresh_controls(channel, info)

    le = embed("🔀 تحويل تذكرة", color=0x8888FF)
    le.add_field(name="التذكرة", value=channel.mention)
    le.add_field(name="من", value=old_label)
    le.add_field(name="إلى", value=t["label"])
    le.add_field(name="بواسطة", value=mover.mention)
    await ticket_log(guild, le)

# ---------- نقاط الدعم (تنحسب تلقائياً عند إغلاق التذكرة)
def _pts(guild_id: int, staff_id) -> dict:
    return conf(guild_id)["points"].setdefault(
        str(staff_id), {"points": 0, "closed": 0, "rating_sum": 0, "rating_count": 0})

def award_points(guild_id: int, staff_id, amount: int):
    p = _pts(guild_id, staff_id)
    p["points"] += amount
    p["closed"] += 1

def record_rating(guild_id: int, staff_id, stars: int):
    p = _pts(guild_id, staff_id)
    p["rating_sum"] += stars
    p["rating_count"] += 1
    save_data()

def points_order(guild_id: int):
    return sorted(conf(guild_id)["points"].items(), key=lambda kv: kv[1]["points"], reverse=True)

@bot.hybrid_command(name="points", aliases=["نقاطي", "نقاط"], description="نقاط الدعم الفني (تنحسب تلقائياً عند إغلاق التذاكر)")
@commands.guild_only()
async def points_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    p = conf(ctx.guild.id)["points"].get(str(member.id))
    e = fancy(f"🏆 نقاط {member.display_name}", color=0xFFD700)
    e.set_thumbnail(url=member.display_avatar.url)
    if not p:
        e.description = "ما عنده نقاط بعد — تنحسب تلقائياً لما يغلق تذكرة هو مستلمها."
        return await ctx.send(embed=e)
    order = points_order(ctx.guild.id)
    rank = next((i for i, (k, _) in enumerate(order, 1) if k == str(member.id)), len(order))
    e.add_field(name="⭐ النقاط", value=f"**{p['points']}**")
    e.add_field(name="🎫 تذاكر مغلقة", value=str(p["closed"]))
    e.add_field(name="🏅 الترتيب", value=f"#{rank} من {len(order)}")
    if p["rating_count"]:
        avg = p["rating_sum"] / p["rating_count"]
        e.add_field(name="⭐ متوسط التقييم", value=f"{avg:.1f} / 5  ({p['rating_count']} تقييم)")
    await ctx.send(embed=e)

@bot.hybrid_command(name="topstaff", aliases=["توب", "ترتيب_الدعم"], description="ترتيب أفضل أعضاء الدعم بالنقاط")
@commands.guild_only()
async def topstaff(ctx):
    order = points_order(ctx.guild.id)[:10]
    if not order:
        return await ctx.send(embed=fancy("🏆 ترتيب الدعم", "ما فيه نقاط بعد.", 0xFFD700))
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (k, v) in enumerate(order):
        mark = medals[i] if i < 3 else f"`#{i + 1}`"
        extra = ""
        if v["rating_count"]:
            extra = f" • ⭐ {v['rating_sum'] / v['rating_count']:.1f}"
        lines.append(f"{mark} <@{k}> — **{v['points']}** نقطة • {v['closed']} تذكرة{extra}")
    await ctx.send(embed=fancy("🏆 ترتيب الدعم", "\n".join(lines), 0xFFD700))

@bot.hybrid_command(name="pointsadmin", description="إضافة / خصم / تصفير نقاط عضو")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def pointsadmin(ctx, action: Literal["add", "remove", "reset"], member: discord.Member, amount: int = 1):
    pts = conf(ctx.guild.id)["points"]
    if action == "reset":
        pts.pop(str(member.id), None)
        txt = f"تم تصفير نقاط {member.mention}"
    else:
        if not 1 <= amount <= 10000:
            return await send_err(ctx, "الكمية من 1 إلى 10000.", "رقم غير صحيح")
        p = _pts(ctx.guild.id, member.id)
        p["points"] = p["points"] + amount if action == "add" else max(0, p["points"] - amount)
        txt = f"{member.mention} ← **{p['points']}** نقطة"
    save_data()
    await ctx.send(embed=ok_e("تم تحديث النقاط", txt))

@bot.hybrid_command(name="pointsvalue", description="كم نقطة ياخذ المستلم عند إغلاق كل تذكرة")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def pointsvalue(ctx, amount: int):
    if not 0 <= amount <= 100:
        return await send_err(ctx, "من 0 إلى 100 (0 = إيقاف النقاط).", "رقم غير صحيح")
    conf(ctx.guild.id)["ticket"]["point_value"] = amount
    save_data()
    await ctx.send(embed=ok_e("نقاط التذكرة", f"المستلم ياخذ **{amount}** نقطة عند إغلاق كل تذكرة."))

@bot.hybrid_command(name="pointsreset", description="تصفير نقاط كل الدعم")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def pointsreset(ctx):
    view = ConfirmView(ctx.author.id)
    msg = await ctx.send(embed=warn_e("تأكيد التصفير", "راح تنمسح نقاط **كل** أعضاء الدعم. ما ينفع التراجع!"), view=view)
    await view.wait()
    if not view.value:
        return await msg.edit(embed=err_e("تم الإلغاء.", "ملغي"), view=None)
    conf(ctx.guild.id)["points"].clear()
    save_data()
    await msg.edit(embed=ok_e("تم تصفير كل النقاط"), view=None)

# ---------- لوحة التذاكر (الرئيسية)
def panel_message(guild: discord.Guild):
    c = conf(guild.id)
    p, types = c["panel"], c["ticket"]["types"]
    lines = "\n".join(f"> **{t['label']}**" for t in types.values())
    desc = (lines + "\n\n" if lines else "") + p["desc"]
    e = discord.Embed(title=p["title"], description=desc, color=parse_color(p["color"]))
    if p["footer"]:
        e.set_footer(text=p["footer"])
    f = apply_image(e, p["image"], "ticket")
    view = discord.ui.View(timeout=None)
    for key, t in types.items():
        view.add_item(TicketButton(key, t["label"], t.get("emoji"), STYLES[t.get("style", "gray")]))
    return e, f, view

async def refresh_panel(guild: discord.Guild) -> bool:
    p = conf(guild.id)["panel"]
    ch = guild.get_channel(p["channel_id"]) if p["channel_id"] else None
    if not ch or not p["message_id"]:
        return False
    try:
        msg = await ch.fetch_message(p["message_id"])
        e, f, view = panel_message(guild)
        await msg.edit(embed=e, view=view, attachments=[f] if f else [])
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False

@bot.hybrid_command(name="ticketpanel", description="إرسال لوحة التذاكر في روم")
@commands.has_permissions(manage_guild=True)
async def ticketpanel(ctx, channel: discord.TextChannel, log_channel: discord.TextChannel = None):
    c = conf(ctx.guild.id)
    if not c["ticket"]["types"]:
        return await ctx.send(f"❌ أضف نوع تذكرة أول بـ `{PREFIX}ticketadd`.")
    if log_channel:
        c["ticket"]["log_channel"] = log_channel.id
    e, f, view = panel_message(ctx.guild)
    msg = await channel.send(embed=e, file=f, view=view)
    c["panel"]["channel_id"], c["panel"]["message_id"] = channel.id, msg.id
    save_data()
    await ctx.send(embed=embed("✅ تم إرسال اللوحة", channel.mention))

@bot.hybrid_command(name="panelset", description="تعديل لوحة التذاكر")
@commands.has_permissions(manage_guild=True)
async def panelset(ctx, item: Literal["title", "desc", "footer", "color", "ticketmsg"], *, value: str):
    """title=العنوان | desc=الشرح | footer=النص تحت الصورة | color=اللون | ticketmsg=رسالة داخل التذكرة"""
    p = conf(ctx.guild.id)["panel"]
    if item == "color":
        if not valid_color(value):
            return await ctx.send("❌ اللون لازم يكون HEX مثل `2B2D31`.")
        p["color"] = value.strip().lstrip("#")
    else:
        p[item] = nl(value)
    save_data()
    done = await refresh_panel(ctx.guild)
    await ctx.send(embed=embed("✅ تم الحفظ", f"**{item}** ← {value}" + ("\nوتحدّثت اللوحة." if done else "")))

@bot.hybrid_command(name="panelimage", description="تغيير صورة لوحة التذاكر (صورة مرفقة أو رابط)")
@commands.has_permissions(manage_guild=True)
async def panelimage(ctx, image: discord.Attachment = None, url: str = None):
    try:
        conf(ctx.guild.id)["panel"]["image"] = await store_image(ctx.guild.id, "ticket", image, url)
    except ValueError as err:
        return await ctx.send(f"❌ {err}")
    save_data()
    done = await refresh_panel(ctx.guild)
    await ctx.send(embed=embed("✅ تم تغيير الصورة", "وتحدّثت اللوحة." if done else f"أرسل اللوحة بـ `{PREFIX}ticketpanel`"))

@bot.hybrid_command(name="ticketadd", description="إضافة زر/نوع تذكرة")
@commands.has_permissions(manage_guild=True)
async def ticketadd(ctx, label: str, emoji: str = None, category: discord.CategoryChannel = None,
                    role: discord.Role = None, style: Literal["gray", "blue", "green", "red"] = "gray"):
    """label=اسم الزر | emoji=إيموجي (عادي أو مخصص) | category=كاتيجوري التذاكر | role=رتبة الدعم | style=لون الزر"""
    c = conf(ctx.guild.id)
    if len(c["ticket"]["types"]) >= 25:
        return await ctx.send("❌ الحد الأقصى 25 زر.")
    if emoji:
        pe = discord.PartialEmoji.from_str(emoji)
        if not pe.is_custom_emoji() and not pe.name:
            return await ctx.send("❌ إيموجي غير صحيح.")
    c["ticket"]["type_counter"] += 1
    key = str(c["ticket"]["type_counter"])
    c["ticket"]["types"][key] = {
        "label": label, "emoji": emoji, "style": style,
        "category": category.id if category else None, "role": role.id if role else None}
    save_data()
    done = await refresh_panel(ctx.guild)
    await ctx.send(embed=embed("✅ تمت إضافة الزر", f"{emoji or ''} **{label}**" + ("\nوتحدّثت اللوحة." if done else "")))

@bot.hybrid_command(name="ticketdel", description="حذف زر/نوع تذكرة")
@commands.has_permissions(manage_guild=True)
async def ticketdel(ctx, label: str):
    types = conf(ctx.guild.id)["ticket"]["types"]
    key = next((k for k, t in types.items() if t["label"].lower() == label.lower()), None)
    if not key:
        return await ctx.send("❌ ما لقيت هذا الزر.")
    types.pop(key)
    save_data()
    await refresh_panel(ctx.guild)
    await ctx.send(embed=embed("🗑️ تم الحذف", label))

@bot.hybrid_command(name="ticketlist", description="عرض أنواع التذاكر")
@commands.has_permissions(manage_guild=True)
async def ticketlist(ctx):
    types = conf(ctx.guild.id)["ticket"]["types"]
    if not types:
        return await ctx.send("ما فيه أزرار. أضف بـ `ticketadd`.")
    lines = [f"{t.get('emoji') or '🎫'} **{t['label']}** — "
             f"{('<#%s>' % t['category']) if t.get('category') else 'بدون كاتيجوري'} / "
             f"{('<@&%s>' % t['role']) if t.get('role') else 'بدون رتبة'}"
             for t in types.values()]
    await ctx.send(embed=embed("🎫 أنواع التذاكر", "\n".join(lines)))

@bot.hybrid_command(name="ticketlog", description="تحديد روم لوق التذاكر")
@commands.has_permissions(manage_guild=True)
async def ticketlog(ctx, channel: discord.TextChannel):
    conf(ctx.guild.id)["ticket"]["log_channel"] = channel.id
    save_data()
    await ctx.send(embed=embed("✅ لوق التذاكر", channel.mention))

@bot.hybrid_command(name="tadd", description="إضافة عضو للتذكرة")
async def tadd(ctx, member: discord.Member):
    info = conf(ctx.guild.id)["tickets"].get(str(ctx.channel.id))
    if not info:
        return await ctx.send("❌ هذا مو روم تذكرة.")
    if not is_staff(ctx.author, info):
        return await ctx.send("❌ للفريق فقط.")
    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True,
                                      read_message_history=True)
    await ctx.send(embed=embed("➕ تمت الإضافة", member.mention))

@bot.hybrid_command(name="tremove", description="إزالة عضو من التذكرة")
async def tremove(ctx, member: discord.Member):
    info = conf(ctx.guild.id)["tickets"].get(str(ctx.channel.id))
    if not info:
        return await ctx.send("❌ هذا مو روم تذكرة.")
    if not is_staff(ctx.author, info):
        return await ctx.send("❌ للفريق فقط.")
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.send(embed=embed("➖ تمت الإزالة", member.mention))

@bot.hybrid_command(name="tclose", description="إغلاق التذكرة الحالية")
async def tclose(ctx, *, reason: str = None):
    info = conf(ctx.guild.id)["tickets"].get(str(ctx.channel.id))
    if not info:
        return await ctx.send("❌ هذا مو روم تذكرة.")
    if ctx.author.id != info["owner"] and not is_staff(ctx.author, info):
        return await ctx.send("❌ ما تقدر تغلقها.")
    await ctx.send("🔒 جاري الإغلاق وحفظ السجل...")
    await close_ticket(ctx.channel, ctx.author, reason)

# ---------- أوامر تذاكر إضافية
async def get_ticket(ctx, staff: bool = True):
    info = conf(ctx.guild.id)["tickets"].get(str(ctx.channel.id))
    if not info:
        await ctx.send("❌ هذا مو روم تذكرة.")
        return None
    if staff and not is_staff(ctx.author, info):
        await ctx.send("❌ للفريق فقط.")
        return None
    return info

@bot.hybrid_command(name="tclaim", description="استلام التذكرة")
async def tclaim(ctx):
    info = await get_ticket(ctx)
    if not info:
        return
    err = await claim_ticket(ctx.channel, ctx.author, info)
    if err:
        await ctx.send(f"❌ {err}")
    elif ctx.interaction:
        await ctx.send("✅", ephemeral=True)

@bot.hybrid_command(name="tunclaim", description="إلغاء استلام التذكرة")
async def tunclaim(ctx):
    info = await get_ticket(ctx)
    if not info:
        return
    if not info.get("claimed"):
        return await ctx.send("❌ التذكرة مو مستلمة.")
    await unclaim_ticket(ctx.channel, ctx.author, info)
    if ctx.interaction:
        await ctx.send("✅", ephemeral=True)

@bot.hybrid_command(name="trename", description="إعادة تسمية التذكرة")
async def trename(ctx, *, name: str):
    if not await get_ticket(ctx):
        return
    new = re.sub(r"\s+", "-", name.strip().lower())
    try:
        await ctx.channel.edit(name=new)
    except discord.HTTPException:
        return await ctx.send("❌ ما قدرت أغيّر الاسم (ممكن حد الطلبات).")
    await ctx.send(embed=embed("✏️ تمت إعادة التسمية", new))

@bot.hybrid_command(name="tpriority", description="تغيير أولوية التذكرة")
async def tpriority(ctx, level: Literal["low", "normal", "high", "urgent"]):
    info = await get_ticket(ctx)
    if info:
        await set_priority(ctx.channel, info, level)

@bot.hybrid_command(name="tlock", description="منع صاحب التذكرة من الكتابة")
async def tlock(ctx):
    info = await get_ticket(ctx)
    if info:
        await set_lock(ctx.channel, info, True)

@bot.hybrid_command(name="tunlock", description="السماح لصاحب التذكرة بالكتابة")
async def tunlock(ctx):
    info = await get_ticket(ctx)
    if info:
        await set_lock(ctx.channel, info, False)

@bot.hybrid_command(name="ttranscript", description="سجل محادثة التذكرة كملف")
async def ttranscript(ctx):
    if not await get_ticket(ctx):
        return
    data = await build_transcript(ctx.channel)
    await ctx.send(file=discord.File(io.BytesIO(data), filename=f"{ctx.channel.name}.txt"))

@bot.hybrid_command(name="tblacklist", description="منع/سماح عضو بفتح التذاكر")
@commands.has_permissions(manage_guild=True)
async def tblacklist(ctx, action: Literal["add", "remove", "list"], member: discord.Member = None):
    bl = conf(ctx.guild.id)["ticket"]["blacklist"]
    if action == "list":
        txt = "\n".join(f"<@{i}>" for i in bl) or "فاضية."
        return await ctx.send(embed=embed("🚫 الممنوعين من التذاكر", txt))
    if not member:
        return await ctx.send("❌ حدد العضو.")
    if action == "add":
        if member.id not in bl:
            bl.append(member.id)
    elif member.id in bl:
        bl.remove(member.id)
    save_data()
    await ctx.send(embed=embed("✅ تم", f"{member.mention} — {'ممنوع' if action == 'add' else 'مسموح'}"))

@bot.hybrid_command(name="tmax", description="أقصى عدد تذاكر مفتوحة للعضو الواحد")
@commands.has_permissions(manage_guild=True)
async def tmax(ctx, amount: int):
    if not 1 <= amount <= 10:
        return await ctx.send("❌ من 1 إلى 10.")
    conf(ctx.guild.id)["ticket"]["max"] = amount
    save_data()
    await ctx.send(embed=embed("✅ تم", f"الحد الأقصى: **{amount}**"))

@bot.hybrid_command(name="tautoclose", description="إغلاق تلقائي بعد عدد ساعات بدون نشاط (0 للإيقاف)")
@commands.has_permissions(manage_guild=True)
async def tautoclose(ctx, hours: int):
    if not 0 <= hours <= 720:
        return await ctx.send("❌ من 0 إلى 720 ساعة.")
    conf(ctx.guild.id)["ticket"]["autoclose"] = hours
    save_data()
    await ctx.send(embed=embed("✅ تم", f"**{hours}** ساعة" if hours else "الإغلاق التلقائي متوقف"))

@bot.hybrid_command(name="tstats", description="إحصائيات التذاكر")
@commands.has_permissions(manage_channels=True)
async def tstats(ctx):
    c = conf(ctx.guild.id)
    tk = c["tickets"]
    claimed = sum(1 for i in tk.values() if i.get("claimed"))
    e = embed("📊 إحصائيات التذاكر")
    e.add_field(name="المفتوحة الآن", value=len(tk))
    e.add_field(name="المستلمة", value=claimed)
    e.add_field(name="غير مستلمة", value=len(tk) - claimed)
    e.add_field(name="إجمالي ما انفتح", value=c["ticket"]["counter"])
    e.add_field(name="الأنواع", value=len(c["ticket"]["types"]))
    e.add_field(name="الممنوعين", value=len(c["ticket"]["blacklist"]))
    await ctx.send(embed=e)

# ---------------------------------------------------------------- تخصيص لوحة التحكم داخل التذكرة
def _none(v: str) -> bool:
    return v.strip().lower() in ("none", "no", "-", "لا", "بدون")

@bot.hybrid_command(name="insideset", description="تعديل رسالة التحكم داخل التذكرة")
@commands.has_permissions(manage_guild=True)
async def insideset(ctx, item: Literal["content", "author", "authoricon", "desc", "footer", "color"], *, value: str):
    """content=الرسالة فوق | author=الاسم فوق | authoricon=رابط أيقونة الاسم | desc=الوصف | footer=الفوتر | color=اللون
    المتغيرات: {user} {name} {server} {date} {reason} {type} {ticket} {support} {claimed} — اكتب none للحذف"""
    ins = conf(ctx.guild.id)["inside"]
    if item == "color":
        if not valid_color(value):
            return await ctx.send("❌ اللون لازم يكون HEX مثل `2B2D31`.")
        ins["color"] = value.strip().lstrip("#")
    elif item == "authoricon":
        if _none(value):
            ins["author_icon"] = None
        elif value.startswith("http"):
            ins["author_icon"] = value.strip()
        else:
            return await ctx.send("❌ لازم رابط يبدأ بـ http.")
    else:
        ins[item] = "" if _none(value) and item != "desc" else nl(value)
    save_data()
    await ctx.send(embed=embed("✅ تم الحفظ", f"**{item}** ← {value[:500]}\nجرّب `{PREFIX}insidepreview`"))

@bot.hybrid_command(name="insideimage", description="تغيير صورة رسالة التحكم داخل التذكرة (مرفق أو رابط)")
@commands.has_permissions(manage_guild=True)
async def insideimage(ctx, image: discord.Attachment = None, url: str = None):
    try:
        conf(ctx.guild.id)["inside"]["image"] = await store_image(ctx.guild.id, "inside", image, url)
    except ValueError as err:
        return await ctx.send(f"❌ {err}")
    save_data()
    await ctx.send(embed=embed("✅ تم تغيير الصورة", f"جرّب `{PREFIX}insidepreview`"))

@bot.hybrid_command(name="insideimageoff", description="إزالة صورة رسالة التحكم داخل التذكرة")
@commands.has_permissions(manage_guild=True)
async def insideimageoff(ctx):
    conf(ctx.guild.id)["inside"]["image"] = None
    save_data()
    await ctx.send(embed=embed("✅ تمت إزالة الصورة"))

@bot.hybrid_command(name="insidethumb", description="إظهار/إخفاء صورة صاحب التذكرة الصغيرة")
@commands.has_permissions(manage_guild=True)
async def insidethumb(ctx, enabled: bool):
    conf(ctx.guild.id)["inside"]["thumb"] = enabled
    save_data()
    await ctx.send(embed=embed("✅ تم", "تظهر" if enabled else "مخفية"))

@bot.hybrid_command(name="insidereason", description="تفعيل/إيقاف سؤال سبب التذكرة عند الفتح")
@commands.has_permissions(manage_guild=True)
async def insidereason(ctx, enabled: bool):
    conf(ctx.guild.id)["inside"]["ask_reason"] = enabled
    save_data()
    await ctx.send(embed=embed("✅ تم", "راح يطلع نموذج السبب" if enabled else "بدون نموذج"))

@bot.hybrid_command(name="insidebtn", description="تخصيص أزرار التحكم (الاسم/الإيموجي/اللون)")
@commands.has_permissions(manage_guild=True)
async def insidebtn(ctx, button: Literal["claim", "close", "more"], label: str, emoji: str = None,
                    style: Literal["gray", "blue", "green", "red"] = "gray"):
    """button=claim/close/more | label=الاسم | emoji=إيموجي (عادي أو مخصص) | style=اللون"""
    if emoji:
        pe = discord.PartialEmoji.from_str(emoji)
        if not pe.is_custom_emoji() and not pe.name:
            return await ctx.send("❌ إيموجي غير صحيح.")
    conf(ctx.guild.id)["inside"]["btn"][button] = {"label": label, "emoji": emoji, "style": style}
    save_data()
    await ctx.send(embed=embed("✅ تم", f"{emoji or ''} **{label}**\nيطبق على التذاكر الجديدة • جرّب `{PREFIX}insidepreview`"))

@bot.hybrid_command(name="insidepreview", description="معاينة رسالة التحكم داخل التذكرة")
@commands.has_permissions(manage_guild=True)
async def insidepreview(ctx):
    info = {"owner": ctx.author.id, "claimed": None, "type": "معاينة", "role": None,
            "reason": "هذا سبب تجريبي", "priority": "normal",
            "opened": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    content, e, f = build_inside(ctx.guild, ctx.author, ctx.channel, info)
    await ctx.send(content=content, embed=e, file=f, view=TicketControls(ctx.guild.id))

# ---------------------------------------------------------------- الحماية: روم القوانين
@bot.hybrid_command(name="rulesguard", description="عقوبة لأي أحد يكتب في روم القوانين")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def rulesguard(ctx, channel: discord.TextChannel,
                     action: Literal["delete", "warn", "mute", "kick", "ban"] = "ban"):
    r = conf(ctx.guild.id)["rules"]
    r["channel"], r["action"] = channel.id, action
    save_data()
    e = ok_e("تم تفعيل حماية روم القوانين")
    e.add_field(name="💬 الروم", value=channel.mention)
    e.add_field(name="⚖️ العقوبة", value=f"**{action}**")
    e.add_field(name="ℹ️ ملاحظة", value="الأدمن والرتب المستثناة ما تنطبق عليهم.", inline=False)
    await ctx.send(embed=e)

@bot.hybrid_command(name="rulesoff", description="إيقاف حماية روم القوانين")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def rulesoff(ctx):
    conf(ctx.guild.id)["rules"]["channel"] = None
    save_data()
    await ctx.send(embed=ok_e("تم إيقاف حماية روم القوانين"))

@bot.hybrid_command(name="rulesexempt", description="استثناء/إلغاء استثناء رتبة من حماية القوانين")
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def rulesexempt(ctx, role: discord.Role):
    ex = conf(ctx.guild.id)["rules"]["exempt"]
    if role.id in ex:
        ex.remove(role.id)
        txt = f"{role.mention} ← انشالت من الاستثناء"
    else:
        ex.append(role.id)
        txt = f"{role.mention} ← مستثناة"
    save_data()
    await ctx.send(embed=ok_e("تم تحديث الاستثناءات", txt))

@bot.listen("on_message")
async def rules_guard(message: discord.Message):
    if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
        return
    r = conf(message.guild.id)["rules"]
    if not r["channel"] or message.channel.id != r["channel"]:
        return
    m = message.author
    if m.guild_permissions.administrator or m.id == message.guild.owner_id:
        return
    if any(role.id in r["exempt"] for role in m.roles):
        return
    try:
        await message.delete()
    except discord.HTTPException:
        pass
    action, reason = r["action"], "الكتابة في روم القوانين"
    try:
        if action == "warn":
            lst = conf(message.guild.id)["warns"].setdefault(str(m.id), [])
            lst.append({"reason": reason, "mod": bot.user.id,
                        "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
            save_data()
        elif action == "mute":
            await m.timeout(datetime.timedelta(days=1), reason=reason)
        elif action == "kick":
            await m.kick(reason=reason)
        elif action == "ban":
            await m.ban(reason=reason, delete_message_days=0)
    except discord.HTTPException:
        pass
    e = fancy("🔰 حماية القوانين", color=C_ERR)
    e.add_field(name="👤 العضو", value=f"{m.mention} (`{m.id}`)")
    e.add_field(name="⚖️ العقوبة", value=action)
    e.add_field(name="💬 الرسالة", value=(message.content or "—")[:500], inline=False)
    await modlog(message.guild, e)

# ---------------------------------------------------------------- الحماية: روابط / كلمات ممنوعة
@bot.hybrid_command(name="antilink", description="منع الروابط لغير الإدارة")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def antilink(ctx, enabled: bool):
    conf(ctx.guild.id)["automod"]["antilink"] = enabled
    save_data()
    await ctx.send(embed=ok_e("منع الروابط", "🟢 **مفعّل**" if enabled else "🔴 **متوقف**"))

@bot.hybrid_command(name="badword", description="إدارة الكلمات الممنوعة")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def badword(ctx, action: Literal["add", "remove", "list"], word: str = None):
    words = conf(ctx.guild.id)["automod"]["badwords"]
    if action == "list":
        txt = "، ".join(f"||{w}||" for w in words) or "فاضية."
        return await ctx.send(embed=info_e("🚫 الكلمات الممنوعة", txt), ephemeral=True)
    if not word:
        return await send_err(ctx, "اكتب الكلمة.", "كلمة ناقصة")
    w = word.lower().strip()
    if action == "add":
        if w in words:
            return await send_err(ctx, "الكلمة موجودة من قبل.", "موجودة")
        words.append(w)
    else:
        if w not in words:
            return await send_err(ctx, "الكلمة مو موجودة بالقائمة.", "غير موجودة")
        words.remove(w)
    save_data()
    await ctx.send(embed=ok_e("تمت الإضافة" if action == "add" else "تمت الإزالة", f"||{w}||"), ephemeral=True)

@bot.listen("on_message")
async def automod_listener(message: discord.Message):
    if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
        return
    if message.author.guild_permissions.manage_messages:
        return
    a = conf(message.guild.id)["automod"]
    text = message.content.lower()
    reason = None
    if a["antilink"] and URL_RE.search(text):
        reason = "الروابط ممنوعة"
    elif any(w in text for w in a["badwords"]):
        reason = "كلمة ممنوعة"
    if reason:
        try:
            await message.delete()
            await message.channel.send(embed=err_e(f"{message.author.mention} {reason}", "🛡️ حماية تلقائية"),
                                       delete_after=5)
        except discord.HTTPException:
            pass

# ---------------------------------------------------------------- لوق السيرفر
@bot.hybrid_command(name="setmodlog", description="تحديد روم لوق السيرفر (حذف/تعديل رسائل، حظر...)")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def setmodlog(ctx, channel: discord.TextChannel):
    conf(ctx.guild.id)["modlog"]["channel"] = channel.id
    save_data()
    await ctx.send(embed=ok_e("تم تحديد لوق السيرفر", channel.mention))

@bot.listen("on_message_delete")
async def log_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    e = fancy("🗑️ رسالة محذوفة", color=C_ERR)
    e.add_field(name="👤 الكاتب", value=message.author.mention)
    e.add_field(name="💬 الروم", value=message.channel.mention)
    e.add_field(name="📝 المحتوى", value=(message.content or "—")[:1000], inline=False)
    await modlog(message.guild, e)

@bot.listen("on_message_edit")
async def log_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    e = fancy("✏️ رسالة معدّلة", color=C_WARN)
    e.add_field(name="👤 الكاتب", value=before.author.mention)
    e.add_field(name="💬 الروم", value=before.channel.mention)
    e.add_field(name="قبل", value=(before.content or "—")[:500], inline=False)
    e.add_field(name="بعد", value=(after.content or "—")[:500], inline=False)
    e.add_field(name="🔗 الرابط", value=f"[اذهب للرسالة]({after.jump_url})")
    await modlog(before.guild, e)

@bot.listen("on_member_ban")
async def log_ban(guild: discord.Guild, user: discord.User):
    await modlog(guild, fancy("🔨 حظر", f"{user} (`{user.id}`)", C_ERR))

@bot.listen("on_member_unban")
async def log_unban(guild: discord.Guild, user: discord.User):
    await modlog(guild, fancy("✅ فك حظر", f"{user} (`{user.id}`)", C_OK))

# ---------------------------------------------------------------- الردود التلقائية
_TASHKEEL = re.compile(r"[\u064b-\u0670\u065f\u0640]")

def norm_text(s: str) -> str:
    """يوحّد النص للمقارنة: بدون تشكيل/رموز، ألف وهاء موحّدة، حروف صغيرة."""
    s = _norm(_TASHKEEL.sub("", s or "")).lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()

_AR_COOLDOWN: dict[tuple, float] = {}

@bot.listen("on_message")
async def autoreply_listener(message: discord.Message):
    if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
        return
    if not message.content or message.content.startswith(PREFIX):
        return
    ar = conf(message.guild.id)["autoreply"]
    if not ar["enabled"] or not ar["list"]:
        return
    text = norm_text(message.content)
    if not text:
        return
    hit = ar["list"].get(text)
    if not hit:
        for key, item in ar["list"].items():
            if item.get("mode") == "contains" and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text):
                hit = item
                break
    if not hit:
        return
    ck = (message.guild.id, message.channel.id, norm_text(hit["trigger"]))
    now = time.monotonic()
    if now - _AR_COOLDOWN.get(ck, 0) < 8:
        return
    _AR_COOLDOWN[ck] = now
    try:
        await message.reply(fmt(hit["reply"], message.author), mention_author=False,
                            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False,
                                                                     users=True, replied_user=False))
    except discord.HTTPException:
        pass

@bot.hybrid_command(name="replyadd", aliases=["اضف_رد"], description='إضافة رد تلقائي — مثال: replyadd "السلام عليكم" وعليكم السلام')
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def replyadd(ctx, trigger: str, *, reply: str):
    """trigger=الكلمة/الجملة (بين علامات تنصيص إذا فيها مسافات) | reply=رد البوت — المتغيرات: {user} {name} {server} {count}"""
    ar = conf(ctx.guild.id)["autoreply"]
    key = norm_text(trigger)
    if not key:
        return await send_err(ctx, "الكلمة لازم فيها حروف أو أرقام.", "كلمة غير صحيحة")
    if len(ar["list"]) >= 50 and key not in ar["list"]:
        return await send_err(ctx, "الحد الأقصى 50 رد.", "وصلت الحد")
    reply = nl(reply)
    if len(reply) > 1500:
        return await send_err(ctx, "الرد طويل (الحد 1500 حرف).", "رد طويل")
    old = ar["list"].get(key)
    ar["list"][key] = {"trigger": trigger.strip(), "reply": reply, "mode": (old or {}).get("mode", "exact")}
    save_data()
    e = ok_e("تم تحديث الرد" if old else "تمت إضافة الرد")
    e.add_field(name="💬 إذا كتب العضو", value=trigger.strip(), inline=False)
    e.add_field(name="🤖 البوت يرد", value=reply[:1000], inline=False)
    e.add_field(name="🎯 النوع", value="مطابقة كاملة" if ar["list"][key]["mode"] == "exact" else "يحتوي الكلمة")
    await ctx.send(embed=e)

@bot.hybrid_command(name="replydel", aliases=["احذف_رد"], description="حذف رد تلقائي")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def replydel(ctx, *, trigger: str):
    ar = conf(ctx.guild.id)["autoreply"]
    if ar["list"].pop(norm_text(trigger), None) is None:
        return await send_err(ctx, "ما لقيت رد بهذي الكلمة. شوف `replylist`.", "غير موجود")
    save_data()
    await ctx.send(embed=ok_e("تم حذف الرد", trigger))

@bot.hybrid_command(name="replymode", description="نوع المطابقة: exact = الرسالة كلها، contains = إذا الكلمة داخل الرسالة")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def replymode(ctx, mode: Literal["exact", "contains"], *, trigger: str):
    ar = conf(ctx.guild.id)["autoreply"]
    key = norm_text(trigger)
    item = ar["list"].get(key)
    if not item:
        return await send_err(ctx, "ما لقيت رد بهذي الكلمة.", "غير موجود")
    if mode == "contains" and len(key) < 3:
        return await send_err(ctx, "وضع `contains` يحتاج كلمة 3 حروف أو أكثر عشان ما يزعج الشات.", "كلمة قصيرة")
    item["mode"] = mode
    save_data()
    await ctx.send(embed=ok_e("تم تغيير النوع", f"**{item['trigger']}** ← {'مطابقة كاملة' if mode == 'exact' else 'يحتوي الكلمة'}"))

@bot.hybrid_command(name="replylist", aliases=["الردود"], description="عرض الردود التلقائية")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def replylist(ctx):
    ar = conf(ctx.guild.id)["autoreply"]
    if not ar["list"]:
        return await ctx.send(embed=info_e("💬 الردود التلقائية", "ما فيه ردود. أضف بـ `replyadd`."))
    lines = [f"{'🎯' if v['mode'] == 'contains' else '💬'} **{v['trigger']}** ← {v['reply'][:60]}"
             for v in ar["list"].values()]
    e = info_e("💬 الردود التلقائية", "\n".join(lines)[:4000])
    e.add_field(name="الحالة", value="🟢 مفعّلة" if ar["enabled"] else "🔴 متوقفة")
    e.set_footer(text=f"{BOT_NAME} • 💬 مطابقة كاملة • 🎯 يحتوي الكلمة")
    await ctx.send(embed=e)

@bot.hybrid_command(name="replytoggle", description="تشغيل/إيقاف الردود التلقائية")
@commands.has_permissions(manage_guild=True)
@commands.guild_only()
async def replytoggle(ctx, enabled: bool):
    conf(ctx.guild.id)["autoreply"]["enabled"] = enabled
    save_data()
    await ctx.send(embed=ok_e("الردود التلقائية", "🟢 **مفعّلة**" if enabled else "🔴 **متوقفة**"))

