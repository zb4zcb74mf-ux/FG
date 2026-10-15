# ============================================================
# TURKI SYSTEMS - All-in-One Discord Bot
# Python | discord.py 2.x | SQLite | Railway Persistent Storage
# ============================================================

import os
import json
import re
import asyncio
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET

from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands, tasks

import yt_dlp

TOKEN = os.getenv("DISCORD_TOKEN")

# تخزين قاعدة البيانات في مسار دائم داخل الحاوية أو المجلد الحالي لضمان عدم حذف البيانات عند الـ Redeploy
DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", ".")
DB_FILE = os.path.join(DATA_DIR, "turki_systems.db")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
# DATABASE
# ============================================================

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def setup_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tickets (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            claimed_by INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ticket_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        """)


def get_settings(guild_id: int) -> dict:
    with db() as con:
        row = con.execute(
            "SELECT data FROM settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["data"])
    except (TypeError, json.JSONDecodeError):
        return {}


def save_settings(guild_id: int, data: dict):
    with db() as con:
        con.execute(
            """INSERT INTO settings (guild_id, data) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data""",
            (guild_id, json.dumps(data, ensure_ascii=False))
        )


def update_settings(guild_id: int, **kwargs):
    data = get_settings(guild_id)
    data.update(kwargs)
    save_settings(guild_id, data)
    return data


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator


def admin_check():
    return app_commands.checks.has_permissions(administrator=True)


def make_embed(title, description=None, color=0xD889C9):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    return embed


async def send_log(guild: discord.Guild, title: str, description: str):
    settings = get_settings(guild.id)
    channel_id = settings.get("logs_channel")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if channel:
        try:
            await channel.send(embed=make_embed(title, description))
        except discord.HTTPException:
            pass


async def reply(interaction: discord.Interaction, content=None, *, embed=None,
                view=None, ephemeral=True):
    if interaction.response.is_done():
        await interaction.followup.send(
            content=content, embed=embed, view=view, ephemeral=ephemeral
        )
    else:
        await interaction.response.send_message(
            content=content, embed=embed, view=view, ephemeral=ephemeral
        )


# ============================================================
# TICKETS: BUTTONS, REASONS, CLAIM, CLOSE, RATINGS
# ============================================================

class TicketReasonModal(discord.ui.Modal, title="فتح تكت جديد"):
    reason = discord.ui.TextInput(
        label="سبب فتح التكت",
        placeholder="اكتب سبب فتح التكت هنا...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    def __init__(self, section_key: str, section_label: str):
        super().__init__()
        self.section_key = section_key
        self.section_label = section_label

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction,
            self.section_key,
            self.section_label,
            str(self.reason.value)
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, guild_id: int, timeout=None):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        settings = get_settings(guild_id)
        buttons = settings.get("ticket_buttons", [
            {"label": "الدعم الفني", "key": "support", "emoji": "🎫"}
        ])

        for index, item in enumerate(buttons[:20]):
            label = str(item.get("label", f"تكت {index + 1}"))[:80]
            key = str(item.get("key", f"section_{index}"))[:40]
            emoji = item.get("emoji") or None
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.primary,
                custom_id=f"turki_ticket:{guild_id}:{key}"
            )

            async def callback(interaction: discord.Interaction,
                               section_key=key, section_label=label):
                await interaction.response.send_modal(
                    TicketReasonModal(section_key, section_label)
                )

            button.callback = callback
            self.add_item(button)


class TicketControlsView(discord.ui.View):
    def __init__(self, timeout=None):
        super().__init__(timeout=timeout)

    @discord.ui.button(
        label="استلام التكت", emoji="🙋", style=discord.ButtonStyle.success,
        custom_id="turki_ticket_claim"
    )
    async def claim(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await reply(interaction, "ما عندك صلاحية استلام التكت.")

        with db() as con:
            row = con.execute(
                "SELECT claimed_by FROM tickets WHERE channel_id = ?",
                (interaction.channel_id,)
            ).fetchone()
            if not row:
                return await reply(interaction, "هذا الروم ليس تكت مسجلًا.")
            if row["claimed_by"]:
                return await reply(interaction, "تم استلام التكت مسبقًا.")

            con.execute(
                "UPDATE tickets SET claimed_by = ? WHERE channel_id = ?",
                (interaction.user.id, interaction.channel_id)
            )

        button.disabled = True
        button.label = f"استلمه {interaction.user.display_name}"[:80]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"تم استلام التكت بواسطة {interaction.user.mention}."
        )
        await send_log(
            interaction.guild, "استلام تكت",
            f"الروم: {interaction.channel.mention}\nالإداري: {interaction.user.mention}"
        )

    @discord.ui.button(
        label="إغلاق التكت", emoji="🔒", style=discord.ButtonStyle.danger,
        custom_id="turki_ticket_close"
    )
    async def close(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        with db() as con:
            row = con.execute(
                "SELECT user_id FROM tickets WHERE channel_id = ?",
                (interaction.channel_id,)
            ).fetchone()

        if not row:
            return await reply(interaction, "هذا الروم ليس تكت مسجلًا.")

        owner_id = int(row["user_id"])
        allowed = (
            interaction.user.id == owner_id
            or interaction.user.guild_permissions.manage_channels
        )
        if not allowed:
            return await reply(interaction, "فقط صاحب التكت أو الإدارة يستطيع إغلاقه.")

        await interaction.response.send_message("سيتم إغلاق التكت خلال 5 ثوانٍ.")
        guild = interaction.guild
        channel = interaction.channel

        try:
            owner = await bot.fetch_user(owner_id)
            rating_view = TicketRatingView(guild.id, channel.id)
            await owner.send(
                f"تم إغلاق تكتك في **{guild.name}**. قيّم تجربتك:",
                view=rating_view
            )
        except (discord.HTTPException, discord.NotFound):
            pass

        await send_log(
            guild, "إغلاق تكت",
            f"الروم: #{channel.name}\nبواسطة: {interaction.user.mention}"
        )
        await asyncio.sleep(5)
        try:
            with db() as con:
                con.execute(
                    "DELETE FROM tickets WHERE channel_id = ?", (channel.id,)
                )
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass


class TicketRatingView(discord.ui.View):
    def __init__(self, guild_id: int, channel_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.channel_id = channel_id

        for rating in range(1, 6):
            button = discord.ui.Button(
                label=f"{rating} ⭐",
                style=discord.ButtonStyle.secondary,
                custom_id=f"turki_rate:{guild_id}:{channel_id}:{rating}"
            )

            async def callback(interaction: discord.Interaction, score=rating):
                with db() as con:
                    existing = con.execute(
                        """SELECT id FROM ticket_ratings
                           WHERE guild_id=? AND channel_id=? AND user_id=?""",
                        (self.guild_id, self.channel_id, interaction.user.id)
                    ).fetchone()
                    if existing:
                        return await reply(interaction, "سبق وقيّمت هذا التكت.")

                    con.execute(
                        """INSERT INTO ticket_ratings
                           (guild_id, channel_id, user_id, rating, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (self.guild_id, self.channel_id, interaction.user.id,
                         score, utcnow())
                    )

                await reply(interaction, f"شكرًا لك! تم تسجيل تقييمك: {score}/5 ⭐")
                guild = bot.get_guild(self.guild_id)
                if guild:
                    await send_log(
                        guild, "تقييم تكت",
                        f"العضو: {interaction.user.mention}\nالتقييم: {score}/5"
                    )

            button.callback = callback
            self.add_item(button)


async def create_ticket(interaction, section_key, section_label, reason):
    guild = interaction.guild
    if not guild:
        return await reply(interaction, "استخدم الأمر داخل السيرفر.")

    settings = get_settings(guild.id)

    with db() as con:
        existing = con.execute(
            "SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=?",
            (guild.id, interaction.user.id)
        ).fetchone()

    if existing:
        channel = guild.get_channel(int(existing["channel_id"]))
        if channel:
            return await reply(
                interaction, f"عندك تكت مفتوح بالفعل: {channel.mention}"
            )

    category_id = settings.get("ticket_category")
    category = guild.get_channel(int(category_id)) if category_id else None
    if category_id and not isinstance(category, discord.CategoryChannel):
        category = None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            attach_files=True, embed_links=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_channels=True
        )
    }

    role_id = settings.get("ticket_roles", {}).get(section_key)
    if role_id:
        role = guild.get_role(int(role_id))
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    safe_name = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF-]", "-", interaction.user.name.lower())
    channel_name = f"ticket-{safe_name}"[:90]

    try:
        channel = await guild.create_text_channel(
            channel_name, category=category, overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user}"
        )
    except discord.HTTPException as exc:
        return await reply(interaction, f"ما قدرت أفتح التكت: {exc}")

    with db() as con:
        con.execute(
            """INSERT OR REPLACE INTO tickets
               (channel_id, guild_id, user_id, claimed_by, created_at)
               VALUES (?, ?, ?, NULL, ?)""",
            (channel.id, guild.id, interaction.user.id, utcnow())
        )

    embed = make_embed(
        f"🎫 {section_label}",
        f"أهلًا {interaction.user.mention}\n"
        f"**سبب فتح التكت:**\n{reason}\n\n"
        "اشرح طلبك بالتفصيل وانتظر رد الإدارة."
    )
    await channel.send(
        content=interaction.user.mention,
        embed=embed,
        view=TicketControlsView()
    )
    await reply(interaction, f"تم فتح تكتك: {channel.mention}")
    await send_log(
        guild, "فتح تكت",
        f"العضو: {interaction.user.mention}\n"
        f"القسم: {section_label}\nالروم: {channel.mention}"
    )


