import io
import os
import re
import json
import asyncio
import datetime
from typing import Literal

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

def conf(guild_id: int) -> dict:
    g = DATA.setdefault(str(guild_id), {})
    g.setdefault("autorole", None)
    g.setdefault("warns", {})
    g.setdefault("tickets", {})

    w = g.setdefault("welcome", {})
    w.setdefault("channel", None)
    w.setdefault("content", "{user}")
    w.setdefault("author", "{name}")
    w.setdefault("desc", "Welcome To {server}")
    w.setdefault("footer", "{count}")
    w.setdefault("color", "E8352A")
    w.setdefault("thumb", True)
    w.setdefault("image", None)

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

def fmt(text: str, member: discord.Member) -> str:
    return ((text or "")
            .replace("{user}", member.mention)
            .replace("{name}", member.name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count)))

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

# ---------------------------------------------------------------- الأحداث
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | {BOT_NAME}"))
    print(f"✅ {bot.user} شغّال على {len(bot.guilds)} سيرفر")

@bot.event
async def setup_hook():
    bot.add_dynamic_items(TicketButton)
    bot.add_view(TicketControls())
    if not autoclose_loop.is_running():
        autoclose_loop.start()
    await bot.tree.sync()

def build_welcome(member: discord.Member):
    w = conf(member.guild.id)["welcome"]
    e = discord.Embed(description=fmt(w["desc"], member), color=parse_color(w["color"]))
    e.set_author(name=fmt(w["author"], member), icon_url=member.display_avatar.url)
    if w["thumb"]:
        e.set_thumbnail(url=member.display_avatar.url)
    if w["footer"]:
        e.set_footer(text=fmt(w["footer"], member))
    f = apply_image(e, w["image"], "welcome")
    return fmt(w["content"], member) or None, e, f

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
    cid = c["welcome"]["channel"]
    ch = member.guild.get_channel(cid) if cid else None
    if ch:
        content, e, f = build_welcome(member)
        try:
            await ch.send(content=content, embed=e, file=f)
        except discord.Forbidden:
            pass

