import io
import os
import re
import json
import asyncio
import datetime
from typing import Literal

import discord
from discord.ext import commands
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


# ---------------------------------------------------------------- الأحداث
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | {BOT_NAME}"))
    print(f"✅ {bot.user} شغّال على {len(bot.guilds)} سيرفر")


@bot.event
async def setup_hook():
    bot.add_dynamic_items(TicketButton)
    bot.add_view(TicketControls())
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
        f"`{PREFIX}botinfo` `{PREFIX}roleinfo` `{PREFIX}membercount` `{PREFIX}say`"))
    e.add_field(name="🛡️ إدارية", inline=False, value=(
        f"`{PREFIX}kick` `{PREFIX}ban` `{PREFIX}unban` `{PREFIX}mute` `{PREFIX}unmute`\n"
        f"`{PREFIX}warn` `{PREFIX}warnings` `{PREFIX}clearwarns` `{PREFIX}clear`\n"
        f"`{PREFIX}lock` `{PREFIX}unlock` `{PREFIX}slowmode` `{PREFIX}nick`\n"
        f"`{PREFIX}addrole` `{PREFIX}removerole`"))
    e.add_field(name="👋 الترحيب", inline=False, value=(
        f"`{PREFIX}setwelcome` `{PREFIX}welcomeset` `{PREFIX}welcomeimage` `{PREFIX}welcomethumb`\n"
        f"`{PREFIX}testwelcome` `{PREFIX}setleave` `{PREFIX}leavemsg` `{PREFIX}autorole`"))
    e.add_field(name="🎫 التذاكر", inline=False, value=(
        f"`{PREFIX}ticketpanel` `{PREFIX}panelset` `{PREFIX}panelimage`\n"
        f"`{PREFIX}ticketadd` `{PREFIX}ticketdel` `{PREFIX}ticketlist` `{PREFIX}ticketlog`\n"
        f"`{PREFIX}tadd` `{PREFIX}tremove` `{PREFIX}tclose`"))
    e.add_field(name="💡 ملاحظة", inline=False,
                value="كل الأوامر تشتغل بالبادئة أو بالسلاش `/`.\n"
                      "متغيرات النصوص: `{user}` `{name}` `{server}` `{count}`\n"
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


async def close_ticket(channel: discord.TextChannel, closer: discord.Member):
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
    await ticket_log(guild, e, discord.File(io.BytesIO(data), filename=f"{channel.name}.txt"))

    if owner:
        try:
            await owner.send(f"🔒 تم إغلاق تذكرتك في **{guild.name}**. هذا سجل المحادثة:",
                             file=discord.File(io.BytesIO(data), filename=f"{channel.name}.txt"))
        except discord.Forbidden:
            pass

    c["tickets"].pop(str(channel.id), None)
    save_data()
    await asyncio.sleep(3)
    await channel.delete(reason=f"Ticket closed by {closer}")


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

        for cid in c["tickets"]:
            info = c["tickets"][cid]
            if info["owner"] == user.id and guild.get_channel(int(cid)):
                return await interaction.response.send_message(
                    f"❌ عندك تذكرة مفتوحة: <#{cid}>", ephemeral=True)

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
        c["tickets"][str(channel.id)] = {
            "owner": user.id, "claimed": None, "type": t["label"], "role": t.get("role"),
            "opened": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        save_data()

        e = embed(f"{t.get('emoji') or '🎫'} {t['label']}",
                  f"أهلاً {user.mention}\n{c['panel']['ticketmsg']}",
                  parse_color(c["panel"]["color"]))
        await channel.send(content=f"{user.mention} {support.mention if support else ''}",
                           embed=e, view=TicketControls())
        await interaction.followup.send(f"✅ تم فتح تذكرتك: {channel.mention}", ephemeral=True)

        le = embed("🎫 تذكرة جديدة", color=0x55FF88)
        le.add_field(name="التذكرة", value=channel.mention)
        le.add_field(name="النوع", value=t["label"])
        le.add_field(name="صاحبها", value=user.mention)
        await ticket_log(guild, le)


class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام", emoji="🙋", style=discord.ButtonStyle.success,
                       custom_id="taqat:ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.send_message("❌ هذي مو تذكرة.", ephemeral=True)
        if not is_staff(interaction.user, info):
            return await interaction.response.send_message("❌ للفريق فقط.", ephemeral=True)
        if info.get("claimed"):
            return await interaction.response.send_message(
                f"❌ مستلمها <@{info['claimed']}>", ephemeral=True)
        info["claimed"] = interaction.user.id
        save_data()
        await interaction.response.send_message(
            embed=embed("🙋 تم الاستلام", f"{interaction.user.mention} استلم التذكرة."))
        le = embed("🙋 استلام تذكرة", color=0xFFAA00)
        le.add_field(name="التذكرة", value=interaction.channel.mention)
        le.add_field(name="المستلم", value=interaction.user.mention)
        await ticket_log(interaction.guild, le)

    @discord.ui.button(label="إغلاق", emoji="🔒", style=discord.ButtonStyle.danger,
                       custom_id="taqat:ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = conf(interaction.guild.id)["tickets"].get(str(interaction.channel.id))
        if not info:
            return await interaction.response.send_message("❌ هذي مو تذكرة.", ephemeral=True)
        if interaction.user.id != info["owner"] and not is_staff(interaction.user, info):
            return await interaction.response.send_message("❌ ما تقدر تغلقها.", ephemeral=True)
        await interaction.response.send_message("🔒 جاري الإغلاق وحفظ السجل...")
        await close_ticket(interaction.channel, interaction.user)


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
async def tclose(ctx):
    info = conf(ctx.guild.id)["tickets"].get(str(ctx.channel.id))
    if not info:
        return await ctx.send("❌ هذا مو روم تذكرة.")
    if ctx.author.id != info["owner"] and not is_staff(ctx.author, info):
        return await ctx.send("❌ ما تقدر تغلقها.")
    await ctx.send("🔒 جاري الإغلاق وحفظ السجل...")
    await close_ticket(ctx.channel, ctx.author)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("حط التوكن في ملف .env: DISCORD_TOKEN=xxxx")
    bot.run(TOKEN)