@bot.tree.command(name="ticketsetup", description="إرسال لوحة التكت")
@admin_check()
async def ticketsetup(interaction: discord.Interaction):
    if not interaction.guild:
        return await reply(interaction, "استخدم الأمر داخل السيرفر.")
    settings = get_settings(interaction.guild.id)
    buttons = settings.get("ticket_buttons", [
        {"label": "الدعم الفني", "key": "support", "emoji": "🎫"},
        {"label": "الإدارة", "key": "management", "emoji": "🛡️"}
    ])
    settings["ticket_buttons"] = buttons
    save_settings(interaction.guild.id, settings)

    embed = make_embed(
        settings.get("ticket_title", "🎫 تذاكر الدعم الفني"),
        settings.get("ticket_description", "اضغط على القسم المناسب لفتح تكت.")
    )
    image = settings.get("ticket_image")
    if image:
        embed.set_image(url=image)

    await interaction.channel.send(
        embed=embed, view=TicketPanelView(interaction.guild.id)
    )
    await reply(interaction, "تم إرسال لوحة التكت.")


@bot.tree.command(name="ticketedit", description="تعديل عنوان ووصف وصورة لوحة التكت")
@admin_check()
@app_commands.describe(title="عنوان اللوحة", description="وصف اللوحة",
                       image_url="رابط صورة مباشر، أو اتركه فارغًا")
async def ticketedit(interaction: discord.Interaction, title: str,
                     description: str, image_url: str = ""):
    settings = update_settings(
        interaction.guild.id,
        ticket_title=title[:256],
        ticket_description=description[:4000],
        ticket_image=image_url.strip()
    )
    await reply(interaction, "تم حفظ إعدادات لوحة التكت.")


@bot.tree.command(name="ticketbutton", description="إضافة زر جديد للوحة التكت")
@admin_check()
@app_commands.describe(label="اسم الزر", key="معرّف القسم بالإنجليزية",
                       emoji="إيموجي اختياري")