@bot.event
async def on_member_remove(member: discord.Member):
    lv = conf(member.guild.id)["leave"]
    ch = member.guild.get_channel(lv["channel"]) if lv["channel"] else None
    if ch:
        text = fmt(lv["msg"], member).replace(member.mention, str(member))
        await ch.send(embed=embed(None, text, 0xFF5555))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ ما عندك صلاحية لهذا الأمر.", ephemeral=True)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ البوت ما عنده الصلاحيات الكافية.", ephemeral=True)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ ناقصك: `{error.param.name}`", ephemeral=True)
    elif isinstance(error, (commands.MemberNotFound, commands.BadArgument,
                            commands.BadLiteralArgument)):
        await ctx.send("❌ مدخلات غير صحيحة.", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        print(error)
        await ctx.send("❌ صار خطأ غير متوقع.", ephemeral=True)

# ---------------------------------------------------------------- الأوامر العامة
@bot.hybrid_command(name="help", description="قائمة الأوامر")
async def help_cmd(ctx):
    e = embed(f"📖 أوامر {BOT_NAME}")
    e.add_field(name="🌐 عامة", inline=False, value=(
        f"`{PREFIX}ping` `{PREFIX}avatar` `{PREFIX}userinfo` `{PREFIX}serverinfo`\n"
        f"`{PREFIX}botinfo` `{PREFIX}roleinfo` `{PREFIX}membercount` `{PREFIX}say`\n"
        f"`{PREFIX}poll` `{PREFIX}announce` `{PREFIX}roll` `{PREFIX}coinflip`"))
    e.add_field(name="🛡️ إدارية", inline=False, value=(
        f"`{PREFIX}kick` `{PREFIX}ban` `{PREFIX}unban` `{PREFIX}mute` `{PREFIX}unmute`\n"
        f"`{PREFIX}warn` `{PREFIX}unwarn` `{PREFIX}warnings` `{PREFIX}clearwarns` `{PREFIX}clear`\n"
        f"`{PREFIX}lock` `{PREFIX}unlock` `{PREFIX}hide` `{PREFIX}unhide` `{PREFIX}nuke`\n"
        f"`{PREFIX}slowmode` `{PREFIX}nick` `{PREFIX}addrole` `{PREFIX}removerole`"))
    e.add_field(name="🔰 الحماية", inline=False, value=(
        f"`{PREFIX}rulesguard` `{PREFIX}rulesoff` `{PREFIX}rulesexempt`\n"
        f"`{PREFIX}antilink` `{PREFIX}badword` `{PREFIX}setmodlog`"))
    e.add_field(name="👋 الترحيب", inline=False, value=(
        f"`{PREFIX}setwelcome` `{PREFIX}welcomeset` `{PREFIX}welcomeimage` `{PREFIX}welcomethumb`\n"
        f"`{PREFIX}testwelcome` `{PREFIX}setleave` `{PREFIX}leavemsg` `{PREFIX}autorole`"))
    e.add_field(name="🎫 التذاكر", inline=False, value=(
        f"`{PREFIX}ticketpanel` `{PREFIX}panelset` `{PREFIX}panelimage`\n"
        f"`{PREFIX}ticketadd` `{PREFIX}ticketdel` `{PREFIX}ticketlist` `{PREFIX}ticketlog`\n"
        f"`{PREFIX}tadd` `{PREFIX}tremove` `{PREFIX}tclose` `{PREFIX}tclaim` `{PREFIX}tunclaim`\n"
        f"`{PREFIX}trename` `{PREFIX}tpriority` `{PREFIX}tlock` `{PREFIX}tunlock`\n"
        f"`{PREFIX}ttranscript` `{PREFIX}tblacklist` `{PREFIX}tmax` `{PREFIX}tautoclose` `{PREFIX}tstats`"))
    e.add_field(name="🎛️ تخصيص داخل التذكرة", inline=False, value=(
        f"`{PREFIX}insideset` `{PREFIX}insideimage` `{PREFIX}insideimageoff` `{PREFIX}insidethumb`\n"
        f"`{PREFIX}insidebtn` `{PREFIX}insidereason` `{PREFIX}insidepreview`"))
    e.add_field(name="💡 ملاحظة", inline=False,
                value="كل الأوامر تشتغل بالبادئة أو بالسلاش `/`.\n"
                      "متغيرات النصوص: `{user}` `{name}` `{server}` `{count}`\n"
                      "متغيرات داخل التذكرة: `{user}` `{name}` `{server}` `{date}` `{reason}` "
                      "`{type}` `{ticket}` `{support}` `{claimed}`\n"
                      "للسطر الجديد في السلاش اكتب `\\n`")
    await ctx.send(embed=e)

@bot.hybrid_command(name="ping", description="سرعة البوت")
async def ping(ctx):
    await ctx.send(embed=embed("🏓 Pong!", f"`{round(bot.latency * 1000)}ms`"))

@bot.hybrid_command(name="avatar", description="صورة العضو")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = embed(f"صورة {member.display_name}")
    e.set_image(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.hybrid_command(name="userinfo", description="معلومات عضو")
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]
    e = embed(f"👤 {member}")
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="الآيدي", value=member.id)
    e.add_field(name="تاريخ الحساب", value=discord.utils.format_dt(member.created_at, "D"))
    e.add_field(name="دخل السيرفر", value=discord.utils.format_dt(member.joined_at, "D"))
    e.add_field(name="أعلى رتبة", value=member.top_role.mention)
    e.add_field(name=f"الرتب ({len(roles)})", value=" ".join(roles[:15]) or "لا يوجد", inline=False)
    await ctx.send(embed=e)

@bot.hybrid_command(name="serverinfo", description="معلومات السيرفر")
async def serverinfo(ctx):
    g = ctx.guild
    e = embed(f"🏠 {g.name}")
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="المالك", value=g.owner.mention if g.owner else "؟")
    e.add_field(name="الأعضاء", value=g.member_count)
    e.add_field(name="الرومات", value=len(g.channels))
    e.add_field(name="الرتب", value=len(g.roles))
    e.add_field(name="البوستات", value=g.premium_subscription_count)
    e.add_field(name="تاريخ الإنشاء", value=discord.utils.format_dt(g.created_at, "D"))
    await ctx.send(embed=e)

