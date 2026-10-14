import os
import json
import sqlite3
import re
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = "turki_systems.db"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ==================== قاعدة البيانات ====================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT,
                user_id TEXT,
                moderator_id TEXT,
                reason TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id TEXT PRIMARY KEY,
                guild_id TEXT,
                user_id TEXT,
                status TEXT,
                created_at TEXT
            )
        """)


def default_settings():
    return {
        "ticket_channel": None,
        "ticket_category": None,
        "ticket_title": "🎫 نظام التذاكر",
        "ticket_description":
            "اختر نوع التذكرة من الأزرار بالأسفل وسيتم فتح تذكرة خاصة بك.",
        "ticket_image": "",
        "ticket_color": "8B5CF6",
        "ticket_buttons": [
            {
                "name": "الدعم الفني",
                "category": None,
                "emoji": "🛠️",
                "color": "primary"
            },
            {
                "name": "شكوى",
                "category": None,
                "emoji": "📩",
                "color": "secondary"
            },
            {
                "name": "استفسار",
                "category": None,
                "emoji": "❓",
                "color": "success"
            },
        ],
        "ticket_counter": 0,
        "welcome_channel": None,
        "welcome_text":
            "أهلًا {mention} في **{server}**! أنت العضو رقم **{count}** 🎉",
        "welcome_image": "",
        "welcome_color": "8B5CF6",
        "leave_channel": None,
        "leave_text": "غادر {user} السيرفر. نتمنا نشوفك مرة ثانية.",
        "leave_image": "",
        "leave_color": "808080",
        "suggestion_channel": None,
        "log_channel": None,
    }


def get_settings(guild_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT data FROM settings WHERE guild_id=?",
            (str(guild_id),)
        ).fetchone()

    data = default_settings()

    if row:
        try:
            data.update(json.loads(row["data"]))
        except (ValueError, TypeError):
            pass

    return data


def save_settings(guild_id: int, data: dict):
    with db() as conn:
        conn.execute(
            """
            INSERT INTO settings(guild_id, data)
            VALUES(?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET data=excluded.data
            """,
            (str(guild_id), json.dumps(data, ensure_ascii=False))
        )


def parse_color(value: str, fallback: int = 0x8B5CF6):
    try:
        return discord.Color(int(value.strip().replace("#", ""), 16))
    except (ValueError, AttributeError):
        return discord.Color(fallback)


def safe_name(value: str):
    value = re.sub(
        r"[^a-zA-Z0-9\u0600-\u06FF_-]",
        "-",
        value.strip().lower()
    )
    return value[:70] or "ticket"


def is_http_url(value: str):
    return value.startswith("https://") or value.startswith("http://")


def can_manage(interaction: discord.Interaction):
    permissions = interaction.user.guild_permissions
    return bool(
        permissions.manage_guild or permissions.administrator
    )


async def admin_check(interaction: discord.Interaction):
    if not can_manage(interaction):
        await interaction.response.send_message(
            "❌ تحتاج صلاحية **إدارة السيرفر** لاستخدام هذا الأمر.",
            ephemeral=True
        )
        return False
    return True


async def send_log(guild: discord.Guild, text: str):
    settings = get_settings(guild.id)
    channel_id = settings.get("log_channel")

    if not channel_id:
        return

    channel = guild.get_channel(int(channel_id))

    if channel:
        try:
            await channel.send(text)
        except discord.HTTPException:
            pass


# ==================== نظام التكت ====================

class TicketOpenButton(discord.ui.Button):
    def __init__(self, button_data: dict, index: int):
        styles = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }

        self.button_name = button_data.get("name", "تذكرة")
        self.category_id = button_data.get("category")
        custom_slug = safe_name(self.button_name)[:45]

        super().__init__(
            label=self.button_name[:80],
            emoji=button_data.get("emoji") or None,
            style=styles.get(
                button_data.get("color", "primary"),
                discord.ButtonStyle.primary
            ),
            custom_id=f"ticket:open:{index}:{custom_slug}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(
            interaction.user, discord.Member
        ):
            return await interaction.response.send_message(
                "هذا الزر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )

        guild = interaction.guild
        settings = get_settings(guild.id)

        with db() as conn:
            row = conn.execute(
                """
                SELECT channel_id FROM tickets
                WHERE guild_id=? AND user_id=? AND status='open'
                """,
                (str(guild.id), str(interaction.user.id))
            ).fetchone()

        if row:
            existing = guild.get_channel(int(row["channel_id"]))
            if existing:
                return await interaction.response.send_message(
                    f"عندك تذكرة مفتوحة بالفعل: {existing.mention}",
                    ephemeral=True
                )

        category = None
        category_id = (
            self.category_id or settings.get("ticket_category")
        )

        if category_id:
            category = guild.get_channel(int(category_id))
            if not isinstance(category, discord.CategoryChannel):
                category = None

        overwrites = {
            guild.default_role:
                discord.PermissionOverwrite(view_channel=False),
            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True
                ),
        }

        bot_member = guild.me
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )

        for role in guild.roles:
            if (
                role.permissions.administrator
                or role.permissions.manage_channels
            ):
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        settings["ticket_counter"] = (
            int(settings.get("ticket_counter", 0)) + 1
        )
        save_settings(guild.id, settings)

        channel_name = (
            f"{safe_name(self.button_name)}-"
            f"{settings['ticket_counter']:04d}"
        )

        try:
            channel = await guild.create_text_channel(
                channel_name[:95],
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ ما عندي صلاحية إنشاء الرومات. أعطني Manage Channels.",
                ephemeral=True
            )

        with db() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tickets
                (channel_id, guild_id, user_id, status, created_at)
                VALUES(?, ?, ?, 'open', ?)
                """,
                (
                    str(channel.id),
                    str(guild.id),
                    str(interaction.user.id),
                    datetime.now(timezone.utc).isoformat()
                )
            )

        embed = discord.Embed(
            title=f"🎫 {self.button_name}",
            description=(
                f"أهلًا {interaction.user.mention}، اشرح لنا طلبك "
                "وسيكون فريق الإدارة بمساعدتك.\n\n"
                "عند الانتهاء اضغط زر **إغلاق التذكرة**."
            ),
            color=parse_color(
                settings.get("ticket_color", "8B5CF6")
            ),
        )

        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=TicketCloseView()
        )

        await interaction.response.send_message(
            f"تم فتح تذكرتك: {channel.mention}",
            ephemeral=True
        )

        await send_log(
            guild,
            f"🎫 فُتحت تذكرة {channel.mention} بواسطة "
            f"{interaction.user.mention} — النوع: **{self.button_name}**"
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, buttons: list[dict]):
        super().__init__(timeout=None)

        for index, button_data in enumerate(buttons[:25]):
            self.add_item(TicketOpenButton(button_data, index))


class TicketCloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="إغلاق التذكرة",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:close"
        )

    async def callback(self, interaction: discord.Interaction):
        if (
            not interaction.guild
            or not isinstance(interaction.channel, discord.TextChannel)
        ):
            return await interaction.response.send_message(
                "هذا الزر يعمل داخل روم التذكرة فقط.",
                ephemeral=True
            )

        with db() as conn:
            row = conn.execute(
                """
                SELECT user_id FROM tickets
                WHERE channel_id=? AND status='open'
                """,
                (str(interaction.channel.id),)
            ).fetchone()

        if not row:
            return await interaction.response.send_message(
                "ما لقيت تذكرة مفتوحة مرتبطة بهذا الروم.",
                ephemeral=True
            )

        is_owner = str(interaction.user.id) == row["user_id"]
        is_staff = (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.administrator
        )

        if not is_owner and not is_staff:
            return await interaction.response.send_message(
                "❌ صاحب التذكرة أو الإدارة فقط يقدرون يقفلونها.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "🔒 سيتم إغلاق التذكرة خلال 5 ثوانٍ.",
            ephemeral=True
        )

        with db() as conn:
            conn.execute(
                "UPDATE tickets SET status='closed' WHERE channel_id=?",
                (str(interaction.channel.id),)
            )

        await send_log(
            interaction.guild,
            f"🔒 أُغلقت التذكرة **{interaction.channel.name}** "
            f"بواسطة {interaction.user.mention}"
        )

        await asyncio.sleep(5)

        try:
            await interaction.channel.delete(
                reason=f"Ticket closed by {interaction.user}"
            )
        except discord.HTTPException:
            pass


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCloseButton())


# ==================== الاقتراحات ====================

class SuggestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SuggestionVoteButton("👍", "suggest:up"))
        self.add_item(SuggestionVoteButton("👎", "suggest:down"))


class SuggestionVoteButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.message or not interaction.message.embeds:
            return await interaction.response.send_message(
                "ما قدرت ألقى الاقتراح.",
                ephemeral=True
            )

        embed = interaction.message.embeds[0]
        key = (
            "👍 مؤيدون"
            if self.custom_id == "suggest:up"
            else "👎 غير مؤيدين"
        )

        current = 0
        for field in embed.fields:
            if field.name == key:
                try:
                    current = int(field.value)
                except ValueError:
                    pass

        footer = embed.footer.text or ""
        marker = (
            f"|v:{interaction.user.id}:"
            f"{self.custom_id.split(':')[1]}"
        )

        if marker in footer:
            return await interaction.response.send_message(
                "صوّتّ على هذا الاقتراح من قبل.",
                ephemeral=True
            )

        other_vote = (
            "down" if self.custom_id.endswith("up") else "up"
        )
        other_marker = f"|v:{interaction.user.id}:{other_vote}"

        if other_marker in footer:
            return await interaction.response.send_message(
                "سبق وصوّتّ لهذا الاقتراح.",
                ephemeral=True
            )

        field_index = 0 if key == "👍 مؤيدون" else 1
        embed.set_field_at(
            field_index,
            name=key,
            value=str(current + 1),
            inline=True
        )
        embed.set_footer(text=(footer + marker)[-2000:])

        await interaction.response.edit_message(
            embed=embed,
            view=self.view
        )