async def ticketbutton(interaction: discord.Interaction, label: str,
                       key: str, emoji: str = ""):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", key):
        return await reply(interaction, "المعرّف يجب أن يكون إنجليزيًا أو أرقامًا أو _ أو -.")

    settings = get_settings(interaction.guild.id)
    buttons = settings.get("ticket_buttons", [])
    if len(buttons) >= 20:
        return await reply(interaction, "وصلت للحد الأقصى: 20 زرًا.")

    buttons = [b for b in buttons if b.get("key") != key]
    buttons.append({"label": label[:80], "key": key, "emoji": emoji or None})
    settings["ticket_buttons"] = buttons
    save_settings(interaction.guild.id, settings)
    await reply(interaction, "تم حفظ الزر. أرسل `/ticketsetup` لإرسال اللوحة المحدثة.")


@bot.tree.command(name="ticketrole", description="تحديد رتبة لكل قسم تكت")
@admin_check()
@app_commands.describe(section_key="معرّف القسم المستخدم في زر التكت",
                       role="الرتبة التي ستشاهد تكتات القسم")
async def ticketrole(interaction: discord.Interaction, section_key: str,
                     role: discord.Role):
    settings = get_settings(interaction.guild.id)
    roles = settings.get("ticket_roles", {})
    roles[section_key] = role.id
    settings["ticket_roles"] = roles
    save_settings(interaction.guild.id, settings)
    await reply(interaction, f"تم ربط القسم `{section_key}` بالرتبة {role.mention}.")


@bot.tree.command(name="ticketcategory", description="تحديد كاتيجوري التكتات")
@admin_check()
async def ticketcategory(interaction: discord.Interaction,
                         category: discord.CategoryChannel):
    update_settings(interaction.guild.id, ticket_category=category.id)
    await reply(interaction, f"تم تحديد الكاتيجوري: **{category.name}**")


@bot.tree.command(name="ticketpreview", description="معاينة لوحة التكت")
@admin_check()
async def ticketpreview(interaction: discord.Interaction):
    settings = get_settings(interaction.guild.id)
    embed = make_embed(
        settings.get("ticket_title", "🎫 تذاكر الدعم الفني"),
        settings.get("ticket_description", "اضغط على القسم المناسب لفتح تكت.")
    )
    if settings.get("ticket_image"):
        embed.set_image(url=settings["ticket_image"])
    await reply(interaction, embed=embed, view=TicketPanelView(interaction.guild.id))


@bot.tree.command(name="ratingstats", description="إحصائيات تقييمات التكت")
@admin_check()
async def ratingstats(interaction: discord.Interaction):
    with db() as con:
        rows = con.execute(
            """SELECT rating, COUNT(*) AS total FROM ticket_ratings
               WHERE guild_id=? GROUP BY rating ORDER BY rating DESC""",
            (interaction.guild.id,)
        ).fetchall()
        total = con.execute(
            "SELECT COUNT(*) AS n FROM ticket_ratings WHERE guild_id=?",
            (interaction.guild.id,)
        ).fetchone()["n"]
        avg = con.execute(
            "SELECT AVG(rating) AS a FROM ticket_ratings WHERE guild_id=?",
            (interaction.guild.id,)
        ).fetchone()["a"]

    desc = f"عدد التقييمات: **{total}**\nالمتوسط: **{avg or 0:.2f}/5**\n\n"
    desc += "\n".join(f"**{r['rating']} ⭐:** {r['total']}" for r in rows) or "لا توجد تقييمات."
    await reply(interaction, embed=make_embed("إحصائيات تقييم التكت", desc))


# ============================================================
# WELCOME, LEAVE, AUTOROLE
# ============================================================