@bot.hybrid_command(name="membercount", description="عدد الأعضاء")
async def membercount(ctx):
    await ctx.send(embed=embed("👥 الأعضاء", f"**{ctx.guild.member_count}**"))

@bot.hybrid_command(name="roleinfo", description="معلومات رتبة")
async def roleinfo(ctx, role: discord.Role):
    e = embed(f"🎭 {role.name}", color=role.color.value or COLOR)
    e.add_field(name="الآيدي", value=role.id)
    e.add_field(name="الأعضاء", value=len(role.members))
    e.add_field(name="اللون", value=str(role.color))
    e.add_field(name="تاريخ الإنشاء", value=discord.utils.format_dt(role.created_at, "D"))
    await ctx.send(embed=e)

@bot.hybrid_command(name="botinfo", description="معلومات البوت")
async def botinfo(ctx):
    up = datetime.datetime.now(datetime.timezone.utc) - START_TIME
    h, rem = divmod(int(up.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    e = embed(f"🤖 {BOT_NAME}")
    e.add_field(name="السيرفرات", value=len(bot.guilds))
    e.add_field(name="المستخدمين", value=sum(g.member_count for g in bot.guilds))
    e.add_field(name="مدة التشغيل", value=f"{h}س {m}د {s}ث")
    e.add_field(name="discord.py", value=discord.__version__)
    await ctx.send(embed=e)

@bot.hybrid_command(name="say", description="البوت يكرر كلامك")
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, text: str):
    if ctx.interaction:
        await ctx.send("✅", ephemeral=True)
        await ctx.channel.send(text, allowed_mentions=discord.AllowedMentions.none())
    else:
        await ctx.message.delete()
        await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())

# ---------------------------------------------------------------- الأوامر الإدارية
@bot.hybrid_command(name="kick", description="طرد عضو")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await ctx.send(f"❌ {err}")
    await member.kick(reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=embed("👢 تم الطرد", f"{member} — {reason}"))

@bot.hybrid_command(name="ban", description="حظر عضو")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await ctx.send(f"❌ {err}")
    await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=0)
    await ctx.send(embed=embed("🔨 تم الحظر", f"{member} — {reason}", 0xFF5555))