# ==================== أحداث البوت ====================

@bot.event
async def on_ready():
    init_db()

    bot.add_view(TicketCloseView())
    bot.add_view(SuggestionView())

    with db() as conn:
        rows = conn.execute(
            "SELECT guild_id, data FROM settings"
        ).fetchall()

    for row in rows:
        try:
            data = json.loads(row["data"])
            if data.get("ticket_channel"):
                bot.add_view(
                    TicketPanelView(data.get("ticket_buttons", []))
                )
        except (ValueError, TypeError):
            continue

    try:
        guild_id = int(os.getenv("GUILD_ID", "0"))

        if guild_id:
            guild_obj = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild_obj)
            await bot.tree.sync(guild=guild_obj)
        else:
            await bot.tree.sync()

    except Exception as exc:
        print(f"Slash command sync error: {exc}")

    print(f"Logged in as {bot.user} | TURKI SYSTEMS is online")


@bot.event
async def on_member_join(member: discord.Member):
    settings = get_settings(member.guild.id)
    channel_id = settings.get("welcome_channel")

    if not channel_id:
        return

    channel = member.guild.get_channel(int(channel_id))
    if not channel:
        return

    text = settings.get(
        "welcome_text",
        "أهلًا {mention} في {server}!"
    )

    text = (
        text.replace("{mention}", member.mention)
        .replace("{user}", str(member))
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or 0))
    )

    embed = discord.Embed(
        description=text,
        color=parse_color(settings.get("welcome_color", "8B5CF6"))
    )

    image_url = settings.get("welcome_image", "")
    if image_url and is_http_url(image_url):
        embed.set_image(url=image_url)

    embed.set_thumbnail(url=member.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


@bot.event
async def on_member_remove(member: discord.Member):
    settings = get_settings(member.guild.id)
    channel_id = settings.get("leave_channel")

    if not channel_id:
        return

    channel = member.guild.get_channel(int(channel_id))
    if not channel:
        return

    text = settings.get(
        "leave_text",
        "غادر {user} السيرفر."
    )

    text = (
        text.replace("{mention}", member.mention)
        .replace("{user}", str(member))
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or 0))
    )

    embed = discord.Embed(
        description=text,
        color=parse_color(settings.get("leave_color", "808080"))
    )

    image_url = settings.get("leave_image", "")
    if image_url and is_http_url(image_url):
        embed.set_image(url=image_url)

    embed.set_thumbnail(url=member.display_avatar.url)

    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


# ==================== أوامر إعداد التكت ====================

@bot.tree.command(
    name="ticketsetup",
    description="إرسال لوحة التذاكر في روم تختاره"
)
@app_commands.describe(
    channel="الروم الذي تريد إرسال لوحة التكت فيه",
    category="تصنيف رومات التذاكر الافتراضي (اختياري)"
)
async def ticketsetup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    category: discord.CategoryChannel | None = None
):
    if not await admin_check(interaction):
        return

    settings = get_settings(interaction.guild_id)
    settings["ticket_channel"] = channel.id
    settings["ticket_category"] = category.id if category else None
    save_settings(interaction.guild_id, settings)

    embed = discord.Embed(
        title=settings["ticket_title"],
        description=settings["ticket_description"],
        color=parse_color(settings["ticket_color"])
    )

    if settings.get("ticket_image") and is_http_url(
        settings["ticket_image"]
    ):
        embed.set_image(url=settings["ticket_image"])

    await channel.send(
        embed=embed,
        view=TicketPanelView(settings["ticket_buttons"])
    )

    await interaction.response.send_message(
        f"✅ تم إرسال لوحة التكت في {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(
    name="ticketedit",
    description="تعديل عنوان ووصف وصورة ولون لوحة التكت"
)
@app_commands.describe(
    title="عنوان اللوحة",
    description="وصف اللوحة",
    image="رابط صورة مباشر أو remove لحذفها",
    color="لون HEX مثل 8B5CF6"
)
async def ticketedit(
    interaction: discord.Interaction,
    title: str | None = None,
    description: str | None = None,
    image: str | None = None,
    color: str | None = None
):
    if not await admin_check(interaction):
        return

    settings = get_settings(interaction.guild_id)

    if title is not None:
        settings["ticket_title"] = title[:256]

    if description is not None:
        settings["ticket_description"] = description[:4000]

    if image is not None:
        if image.lower() in ("remove", "delete", "حذف", "إزالة"):
            settings["ticket_image"] = ""
        elif is_http_url(image):
            settings["ticket_image"] = image
        else:
            return await interaction.response.send_message(
                "أرسل رابط صورة يبدأ بـ https:// أو اكتب `remove` لحذفها.",
                ephemeral=True
            )

    if color is not None:
        settings["ticket_color"] = color.replace("#", "")

    save_settings(interaction.guild_id, settings)

    embed = discord.Embed(
        title=settings["ticket_title"],
        description=settings["ticket_description"],
        color=parse_color(settings["ticket_color"])
    )

    if settings.get("ticket_image") and is_http_url(
        settings["ticket_image"]
    ):
        embed.set_image(url=settings["ticket_image"])

    await interaction.response.send_message(
        "✅ تم حفظ إعدادات لوحة التكت. استخدم `/ticketsetup` "
        "لإرسال لوحة محدثة.",
        embed=embed,
        ephemeral=True
    )