def welcome_text(template: str, member: discord.Member):
    guild = member.guild
    replacements = {
        "{user}": member.mention,
        "{user_name}": member.name,
        "{user_id}": str(member.id),
        "{server}": guild.name,
        "{member_count}": str(guild.member_count or 0),
        "{created}": member.created_at.strftime("%Y-%m-%d"),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


async def post_member_message(member: discord.Member, kind: str):
    settings = get_settings(member.guild.id)
    channel_id = settings.get(f"{kind}_channel")
    if not channel_id:
        return
    channel = member.guild.get_channel(int(channel_id))
    if not channel:
        return

    title = settings.get(f"{kind}_title", "أهلًا بك!" if kind == "welcome" else "إلى اللقاء")
    desc = settings.get(
        f"{kind}_description",
        "{user} نورت السيرفر! أنت العضو رقم {member_count}" if kind == "welcome"
        else "{user} غادر السيرفر."
    )
    embed = make_embed(title, welcome_text(desc, member))
    image = settings.get(f"{kind}_image")
    if image:
        embed.set_image(url=image)
    if settings.get(f"{kind}_thumbnail", True):
        embed.set_thumbnail(url=member.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


@bot.event
async def on_member_join(member: discord.Member):
    await post_member_message(member, "welcome")
    settings = get_settings(member.guild.id)
    role_id = settings.get("autorole")
    if role_id:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role, reason="Auto role")
            except discord.HTTPException:
                pass
    await send_log(member.guild, "عضو جديد", f"{member.mention} انضم للسيرفر.")


@bot.event
async def on_member_remove(member: discord.Member):
    await post_member_message(member, "leave")
    await send_log(member.guild, "مغادرة عضو", f"**{member}** غادر السيرفر.")


@bot.tree.command(name="welcomesetup", description="إعداد الترحيب والمغادرة في الروم الحالي")
@admin_check()
async def welcomesetup(interaction: discord.Interaction):
    update_settings(
        interaction.guild.id,
        welcome_channel=interaction.channel.id,
        leave_channel=interaction.channel.id
    )
    await reply(
        interaction,
        "تم تحديد روم الترحيب والمغادرة على هذا الروم.\n"
        "استخدم `/welcomeedit` لتعديل النص والصورة."
    )


@bot.tree.command(name="welcomeedit", description="تعديل إعدادات الترحيب أو المغادرة")
@admin_check()
@app_commands.describe(kind="welcome للترحيب أو leave للمغادرة",
                       title="عنوان الرسالة", description="نص الرسالة",
                       image_url="رابط الصورة، اتركه فارغًا لإزالة الصورة",
                       channel="روم إرسال الرسالة")
@app_commands.choices(kind=[
    app_commands.Choice(name="الترحيب", value="welcome"),
    app_commands.Choice(name="المغادرة", value="leave")
])
async def welcomeedit(interaction: discord.Interaction,
                      kind: app_commands.Choice[str],
                      title: str,
                      description: str,
                      image_url: str = "",
                      channel: discord.TextChannel = None):
    settings = get_settings(interaction.guild.id)
    prefix = kind.value
    settings[f"{prefix}_title"] = title[:256]
    settings[f"{prefix}_description"] = description[:4000]
    settings[f"{prefix}_image"] = image_url.strip()
    if channel:
        settings[f"{prefix}_channel"] = channel.id
    save_settings(interaction.guild.id, settings)
    await reply(
        interaction,
        "تم الحفظ. المتغيرات المتاحة: `{user}` `{user_name}` `{user_id}` "
        "`{server}` `{member_count}` `{created}`"
    )


@bot.tree.command(name="welcomepreview", description="معاينة الترحيب أو المغادرة")
@admin_check()
@app_commands.choices(kind=[
    app_commands.Choice(name="الترحيب", value="welcome"),
    app_commands.Choice(name="المغادرة", value="leave")
])
async def welcomepreview(interaction: discord.Interaction,
                         kind: app_commands.Choice[str]):
    settings = get_settings(interaction.guild.id)
    prefix = kind.value
    embed = make_embed(
        settings.get(f"{prefix}_title", "أهلًا بك!"),
        welcome_text(
            settings.get(f"{prefix}_description", "{user}"),
            interaction.user
        )
    )
    if settings.get(f"{prefix}_image"):
        embed.set_image(url=settings[f"{prefix}_image"])
    await reply(interaction, embed=embed)


@bot.tree.command(name="autorole", description="تحديد رتبة تلقائية للأعضاء الجدد")
@admin_check()
async def autorole(interaction: discord.Interaction, role: discord.Role):
    update_settings(interaction.guild.id, autorole=role.id)
    await reply(interaction, f"تم تعيين الرتبة التلقائية: {role.mention}")


@bot.tree.command(name="autoroleoff", description="إيقاف الرتبة التلقائية")
@admin_check()
async def autoroleoff(interaction: discord.Interaction):
    settings = get_settings(interaction.guild.id)
    settings.pop("autorole", None)
    save_settings(interaction.guild.id, settings)
    await reply(interaction, "تم إيقاف الرتبة التلقائية.")


# ============================================================
# SUGGESTIONS
# ============================================================

class SuggestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="موافق 0", emoji="👍", style=discord.ButtonStyle.success,
        custom_id="turki_suggest_yes"
    )
    async def yes(self, interaction: discord.Interaction,
                  button: discord.ui.Button):
        await self.vote(interaction, "yes")

    @discord.ui.button(
        label="غير موافق 0", emoji="👎", style=discord.ButtonStyle.danger,
        custom_id="turki_suggest_no"
    )
    async def no(self, interaction: discord.Interaction,
                 button: discord.ui.Button):
        await self.vote(interaction, "no")

    async def vote(self, interaction, choice):
        message = interaction.message
        if not message or not message.embeds:
            return await reply(interaction, "ما قدرت أقرأ الاقتراح.")
        embed = message.embeds[0]
        voters = getattr(self, "voters", {})
        key = (message.id, interaction.user.id)
        if key in voters:
            return await reply(interaction, "صوّت مسبقًا على هذا الاقتراح.")
        voters[key] = choice
        self.voters = voters
        yes = sum(1 for (mid, _), v in voters.items() if mid == message.id and v == "yes")
        no = sum(1 for (mid, _), v in voters.items() if mid == message.id and v == "no")
        self.children[0].label = f"موافق {yes}"
        self.children[1].label = f"غير موافق {no}"
        await interaction.response.edit_message(view=self)


@bot.tree.command(name="suggestionsetup", description="تحديد روم الاقتراحات")
@admin_check()
async def suggestionsetup(interaction: discord.Interaction,
                          channel: discord.TextChannel = None):
    channel = channel or interaction.channel
    update_settings(interaction.guild.id, suggestions_channel=channel.id)
    await reply(interaction, f"تم تحديد روم الاقتراحات: {channel.mention}")