@bot.hybrid_command(name="unban", description="فك الحظر بالآيدي")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def unban(ctx, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
    except (ValueError, discord.NotFound):
        return await ctx.send("❌ ما لقيت هذا الحظر.")
    await ctx.send(embed=embed("✅ تم فك الحظر", str(user)))

@bot.hybrid_command(name="mute", description="كتم عضو (تايم أوت) بالدقائق")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 10, *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await ctx.send(f"❌ {err}")
    if not 1 <= minutes <= 40320:
        return await ctx.send("❌ المدة من 1 إلى 40320 دقيقة.")
    await member.timeout(datetime.timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=embed("🔇 تم الكتم", f"{member.mention} لمدة **{minutes}** دقيقة — {reason}"))

@bot.hybrid_command(name="unmute", description="فك الكتم")
@commands.has_permissions(moderate_members=True)
@commands.bot_has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(embed=embed("🔊 تم فك الكتم", member.mention))

@bot.hybrid_command(name="warn", description="تحذير عضو")
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    err = can_act(ctx, member)
    if err:
        return await ctx.send(f"❌ {err}")
    c = conf(ctx.guild.id)
    lst = c["warns"].setdefault(str(member.id), [])
    lst.append({"reason": reason, "mod": ctx.author.id,
                "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save_data()
    await ctx.send(embed=embed("⚠️ تحذير", f"{member.mention} — {reason}\nإجمالي التحذيرات: **{len(lst)}**", 0xFFAA00))
    try:
        await member.send(f"⚠️ جاك تحذير في **{ctx.guild.name}**: {reason}")
    except discord.Forbidden:
        pass

@bot.hybrid_command(name="warnings", description="عرض تحذيرات عضو")
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    lst = conf(ctx.guild.id)["warns"].get(str(member.id), [])
    if not lst:
        return await ctx.send(embed=embed("✅", f"{member.mention} ما عنده تحذيرات."))
    lines = [f"**{i}.** {w['reason']} — <@{w['mod']}>" for i, w in enumerate(lst, 1)]
    await ctx.send(embed=embed(f"⚠️ تحذيرات {member.display_name}", "\n".join(lines[:20])))

@bot.hybrid_command(name="clearwarns", description="مسح تحذيرات عضو")
@commands.has_permissions(manage_guild=True)
async def clearwarns(ctx, member: discord.Member):
    conf(ctx.guild.id)["warns"].pop(str(member.id), None)
    save_data()
    await ctx.send(embed=embed("🧹 تم المسح", f"تحذيرات {member.mention}"))

@bot.hybrid_command(name="clear", description="مسح رسائل")
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if not 1 <= amount <= 100:
        return await ctx.send("❌ العدد من 1 إلى 100.")
    if ctx.interaction:
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"🧹 انمسح {len(deleted)} رسالة.", ephemeral=True)
    else:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 انمسح {len(deleted) - 1} رسالة.", delete_after=4)

@bot.hybrid_command(name="lock", description="قفل الروم")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(embed=embed("🔒 تم قفل الروم"))

@bot.hybrid_command(name="unlock", description="فتح الروم")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
    await ctx.send(embed=embed("🔓 تم فتح الروم"))

@bot.hybrid_command(name="slowmode", description="وضع البطيء بالثواني (0 للإلغاء)")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    if not 0 <= seconds <= 21600:
        return await ctx.send("❌ من 0 إلى 21600 ثانية.")
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(embed=embed("🐢 الوضع البطيء", f"**{seconds}** ثانية"))

@bot.hybrid_command(name="nick", description="تغيير لقب عضو")
@commands.has_permissions(manage_nicknames=True)
@commands.bot_has_permissions(manage_nicknames=True)
async def nick(ctx, member: discord.Member, *, nickname: str = None):
    err = can_act(ctx, member) if member != ctx.author else None
    if err:
        return await ctx.send(f"❌ {err}")
    await member.edit(nick=nickname)
    await ctx.send(embed=embed("✏️ تم", f"{member.mention} → {nickname or 'الاسم الأصلي'}"))

@bot.hybrid_command(name="addrole", description="إعطاء رتبة لعضو")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    if role >= ctx.guild.me.top_role or (role >= ctx.author.top_role and ctx.author != ctx.guild.owner):
        return await ctx.send("❌ هذي الرتبة أعلى من رتبتك أو رتبة البوت.")
    await member.add_roles(role)
    await ctx.send(embed=embed("✅ تمت الإضافة", f"{role.mention} → {member.mention}"))

@bot.hybrid_command(name="removerole", description="سحب رتبة من عضو")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    if role >= ctx.guild.me.top_role or (role >= ctx.author.top_role and ctx.author != ctx.guild.owner):
        return await ctx.send("❌ هذي الرتبة أعلى من رتبتك أو رتبة البوت.")
    await member.remove_roles(role)
    await ctx.send(embed=embed("✅ تم السحب", f"{role.mention} ← {member.mention}"))

# ---------------------------------------------------------------- إعدادات الترحيب
@bot.hybrid_command(name="setwelcome", description="تحديد روم الترحيب")
@commands.has_permissions(manage_guild=True)
async def setwelcome(ctx, channel: discord.TextChannel):
    conf(ctx.guild.id)["welcome"]["channel"] = channel.id
    save_data()
    await ctx.send(embed=embed("✅ روم الترحيب", channel.mention))

@bot.hybrid_command(name="welcomeset", description="تعديل نص الترحيب (المتغيرات: {user} {name} {server} {count})")
@commands.has_permissions(manage_guild=True)
async def welcomeset(ctx, item: Literal["content", "author", "desc", "footer", "color"], *, value: str):
    """content=الرسالة فوق الإيمبد | author=الاسم فوق | desc=الوصف (تقدر تحط منشن رومات <#id>) | footer=الفوتر | color=اللون"""
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

@bot.hybrid_command(name="testwelcome", description="تجربة رسالة الترحيب")
@commands.has_permissions(manage_guild=True)
async def testwelcome(ctx):
    content, e, f = build_welcome(ctx.author)
    await ctx.send(content=content, embed=e, file=f)

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

    e = embed("🔒 تذكرة مغلقة", color=0xFF5555)
    e.add_field(name="التذكرة", value=channel.name)
    e.add_field(name="النوع", value=info.get("type", "—"))
    e.add_field(name="صاحبها", value=f"<@{info['owner']}>")
    e.add_field(name="أغلقها", value=closer.mention)
    e.add_field(name="استلمها", value=f"<@{info['claimed']}>" if info.get("claimed") else "لا أحد")
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
    await channel.send(embed=embed("🙋 تم الاستلام", f"{user.mention} استلم التذكرة."))
    le = embed("🙋 استلام تذكرة", color=0xFFAA00)
    le.add_field(name="التذكرة", value=channel.mention)
    le.add_field(name="المستلم", value=user.mention)
    await ticket_log(channel.guild, le)
    return None

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

STAFF_OPTS = [
    ("add", "إضافة عضو", "➕", "إضافة شخص للتذكرة"),
    ("remove", "إزالة عضو", "➖", "إزالة شخص من التذكرة"),
    ("transfer", "تحويل الاستلام", "🔁", "تحويل التذكرة لعضو من الفريق"),
    ("unclaim", "إلغاء الاستلام", "↩️", "تحرير التذكرة ليستلمها غيرك"),
    ("rename", "إعادة تسمية", "✏️", "تغيير اسم روم التذكرة"),
    ("priority", "تغيير الأولوية", "🚦", "منخفضة / عادية / عالية / عاجلة"),
    ("lock", "قفل الكتابة", "🔒", "منع صاحب التذكرة من الكتابة"),
    ("unlock", "فتح الكتابة", "🔓", "السماح لصاحب التذكرة بالكتابة"),
    ("ping_owner", "تنبيه صاحب التذكرة", "🔔", "منشن + رسالة خاصة"),
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

    if action in ("lock", "unlock"):
        await interaction.response.edit_message(content="✅ تم.", view=None)
        return await set_lock(ch, info, action == "lock")
    if action == "unclaim":
        if not info.get("claimed"):
            return await interaction.response.edit_message(content="❌ التذكرة مو مستلمة.", view=None)
        info["claimed"] = None
        save_data()
        await interaction.response.edit_message(content="✅ تم.", view=None)
        return await ch.send(embed=embed("↩️ إلغاء الاستلام", f"{user.mention} حرر التذكرة."))
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

class MoreSelect(discord.ui.Select):
    def __init__(self, staff: bool):
        opts = STAFF_OPTS if staff else OWNER_OPTS
        super().__init__(placeholder="⚙️ اختر إجراء...", options=[
            discord.SelectOption(label=l, value=v, emoji=e, description=d) for v, l, e, d in opts])

    async def callback(self, interaction: discord.Interaction):
        await handle_action(interaction, self.values[0])

class MoreView(discord.ui.View):
    def __init__(self, staff: bool):
        super().__init__(timeout=120)
        self.add_item(MoreSelect(staff))

class TicketControls(discord.ui.View):
    """أزرار لوحة التحكم داخل التذكرة — الاسم والإيموجي واللون قابلة للتخصيص (insidebtn)."""
    def __init__(self, guild_id: int = None):
        super().__init__(timeout=None)
        saved = conf(guild_id)["inside"]["btn"] if guild_id else {}
        handlers = {"claim": self.on_claim, "close": self.on_close, "more": self.on_more}
        for k in ("claim", "close", "more"):
            d = {**DEFAULT_BTN[k], **saved.get(k, {})}
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
            return await interaction.response.send_message(
                f"❌ مستلمها <@{info['claimed']}>", ephemeral=True)
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
        await interaction.response.send_message("⚙️ اختر الإجراء:", view=MoreView(staff), ephemeral=True)

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
    info["claimed"] = None
    save_data()
    await ctx.send(embed=embed("↩️ إلغاء الاستلام", f"{ctx.author.mention} حرر التذكرة."))

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
async def rulesguard(ctx, channel: discord.TextChannel,
                     action: Literal["delete", "warn", "mute", "kick", "ban"] = "ban"):
    r = conf(ctx.guild.id)["rules"]
    r["channel"], r["action"] = channel.id, action
    save_data()
    await ctx.send(embed=embed("🔰 حماية روم القوانين",
                               f"{channel.mention}\nالعقوبة: **{action}**\n"
                               f"الأدمن والرتب المستثناة ما تنطبق عليهم."))

@bot.hybrid_command(name="rulesoff", description="إيقاف حماية روم القوانين")
@commands.has_permissions(administrator=True)
async def rulesoff(ctx):
    conf(ctx.guild.id)["rules"]["channel"] = None
    save_data()
    await ctx.send(embed=embed("✅ تم الإيقاف"))

@bot.hybrid_command(name="rulesexempt", description="استثناء/إلغاء استثناء رتبة من حماية القوانين")
@commands.has_permissions(administrator=True)
async def rulesexempt(ctx, role: discord.Role):
    ex = conf(ctx.guild.id)["rules"]["exempt"]
    if role.id in ex:
        ex.remove(role.id)
        txt = f"{role.mention} ← انشالت من الاستثناء"
    else:
        ex.append(role.id)
        txt = f"{role.mention} ← مستثناة"
    save_data()
    await ctx.send(embed=embed("✅ تم", txt))

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
    e = embed("🔰 حماية القوانين", color=0xFF5555)
    e.add_field(name="العضو", value=f"{m.mention} ({m.id})")
    e.add_field(name="العقوبة", value=action)
    e.add_field(name="الرسالة", value=(message.content or "—")[:500], inline=False)
    await modlog(message.guild, e)

# ---------------------------------------------------------------- الحماية: روابط / كلمات ممنوعة
@bot.hybrid_command(name="antilink", description="منع الروابط لغير الإدارة")
@commands.has_permissions(manage_guild=True)
async def antilink(ctx, enabled: bool):
    conf(ctx.guild.id)["automod"]["antilink"] = enabled
    save_data()
    await ctx.send(embed=embed("✅ تم", "مفعّل" if enabled else "متوقف"))

@bot.hybrid_command(name="badword", description="إدارة الكلمات الممنوعة")
@commands.has_permissions(manage_guild=True)
async def badword(ctx, action: Literal["add", "remove", "list"], word: str = None):
    words = conf(ctx.guild.id)["automod"]["badwords"]
    if action == "list":
        return await ctx.send(embed=embed("🚫 الكلمات الممنوعة", "، ".join(f"||{w}||" for w in words) or "فاضية."))
    if not word:
        return await ctx.send("❌ اكتب الكلمة.")
    w = word.lower().strip()
    if action == "add" and w not in words:
        words.append(w)
    elif action == "remove" and w in words:
        words.remove(w)
    save_data()
    await ctx.send("✅ تم.", ephemeral=True)

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
            await message.channel.send(f"{message.author.mention} ❌ {reason}", delete_after=5)
        except discord.HTTPException:
            pass

# ---------------------------------------------------------------- لوق السيرفر
@bot.hybrid_command(name="setmodlog", description="تحديد روم لوق السيرفر (حذف/تعديل رسائل، حظر...)")
@commands.has_permissions(manage_guild=True)
async def setmodlog(ctx, channel: discord.TextChannel):
    conf(ctx.guild.id)["modlog"]["channel"] = channel.id
    save_data()
    await ctx.send(embed=embed("✅ لوق السيرفر", channel.mention))

@bot.listen("on_message_delete")
async def log_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    e = embed("🗑️ رسالة محذوفة", color=0xFF5555)
    e.add_field(name="الكاتب", value=message.author.mention)
    e.add_field(name="الروم", value=message.channel.mention)
    e.add_field(name="المحتوى", value=(message.content or "—")[:1000], inline=False)
    await modlog(message.guild, e)

@bot.listen("on_message_edit")
async def log_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    e = embed("✏️ رسالة معدّلة", color=0xFFAA00)
    e.add_field(name="الكاتب", value=before.author.mention)
    e.add_field(name="الروم", value=before.channel.mention)
    e.add_field(name="قبل", value=(before.content or "—")[:500], inline=False)
    e.add_field(name="بعد", value=(after.content or "—")[:500], inline=False)
    e.add_field(name="الرابط", value=f"[اذهب للرسالة]({after.jump_url})")
    await modlog(before.guild, e)

@bot.listen("on_member_ban")
async def log_ban(guild: discord.Guild, user: discord.User):
    await modlog(guild, embed("🔨 حظر", f"{user} ({user.id})", 0xFF5555))

@bot.listen("on_member_unban")
async def log_unban(guild: discord.Guild, user: discord.User):
    await modlog(guild, embed("✅ فك حظر", f"{user} ({user.id})", 0x55FF88))

# ---------------------------------------------------------------- أوامر إضافية
@bot.hybrid_command(name="unwarn", description="حذف تحذير واحد من عضو (برقمه)")
@commands.has_permissions(manage_messages=True)
async def unwarn(ctx, member: discord.Member, number: int = 1):
    lst = conf(ctx.guild.id)["warns"].get(str(member.id), [])
    if not 1 <= number <= len(lst):
        return await ctx.send("❌ رقم التحذير غير صحيح.")
    removed = lst.pop(number - 1)
    save_data()
    await ctx.send(embed=embed("✅ تم حذف التحذير", f"{member.mention} — {removed['reason']}"))

@bot.hybrid_command(name="hide", description="إخفاء الروم عن الجميع")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def hide(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
    await ctx.send(embed=embed("🙈 تم إخفاء الروم"))

@bot.hybrid_command(name="unhide", description="إظهار الروم")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unhide(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=None)
    await ctx.send(embed=embed("👁️ تم إظهار الروم"))

@bot.hybrid_command(name="nuke", description="مسح كل رسائل الروم (يعيد إنشاءه)")
@commands.has_permissions(administrator=True)
@commands.bot_has_permissions(manage_channels=True)
async def nuke(ctx):
    ch = ctx.channel
    if ctx.interaction:
        await ctx.send("💥 جاري التنظيف...", ephemeral=True)
    new = await ch.clone(reason=f"Nuke by {ctx.author}")
    await new.edit(position=ch.position)
    await ch.delete()
    await new.send(embed=embed("💥 تم تنظيف الروم", f"بواسطة {ctx.author.mention}"))

@bot.hybrid_command(name="announce", description="إرسال إعلان في روم")
@commands.has_permissions(manage_guild=True)
async def announce(ctx, channel: discord.TextChannel, *, text: str):
    await channel.send(embed=embed("📢 إعلان", nl(text)))
    await ctx.send("✅ تم الإرسال.", ephemeral=True)

@bot.hybrid_command(name="poll", description="تصويت — الخيارات مفصولة بـ |")
@commands.has_permissions(manage_messages=True)
async def poll(ctx, question: str, *, options: str):
    opts = [o.strip() for o in options.split("|") if o.strip()]
    if not 2 <= len(opts) <= 10:
        return await ctx.send("❌ من 2 إلى 10 خيارات مفصولة بـ |")
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    e = embed(f"📊 {question}", "\n".join(f"{nums[i]} {o}" for i, o in enumerate(opts)))
    msg = await ctx.channel.send(embed=e)
    for i in range(len(opts)):
        await msg.add_reaction(nums[i])
    if ctx.interaction:
        await ctx.send("✅", ephemeral=True)

@bot.hybrid_command(name="roll", description="رمي نرد")
async def roll(ctx, sides: int = 6):
    import random
    if not 2 <= sides <= 1000:
        return await ctx.send("❌ من 2 إلى 1000.")
    await ctx.send(embed=embed("🎲 النرد", f"طلع لك **{random.randint(1, sides)}** من {sides}"))

@bot.hybrid_command(name="coinflip", description="صورة أو كتابة")
async def coinflip(ctx):
    import random
    await ctx.send(embed=embed("🪙 العملة", random.choice(["**صورة**", "**كتابة**"])))

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("حط التوكن في ملف .env: DISCORD_TOKEN=xxxx")
    bot.run(TOKEN)