@bot.tree.command(
    name="ticketbutton",
    description="إضافة أو حذف زر نوع تكت"
)
@app_commands.describe(
    action="إضافة زر أو حذف زر",
    name="اسم الزر",
    emoji="إيموجي الزر",
    color="لون الزر",
    category="تصنيف رومات هذا النوع، اختياري"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="إضافة زر", value="add"),
        app_commands.Choice(name="حذف زر بالاسم", value="remove")
    ],
    color=[
        app_commands.Choice(name="أزرق", value="primary"),
        app_commands.Choice(name="رمادي", value="secondary"),
        app_commands.Choice(name="أخضر", value="success"),
        app_commands.Choice(name="أحمر", value="danger")
    ]
)
async def ticketbutton(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    name: str,
    emoji: str | None = None,
    color: app_commands.Choice[str] | None = None,
    category: discord.CategoryChannel | None = None
):
    if not await admin_check(interaction):
        return

    settings = get_settings(interaction.guild_id)
    buttons = settings.get("ticket_buttons", [])

    if action.value == "add":
        if len(buttons) >= 25:
            return await interaction.response.send_message(
                "وصلت للحد الأعلى وهو 25 زرًا.",
                ephemeral=True
            )

        if any(
            button.get("name", "").lower() == name.lower()
            for button in buttons
        ):
            return await interaction.response.send_message(
                "يوجد زر بهذا الاسم بالفعل.",
                ephemeral=True
            )

        buttons.append({
            "name": name[:80],
            "category": category.id if category else None,
            "emoji": emoji,
            "color": color.value if color else "primary"
        })

        result = (
            f"✅ أضفت زر **{name}**. أرسل لوحة جديدة "
            "باستخدام `/ticketsetup`."
        )

    else:
        match = next(
            (
                button for button in buttons
                if button.get("name", "").lower() == name.lower()
            ),
            None
        )

        if not match:
            return await interaction.response.send_message(
                "ما لقيت زر بهذا الاسم.",
                ephemeral=True
            )

        buttons.remove(match)
        result = (
            f"✅ حذفت زر **{name}**. أرسل لوحة جديدة "
            "باستخدام `/ticketsetup`."
        )

    settings["ticket_buttons"] = buttons
    save_settings(interaction.guild_id, settings)

    await interaction.response.send_message(
        result,
        ephemeral=True
    )


@bot.tree.command(
    name="ticketpreview",
    description="معاينة لوحة التكت قبل إرسالها"
)
async def ticketpreview(interaction: discord.Interaction):
    settings = get_settings(interaction.guild_id)

    embed = discord.Embed(
        title=settings["ticket_title"],
        description=settings["ticket_description"],
        color=parse_color(settings["ticket_color"])
    )

    if settings.get("ticket_image") and is_http_url(
        settings["ticket_image"]
    ):
        embed.set_image(url=settings["ticket_image"])

    await interaction.response.send_message(
        embed=embed,
        view=TicketPanelView(settings["ticket_buttons"]),
        ephemeral=True
    )


# ==================== الترحيب والمغادرة ====================

@bot.tree.command(
    name="welcomesetup",
    description="تحديد رومات الترحيب والمغادرة"
)
@app_commands.describe(
    welcome_channel="روم الترحيب",
    leave_channel="روم المغادرة، اختياري",
    image="رابط صورة الترحيب، اختياري"
)
async def welcomesetup(
    interaction: discord.Interaction,
    welcome_channel: discord.TextChannel,
    leave_channel: discord.TextChannel | None = None,
    image: str | None = None
):
    if not await admin_check(interaction):
        return

    settings = get_settings(interaction.guild_id)
    settings["welcome_channel"] = welcome_channel.id
    settings["leave_channel"] = (
        leave_channel.id if leave_channel else None
    )

    if image is not None:
        if not is