@bot.tree.command(name="suggest", description="إرسال اقتراح")
@app_commands.describe(text="اكتب اقتراحك")
async def suggest(interaction: discord.Interaction, text: str):
    settings = get_settings(interaction.guild.id)
    channel_id = settings.get("suggestions_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
    if not channel:
        return await reply(interaction, "الإدارة لم تحدد روم الاقتراحات بعد.")

    embed = make_embed("💡 اقتراح جديد", text)
    embed.set_author(
        name=interaction.user.display_name,
        icon_url=interaction.user.display_avatar.url
    )
    embed.set_footer(text=f"الاقتراح بواسطة {interaction.user} • ID: {interaction.user.id}")
    await channel.send(embed=embed, view=SuggestionView())
    await reply(interaction, "تم إرسال اقتراحك، شكرًا لمشاركتك!")


# ============================================================
# MODERATION: WARN, KICK, BAN, TIMEOUT, PURGE, LOCK
# ============================================================

@bot.tree.command(name="warn", description="إعطاء تحذير لعضو")
@admin_check()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    with db() as con:
        con.execute(
            """INSERT INTO warnings
               (guild_id, user_id, moderator_id, reason, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (interaction.guild.id, member.id, interaction.user.id, reason, utcnow())
        )
        count = con.execute(
            "SELECT COUNT(*) AS n FROM warnings WHERE guild_id=? AND user_id=?",
            (interaction.guild.id, member.id)
        ).fetchone()["n"]

    await reply(interaction, f"تم تحذير {member.mention}.\nعدد تحذيراته: **{count}**")
    try:
        await member.send(f"تم تحذيرك في **{interaction.guild.name}**.\nالسبب: {reason}")
    except discord.HTTPException:
        pass
    await send_log(
        interaction.guild, "تحذير عضو",
        f"العضو: {member.mention}\nالإداري: {interaction.user.mention}\n"
        f"السبب: {reason}\nعدد التحذيرات: {count}"
    )


@bot.tree.command(name="warnings", description="عرض تحذيرات عضو")
@admin_check()
async def warnings(interaction: discord.Interaction, member: discord.Member):
    with db() as con:
        rows = con.execute(
            """SELECT * FROM warnings WHERE guild_id=? AND user_id=?
               ORDER BY id DESC LIMIT 15""",
            (interaction.guild.id, member.id)
        ).fetchall()

    if not rows:
        return await reply(interaction, f"ما عند {member.mention} تحذيرات مسجلة.")

    lines = []
    for row in rows:
        lines.append(
            f"**#{row['id']}** — {row['reason']}\n"
            f"بواسطة <@{row['moderator_id']}> • {row['created_at'][:10]}"
        )
    await reply(
        interaction,
        embed=make_embed(f"تحذيرات {member}", "\n\n".join(lines))
    )


@bot.tree.command(name="clearwarnings", description="مسح تحذيرات عضو")
@admin_check()
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    with db() as con:
        cur = con.execute(
            "DELETE FROM warnings WHERE guild_id=? AND user_id=?",
            (interaction.guild.id, member.id)
        )
        deleted = cur.rowcount
    await reply(interaction, f"تم مسح **{deleted}** تحذيرًا من {member.mention}.")
    await send_log(
        interaction.guild, "مسح التحذيرات",
        f"العضو: {member.mention}\nبواسطة: {interaction.user.mention}"
    )


@bot.tree.command(name="kick", description="طرد عضو")
@admin_check()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "لم يحدد"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await reply(interaction, "رتبة هذا العضو أعلى من رتبتك أو مساوية لها.")
    try:
        await member.kick(reason=f"{reason} | By {interaction.user}")
        await reply(interaction, f"تم طرد **{member}**.\nالسبب: {reason}")
        await send_log(interaction.guild, "طرد عضو", f"{member} — {reason}")
    except discord.HTTPException as exc:
        await reply(interaction, f"فشل الطرد: {exc}")


@bot.tree.command(name="ban", description="حظر عضو")
@admin_check()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "لم يحدد"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await reply(interaction, "رتبة هذا العضو أعلى من رتبتك أو مساوية لها.")
    try:
        await member.ban(reason=f"{reason} | By {interaction.user}")
        await reply(interaction, f"تم حظر **{member}**.\nالسبب: {reason}")
        await send_log(interaction.guild, "حظر عضو", f"{member} — {reason}")
    except discord.HTTPException as exc:
        await reply(interaction, f"فشل الحظر: {exc}")


@bot.tree.command(name="timeout", description="إعطاء عضو تايم أوت بالدقائق")
@admin_check()
@app_commands.describe(minutes="المدة بالدقائق، بحد أقصى 40320 دقيقة")
async def timeout_member(interaction: discord.Interaction,
                         member: discord.Member,
                         minutes: app_commands.Range[int, 1, 40320],
                         reason: str = "لم يحدد"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        return await reply(interaction, "رتبة هذا العضو أعلى من رتبتك أو مساوية لها.")
    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await reply(
            interaction,
            f"تم إعطاء {member.mention} تايم أوت لمدة **{minutes} دقيقة**.\nالسبب: {reason}"
        )
        await send_log(
            interaction.guild, "تايم أوت",
            f"{member.mention}\nالمدة: {minutes} دقيقة\nالسبب: {reason}"
        )
    except discord.HTTPException as exc:
        await reply(interaction, f"فشل التايم أوت: {exc}")


@bot.tree.command(name="purge", description="مسح عدد من الرسائل")
@admin_check()
@app_commands.describe(amount="عدد الرسائل من 1 إلى 100")
async def purge(interaction: discord.Interaction,
                amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"تم مسح **{len(deleted)}** رسالة.", ephemeral=True)
    await send_log(
        interaction.guild, "مسح رسائل",
        f"الروم: {interaction.channel.mention}\n"
        f"العدد: {len(deleted)}\nبواسطة: {interaction.user.mention}"
    )


@bot.tree.command(name="lock", description="قفل الروم الحالي")
@admin_check()
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await reply(interaction, "🔒 تم قفل الروم.")
    await send_log(interaction.guild, "قفل روم", interaction.channel.mention)


@bot.tree.command(name="unlock", description="فتح الروم الحالي")
@admin_check()
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await reply(interaction, "🔓 تم فتح الروم.")
    await send_log(interaction.guild, "فتح روم", interaction.channel.mention)


@bot.tree.command(name="setlogs", description="تحديد روم سجلات الإدارة")
@admin_check()
async def setlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    update_settings(interaction.guild.id, logs_channel=channel.id)
    await reply(interaction, f"تم تحديد روم السجلات: {channel.mention}")


# ============================================================
# PRIVATE ANNOUNCEMENTS: SELECT MEMBERS, WRITE, CONFIRM
# ============================================================

class AnnouncementModal(discord.ui.Modal, title="إرسال إعلان خاص"):
    title_input = discord.ui.TextInput(
        label="عنوان الإعلان", max_length=256, required=True
    )
    body_input = discord.ui.TextInput(
        label="نص الإعلان",
        style=discord.TextStyle.paragraph,
        max_length=3500,
        required=True
    )

    def __init__(self, recipients):
        super().__init__()
        self.recipients = recipients

    async def on_submit(self, interaction: discord.Interaction):
        view = AnnouncementConfirmView(
            str(self.title_input.value),
            str(self.body_input.value),
            self.recipients
        )
        await interaction.response.send_message(
            f"معاينة الإعلان لعدد **{len(self.recipients)}** عضوًا:",
            embed=view.build_embed(),
            view=view,
            ephemeral=True
        )


class AnnouncementConfirmView(discord.ui.View):
    def __init__(self, title, body, recipients):
        super().__init__(timeout=300)
        self.title_text = title
        self.body_text = body
        self.recipients = recipients

    def build_embed(self):
        return make_embed(self.title_text, self.body_text)

    @discord.ui.button(label="تأكيد الإرسال", emoji="📨",
                       style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        sent = 0
        failed = 0
        embed = self.build_embed()
        for user in self.recipients:
            try:
                await user.send(embed=embed)
                sent += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
            await asyncio.sleep(0.15)

        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(
            f"انتهى الإرسال.\nتم الإرسال: **{sent}**\nتعذر الإرسال: **{failed}**",
            ephemeral=True
        )
        await send_log(
            interaction.guild, "إعلان خاص",
            f"بواسطة: {interaction.user.mention}\nنجح: {sent}\nتعذر: {failed}"
        )

    @discord.ui.button(label="إلغاء", emoji="✖️",
                       style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="تم إلغاء الإعلان.", view=self)


class AnnouncementMemberSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="اختر الأعضاء الذين سيصلهم الإعلان",
            min_values=1,
            max_values=25
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            AnnouncementModal(list(self.values))
        )


class AnnouncementSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(AnnouncementMemberSelect())


@bot.tree.command(name="announce", description="إرسال إعلان خاص لأعضاء تختارهم")
@admin_check()
async def announce(interaction: discord.Interaction):
    await reply(
        interaction,
        "اختر الأعضاء من القائمة. يمكنك اختيار 25 عضوًا كحد أقصى في كل مرة.",
        view=AnnouncementSelectView()
    )


# ============================================================
# TIKTOK NOTIFICATIONS VIA RSS
# ============================================================

def fetch_tiktok_feed(username: str):
    url = f"https://rsshub.app/tiktok/user/{quote(username)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="TikTok video")
        link = item.findtext("link", default="")
        guid = item.findtext("guid", default=link)
        if link:
            items.append({"title": title, "link": link, "guid": guid})
    return items


@bot.tree.command(name="tiktoksetup", description="تفعيل إشعارات حساب تيك توك")
@admin_check()
@app_commands.describe(username="اسم الحساب بدون @",
                       channel="روم إرسال الإشعارات")
async def tiktoksetup(interaction: discord.Interaction,
                      username: str,
                      channel: discord.TextChannel):
    username = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._]{2,40}", username):
        return await reply(interaction, "اسم الحساب غير صالح.")

    settings = get_settings(interaction.guild.id)
    feeds = settings.get("tiktok_feeds", {})
    feeds[username.lower()] = {
        "username": username,
        "channel_id": channel.id,
        "last_guid": ""
    }
    settings["tiktok_feeds"] = feeds
    save_settings(interaction.guild.id, settings)
    await reply(interaction, f"تم إعداد إشعارات @{username} في {channel.mention}.")


@bot.tree.command(name="tiktokoff", description="إيقاف إشعارات حساب تيك توك")
@admin_check()
async def tiktokoff(interaction: discord.Interaction, username: str):
    settings = get_settings(interaction.guild.id)
    feeds = settings.get("tiktok_feeds", {})
    username = username.strip().lstrip("@").lower()
    if username not in feeds:
        return await reply(interaction, "هذا الحساب غير مضاف.")
    feeds.pop(username)
    settings["tiktok_feeds"] = feeds
    save_settings(interaction.guild.id, settings)
    await reply(interaction, f"تم إيقاف إشعارات @{username}.")


@tasks.loop(minutes=5)
async def tiktok_poll():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        settings = get_settings(guild.id)
        feeds = settings.get("tiktok_feeds", {})
        changed = False

        for key, feed in list(feeds.items()):
            try:
                items = await asyncio.to_thread(
                    fetch_tiktok_feed, feed["username"]
                )
            except Exception as exc:
                print(f"TikTok feed error ({key}): {exc}")
                continue

            if not items:
                continue

            newest = items[0]
            last_guid = feed.get("last_guid", "")

            if not last_guid:
                feed["last_guid"] = newest["guid"]
                changed = True
                continue

            new_items = []
            for item in items:
                if item["guid"] == last_guid:
                    break
                new_items.append(item)

            channel = guild.get_channel(int(feed["channel_id"]))
            if channel:
                for item in reversed(new_items[:5]):
                    embed = make_embed(
                        f"🎵 فيديو جديد من @{feed['username']}",
                        f"[شاهد الفيديو على تيك توك]({item['link']})\n{item['title']}"
                    )
                    try:
                        await channel.send(embed=embed)
                    except discord.HTTPException:
                        pass

            if new_items:
                feed["last_guid"] = newest["guid"]
                changed = True

        if changed:
            settings["tiktok_feeds"] = feeds
            save_settings(guild.id, settings)


@tiktok_poll.before_loop
async def before_tiktok_poll():
    await bot.wait_until_ready()


# ============================================================
# SERVER / USER INFO / AVATAR / HELP
# ============================================================

@bot.tree.command(name="serverinfo", description="معلومات السيرفر")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = make_embed(f"معلومات {guild.name}")
    embed.add_field(name="المالك", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="الأعضاء", value=str(guild.member_count), inline=True)
    embed.add_field(name="الرومات", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="الرتب", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="تاريخ الإنشاء", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await reply(interaction, embed=embed, ephemeral=False)


@bot.tree.command(name="userinfo", description="معلومات عضو")
async def userinfo(interaction: discord.Interaction,
                   member: discord.Member = None):
    member = member or interaction.user
    embed = make_embed(f"معلومات {member}")
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="الاسم", value=member.mention, inline=True)
    embed.add_field(name="ID", value=str(member.id), inline=True)
    embed.add_field(
        name="انضم للسيرفر",
        value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "غير معروف",
        inline=True
    )
    embed.add_field(
        name="تاريخ إنشاء الحساب",
        value=member.created_at.strftime("%Y-%m-%d"),
        inline=True
    )
    roles = [role.mention for role in member.roles if role != interaction.guild.default_role]
    embed.add_field(
        name=f"الرتب ({len(roles)})",
        value=" ".join(roles[:15]) or "لا توجد",
        inline=False
    )
    await reply(interaction, embed=embed, ephemeral=False)


@bot.tree.command(name="avatar", description="عرض صورة عضو")
async def avatar(interaction: discord.Interaction,
                 member: discord.Member = None):
    member = member or interaction.user
    embed = make_embed(f"صورة {member.display_name}")
    embed.set_image(url=member.display_avatar.url)
    await reply(interaction, embed=embed, ephemeral=False)


@bot.tree.command(name="helpme", description="عرض أوامر البوت")
async def helpme(interaction: discord.Interaction):
    embed = make_embed(
        "📚 أوامر TURKI SYSTEMS",
        "قائمة بأهم أوامر البوت. الأوامر الإدارية تتطلب الصلاحيات المناسبة."
    )
    embed.add_field(
        name="🎫 التكت",
        value="`/ticketsetup` `/ticketedit` `/ticketbutton` `/ticketrole` "
              "`/ticketcategory` `/ticketpreview` `/ratingstats`",
        inline=False
    )
    embed.add_field(
        name="👋 الترحيب",
        value="`/welcomesetup` `/welcomeedit` `/welcomepreview` "
              "`/autorole` `/autoroleoff`",
        inline=False
    )
    embed.add_field(
        name="💡 الاقتراحات",
        value="`/suggestionsetup` `/suggest`",
        inline=False
    )
    embed.add_field(
        name="🛡️ الإدارة",
        value="`/warn` `/warnings` `/clearwarnings` `/kick` `/ban` "
              "`/timeout` `/purge` `/lock` `/unlock` `/setlogs` `/announce`",
        inline=False
    )
    embed.add_field(
        name="📱 تيك توك",
        value="`/tiktoksetup` `/tiktokoff`",
        inline=False
    )
    embed.add_field(
        name="🎵 الموسيقى",
        value="`/ادخل` `/شغل` `/وقف` `/كمل` `/س` `/قائمة` `/اخرج`",
        inline=False
    )
    embed.add_field(
        name="ℹ️ معلومات",
        value="`/serverinfo` `/userinfo` `/avatar` `/helpme`",
        inline=False
    )
    await reply(interaction, embed=embed, ephemeral=False)


# ============================================================
# MUSIC SYSTEM (Optimized for Stability & Direct Play)
# ============================================================

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "cookiefile": None,
    "socket_timeout": 30,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
music_queues = defaultdict(deque)
music_now = {}
music_locks = defaultdict(asyncio.Lock)
music_generations = defaultdict(int)


async def ensure_voice(interaction: discord.Interaction):
    if not interaction.guild:
        await reply(interaction, "استخدم أمر الموسيقى داخل السيرفر.")
        return None

    if not interaction.user.voice or not interaction.user.voice.channel:
        await reply(interaction, "ادخل روم صوتي أولًا.")
        return None

    voice = interaction.guild.voice_client
    target = interaction.user.voice.channel

    try:
        if voice and voice.is_connected():
            if voice.channel != target:
                await voice.move_to(target)
        else:
            voice = await target.connect()
    except (discord.HTTPException, asyncio.TimeoutError) as exc:
        await reply(interaction, f"ما قدرت أدخل الروم الصوتي: {exc}")
        return None

    return voice


async def extract_song(query: str):
    def _extract():
        search_query = query if query.startswith("http") else f"ytsearch:{query}"
        info = ytdl.extract_info(search_query, download=False)
        if "entries" in info:
            entries = [entry for entry in info["entries"] if entry]
            if not entries:
                return None
            info = entries[0]

        return {
            "title": info.get("title", "مقطع غير معروف"),
            "url": info.get("url"),
            "webpage_url": info.get("webpage_url", query),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
        }

    return await asyncio.to_thread(_extract)


def format_duration(seconds):
    if not seconds:
        return "غير معروف"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


async def music_play_next(guild_id: int, expected_generation=None):
    async with music_locks[guild_id]:
        if expected_generation is not None:
            if expected_generation != music_generations[guild_id]:
                return

        guild = bot.get_guild(guild_id)
        if not guild:
            return
        voice = guild.voice_client
        if not voice or not voice.is_connected() or voice.is_playing() or voice.is_paused():
            return

        if not music_queues[guild_id]:
            music_now.pop(guild_id, None)
            return

        track = music_queues[guild_id].popleft()
        music_now[guild_id] = track

        try:
            refreshed = await extract_song(track["webpage_url"])
            if refreshed and refreshed.get("url"):
                track.update(refreshed)
        except Exception as exc:
            print(f"Could not refresh music stream: {exc}")

        if not track.get("url"):
            music_now.pop(guild_id, None)
            bot.loop.call_soon(
                lambda: asyncio.create_task(music_play_next(guild_id))
            )
            return

        try:
            source = discord.FFmpegPCMAudio(
                track["url"], **FFMPEG_OPTIONS
            )
            source = discord.PCMVolumeTransformer(source, volume=0.5)
        except Exception as exc:
            print(f"FFmpeg source error: {exc}")
            music_now.pop(guild_id, None)
            bot.loop.call_soon(
                lambda: asyncio.create_task(music_play_next(guild_id))
            )
            return

        generation = music_generations[guild_id]

        def after_play(error):
            if error:
                print(f"Music playback error: {error}")
            try:
                asyncio.run_coroutine_threadsafe(
                    music_play_next(guild_id, generation),
                    bot.loop
                )
            except RuntimeError:
                pass

        try:
            voice.play(source, after=after_play)
        except Exception as exc:
            print(f"Voice playback error: {exc}")
            music_now.pop(guild_id, None)
            bot.loop.call_soon(
                lambda: asyncio.create_task(music_play_next(guild_id))
            )


@bot.tree.command(name="ادخل", description="دخول الروم الصوتي")
async def music_join(interaction: discord.Interaction):
    voice = await ensure_voice(interaction)
    if voice:
        await reply(interaction, f"دخلت الروم الصوتي: **{voice.channel.name}**")


@bot.tree.command(name="شغل", description="تشغيل أغنية باسمها أو رابطها (يدعم يوتيوب وساوندكلاود)")
@app_commands.describe(query="اسم الأغنية أو الرابط المباشر")
async def music_play(interaction: discord.Interaction, query: str):
    voice = await ensure_voice(interaction)
    if not voice:
        return

    await interaction.response.defer(thinking=True)

    try:
        track = await extract_song(query)
    except Exception as exc:
        return await interaction.followup.send(
            f"ما قدرت أجيب الأغنية. جرب استخدام رابط مباشر أو اسم مختلف.\n`{str(exc)[:200]}`",
            ephemeral=True
        )

    if not track or not track.get("url"):
        return await interaction.followup.send("ما لقيت الأغنية المطلوبة، تأكد من صحة الرابط أو الاسم.", ephemeral=True)

    track["requested_by"] = interaction.user.id
    guild_id = interaction.guild.id

    if voice.is_playing() or voice.is_paused() or music_now.get(guild_id):
        music_queues[guild_id].append(track)
        embed = make_embed(
            "🎶 تمت إضافة الأغنية للقائمة",
            f"**[{track['title']}]({track['webpage_url']})**\n"
            f"المدة: `{format_duration(track.get('duration'))}`\n"
            f"الترتيب: **{len(music_queues[guild_id])}**"
        )
        if track.get("thumbnail"):
            embed.set_thumbnail(url=track["thumbnail"])
        await interaction.followup.send(embed=embed)
    else:
        music_queues[guild_id].appendleft(track)
        await music_play_next(guild_id)
        embed = make_embed(
            "▶️ جاري تشغيل الأغنية",
            f"**[{track['title']}]({track['webpage_url']})**\n"
            f"المدة: `{format_duration(track.get('duration'))}`"
        )
        if track.get("thumbnail"):
            embed.set_thumbnail(url=track["thumbnail"])
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="وقف", description="إيقاف الأغنية مؤقتًا")
async def music_pause(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice or not voice.is_playing():
        return await reply(interaction, "ما فيه أغنية شغالة حاليًا.")
    voice.pause()
    await reply(interaction, "⏸️ تم إيقاف الأغنية مؤقتًا.")


@bot.tree.command(name="كمل", description="تكملة الأغنية")
async def music_resume(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice or not voice.is_paused():
        return await reply(interaction, "ما فيه أغنية متوقفة مؤقتًا.")
    voice.resume()
    await reply(interaction, "▶️ تم استئناف الأغنية.")


@bot.tree.command(name="س", description="تخطي الأغنية الحالية")
async def music_skip(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice or not (voice.is_playing() or voice.is_paused()):
        return await reply(interaction, "ما فيه أغنية شغالة لتخطيها.")
    voice.stop()
    await reply(interaction, "⏭️ تم تخطي الأغنية.")


@bot.tree.command(name="قائمة", description="عرض قائمة انتظار الأغاني")
async def music_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    current = music_now.get(guild_id)
    queue = list(music_queues[guild_id])

    if not current and not queue:
        return await reply(interaction, "قائمة الأغاني فارغة.")

    lines = []
    if current:
        lines.append(
            f"**تعمل الآن:** [{current['title']}]({current['webpage_url']}) "
            f"— `{format_duration(current.get('duration'))}`"
        )

    for index, track in enumerate(queue[:15], start=1):
        lines.append(
            f"**{index}.** [{track['title']}]({track['webpage_url']}) "
            f"— `{format_duration(track.get('duration'))}`"
        )

    if len(queue) > 15:
        lines.append(f"... و{len(queue) - 15} أغنية أخرى.")

    await reply(
        interaction,
        embed=make_embed("🎵 قائمة الأغاني", "\n".join(lines)),
        ephemeral=False
    )


@bot.tree.command(name="اخرج", description="إيقاف الموسيقى والخروج من الروم")
async def music_leave(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice:
        return await reply(interaction, "البوت ليس في روم صوتي.")

    music_generations[interaction.guild.id] += 1
    music_queues[interaction.guild.id].clear()
    music_now.pop(interaction.guild.id, None)

    try:
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        await voice.disconnect(force=True)
    except discord.HTTPException:
        pass

    await reply(interaction, "👋 خرجت من الروم الصوتي وتم مسح قائمة الأغاني.")


# ============================================================
# EVENTS, PERSISTENT VIEWS, SLASH COMMAND SYNC
# ============================================================

@bot.event
async def on_ready():
    setup_db()

    bot.add_view(TicketControlsView())
    bot.add_view(SuggestionView())

    for guild in bot.guilds:
        try:
            bot.add_view(TicketPanelView(guild.id))
        except Exception as exc:
            print(f"Could not restore ticket panel view: {exc}")

    with db() as con:
        ticket_rows = con.execute(
            "SELECT guild_id, channel_id, user_id FROM tickets"
        ).fetchall()

    seen = set()
    for row in ticket_rows:
        key = (row["guild_id"], row["channel_id"])
        if key not in seen:
            seen.add(key)
            try:
                bot.add_view(TicketRatingView(int(row["guild_id"]), int(row["channel_id"])))
            except Exception:
                pass

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as exc:
        print(f"Slash command sync failed: {exc}")

    if not tiktok_poll.is_running():
        tiktok_poll.start()

    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "ما عندك الصلاحيات المطلوبة لاستخدام هذا الأمر."
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = "انتظر قليلًا قبل استخدام الأمر مرة أخرى."
    else:
        original = getattr(error, "original", error)
        print(f"Slash command error: {original}")
        message = "صار خطأ أثناء تنفيذ الأمر. تحقق من صلاحيات البوت والإعدادات."

    try:
        await reply(interaction, message)
    except discord.HTTPException:
        pass


# ============================================================
# START
# ============================================================

setup_db()

if not TOKEN:
    raise RuntimeError(
        "لم يتم العثور على DISCORD_TOKEN. أضفه في إعدادات البيئة باسم DISCORD_TOKEN."
    )

bot.run(TOKEN)
