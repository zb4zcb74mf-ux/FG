
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
DB = "turki_systems.db"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------- Database ----------

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    with connect() as conn:
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
            status TEXT
        )
        """)


def defaults():
    return {
        "ticket_title": "🎫 نظام التذاكر",
        "ticket_description": "اختر نوع التذكرة من الأزرار بالأسفل.",
        "ticket_banner": "",
        "ticket_image": "",
        "ticket_color": "8B5CF6",
        "ticket_category": None,
        "ticket_buttons": [
            {"name": "الدعم الفني", "emoji": "🛠️", "color": "primary"},
            {"name": "شكوى", "emoji": "📩", "color": "secondary"},
            {"name": "استفسار", "emoji": "❓", "color": "success"}
        ],
        "ticket_counter": 0,
        "welcome_channel": None,
        "welcome_text": "أهلًا {mention} في {server}! أنت العضو رقم {count} 🎉",
        "welcome_image": "",
        "welcome_color": "8B5CF6",
        "leave_channel": None,
        "leave_text": "غادر {user} السيرفر.",
        "leave_image": "",
        "leave_color": "808080",
        "suggestion_channel": None,
        "log_channel": None
    }


def get_settings(guild_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT data FROM settings WHERE guild_id=?",
            (str(guild_id),)
        ).fetchone()

    data = defaults()
    if row:
        try:
            data.update(json.loads(row["data"]))
        except (ValueError, TypeError):
            pass
    return data


def save_settings(guild_id, data):
    with connect() as conn:
        conn.execute("""
        INSERT INTO settings(guild_id, data) VALUES(?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data
        """, (str(guild_id), json.dumps(data, ensure_ascii=False)))


def color(value):
    try:
        return discord.Color(int(value.strip().replace("#", ""), 16))
    except (ValueError, AttributeError):
        return discord.Color.blurple()


def is_url(value):
    return value.startswith(("https://", "http://"))


def is_admin(interaction):
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_guild


async def require_admin(interaction):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ تحتاج صلاحية إدارة السيرفر.",
            ephemeral=True
        )
        return False
    return True


async def log_action(guild, message):
    settings = get_settings(guild.id)
    channel_id = settings.get("log_channel")
    if channel_id:
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(message)
            except discord.HTTPException:
                pass


# ---------- Ticket panel ----------

def ticket_embed(settings):
    embed = discord.Embed(
        title=settings["ticket_title"],
        description=settings["ticket_description"],
        color=color(settings["ticket_color"])
    )

    # Main panel image / banner
    banner = settings.get("ticket_banner", "")
    if banner and is_url(banner):
        embed.set_image(url=banner)

    # Secondary image, shown in the embed thumbnail
    image = settings.get("ticket_image", "")
    if image and is_url(image):
        embed.set_thumbnail(url=image)

    return embed


class TicketButton(discord.ui.Button):
    def __init__(self, item, index):
        styles = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger
        }
        self.ticket_name = item.get("name", "تذكرة")
        super().__init__(
            label=self.ticket_name[:80],
            emoji=item.get("emoji") or None,
            style=styles.get(item.get("color"), discord.ButtonStyle.primary),
            custom_id=f"turki_ticket_{index}"
        )

    async def callback(self, interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                "استخدم الزر داخل السيرفر.", ephemeral=True
            )

        with connect() as conn:
            row = conn.execute("""
                SELECT channel_id FROM tickets
                WHERE guild_id=? AND user_id=? AND status='open'
            """, (str(guild.id), str(interaction.user.id))).fetchone()

        if row:
            existing = guild.get_channel(int(row["channel_id"]))
            if existing:
                return await interaction.response.send_message(
                    f"عندك تذكرة مفتوحة: {existing.mention}",
                    ephemeral=True
                )

        settings = get_settings(guild.id)
        category_id = settings.get("ticket_category")
        category = guild.get_channel(int(category_id)) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True
            )

        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        settings["ticket_counter"] = int(settings["ticket_counter"]) + 1
        save_settings(guild.id, settings)

        try:
            channel = await guild.create_text_channel(
                f"ticket-{settings['ticket_counter']:04d}",
                category=category,
                overwrites=overwrites
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ البوت يحتاج صلاحية Manage Channels.",
                ephemeral=True
            )

        with connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tickets
                (channel_id, guild_id, user_id, status)
                VALUES(?, ?, ?, 'open')
            """, (
                str(channel.id), str(guild.id), str(interaction.user.id)
            ))

        embed = discord.Embed(
            title=f"🎫 {self.ticket_name}",
            description=(
                f"أهلًا {interaction.user.mention}\n"
                "اكتب تفاصيل طلبك هنا، وعند الانتهاء اضغط إغلاق التذكرة."
            ),
            color=color(settings["ticket_color"])
        )
        await channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=TicketCloseView()
        )
        await interaction.response.send_message(
            f"✅ تم فتح تذكرتك: {channel.mention}",
            ephemeral=True
        )
        await log_action(
            guild,
            f"🎫 تذكرة جديدة: {channel.mention} بواسطة {interaction.user.mention}"
        )


class TicketPanelView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=None)
        for index, item in enumerate(items[:25]):
            self.add_item(TicketButton(item, index))


class TicketCloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="إغلاق التذكرة",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="turki_ticket_close"
        )

    async def callback(self, interaction):
        channel = interaction.channel
        guild = interaction.guild
        if not guild or not isinstance(channel, discord.TextChannel):
            return

        with connect() as conn:
            row = conn.execute("""
                SELECT user_id FROM tickets
                WHERE channel_id=? AND status='open'
            """, (str(channel.id),)).fetchone()

        if not row:
            return await interaction.response.send_message(
                "لم أجد تذكرة مفتوحة هنا.", ephemeral=True
            )

        staff = (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.administrator
        )
        owner = str(interaction.user.id) == row["user_id"]

        if not staff and not owner:
            return await interaction.response.send_message(
                "❌ صاحب التذكرة أو الإدارة فقط يقدرون يقفلونها.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "🔒 سيتم حذف التذكرة بعد 5 ثوانٍ.", ephemeral=True
        )
        with connect() as conn:
            conn.execute(
                "UPDATE tickets SET status='closed' WHERE channel_id=?",
                (str(channel.id),)
            )

        await log_action(
            guild,
            f"🔒 إغلاق التذكرة {channel.name} بواسطة {interaction.user.mention}"
        )
        import asyncio
        await asyncio.sleep(5)
        try:
            await channel.delete()
        except discord.HTTPException:
            pass


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCloseButton())


# ---------- Ticket commands ----------

@bot.tree.command(name="ticketedit", description="تعديل تصميم لوحة التكت")
@app_commands.describe(
    title="عنوان اللوحة",
    description="وصف اللوحة",
    banner="رابط البانر الكبير أو remove",
    image="رابط صورة مصغرة أو remove",
    color_hex="لون HEX مثل 8B5CF6"
)
async def ticketedit(
    interaction: discord.Interaction,
    title: str = None,
    description: str = None,
    banner: str = None,
    image: str = None,
    color_hex: str = None
):
    if not await require_admin(interaction):
        return

    settings = get_settings(interaction.guild_id)

    if title is not None:
        settings["ticket_title"] = title[:256]
    if description is not None:
        settings["ticket_description"] = description[:4000]

    for key, value in (("ticket_banner", banner), ("ticket_image", image)):
        if value is None:
            continue
        if value.lower() in ("remove", "delete", "حذف"):
            settings[key] = ""
        elif is_url(value):
            settings[key] = value
        else:
            return await interaction.response.send_message(
                "روابط الصور يجب أن تبدأ بـ https:// أو اكتب remove.",
                ephemeral=True
            )

    if color_hex is not None:
        settings["ticket_color"] = color_hex.replace("#", "")

    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(
        "✅ تم حفظ التصميم. استخدم `/ticketpreview` للمعاينة.",
        embed=ticket_embed(settings),
        ephemeral=True
    )


@bot.tree.command(name="ticketbutton", description="إضافة أو حذف زر تكت")
@app_commands.choices(action=[
    app_commands.Choice(name="إضافة", value="add"),
    app_commands.Choice(name="حذف", value="remove")
])
@app_commands.choices(style=[
    app_commands.Choice(name="أزرق", value="primary"),
    app_commands.Choice(name="رمادي", value="secondary"),
    app_commands.Choice(name="أخضر", value="success"),
    app_commands.Choice(name="أحمر", value="danger")
])
async def ticketbutton(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    name: str,
    emoji: str = None,
    style: app_commands.Choice[str] = None
):
    if not await require_admin(interaction):
        return

    settings = get_settings(interaction.guild_id)
    buttons = settings["ticket_buttons"]

    if action.value == "add":
        if len(buttons) >= 25:
            return await interaction.response.send_message(
                "الحد الأعلى 25 زرًا.", ephemeral=True
            )
        buttons.append({
            "name": name[:80],
            "emoji": emoji,
            "color": style.value if style else "primary"
        })
    else:
        found = next(
            (b for b in buttons if b["name"].lower() == name.lower()),
            None
        )
        if not found:
            return await interaction.response.send_message(
                "لم أجد زرًا بهذا الاسم.", ephemeral=True
            )
        buttons.remove(found)

    settings["ticket_buttons"] = buttons
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(
        "✅ تم تحديث الأزرار. انشر اللوحة مجددًا بـ `/ticketsetup`.",
        ephemeral=True
    )


@bot.tree.command(name="ticketpreview", description="معاينة لوحة التكت")
async def ticketpreview(interaction: discord.Interaction):
    settings = get_settings(interaction.guild_id)
    await interaction.response.send_message(
        embed=ticket_embed(settings),
        view=TicketPanelView(settings["ticket_buttons"]),
        ephemeral=True
    )


@bot.tree.command(name="ticketsetup", description="نشر لوحة التكت")
async def ticketsetup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    category: discord.CategoryChannel = None
):
    if not await require_admin(interaction):
        return

    settings = get_settings(interaction.guild_id)
    settings["ticket_category"] = category.id if category else None
    save_settings(interaction.guild_id, settings)

    await channel.send(
        embed=ticket_embed(settings),
        view=TicketPanelView(settings["ticket_buttons"])
    )
    await interaction.response.send_message(
        f"✅ تم نشر لوحة التكت في {channel.mention}.",
        ephemeral=True
    )


# ---------- Welcome and leave ----------

def replace_vars(text, member):
    return (
        text.replace("{mention}", member.mention)
        .replace("{user}", str(member))
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or 0))
    )


def member_embed(member, text, image, hex_color):
    embed = discord.Embed(
        description=replace_vars(text, member),
        color=color(hex_color)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if image and is_url(image):
        embed.set_image(url=image)
    return embed


@bot.event
async def on_member_join(member):
    settings = get_settings(member.guild.id)
    channel_id = settings.get("welcome_channel")
    if not channel_id:
        return

    channel = member.guild.get_channel(int(channel_id))
    if channel:
        await channel.send(embed=member_embed(
            member,
            settings["welcome_text"],
            settings["welcome_image"],
            settings["welcome_color"]
        ))


@bot.event
async def on_member_remove(member):
    settings = get_settings(member.guild.id)
    channel_id = settings.get("leave_channel")
    if not channel_id:
        return

    channel = member.guild.get_channel(int(channel_id))
    if channel:
        await channel.send(embed=member_embed(
            member,
            settings["leave_text"],
            settings["leave_image"],
            settings["leave_color"]
        ))


@bot.tree.command(name="welcomesetup", description="تحديد رومات الترحيب والمغادرة")
async def welcomesetup(
    interaction: discord.Interaction,
    welcome_channel: discord.TextChannel,
    leave_channel: discord.TextChannel = None
):
    if not await require_admin(interaction):
        return

    settings = get_settings(interaction.guild_id)
    settings["welcome_channel"] = welcome_channel.id
    settings["leave_channel"] = leave_channel.id if leave_channel else None
    save_settings(interaction.guild_id, settings)

    await interaction.response.send_message(
        "✅ تم ضبط رومات الترحيب والمغادرة.",
        ephemeral=True
    )


@bot.tree.command(name="welcomeedit", description="تعديل الترحيب أو المغادرة")
@app_commands.choices(kind=[
    app_commands.Choice(name="الترحيب", value="welcome"),
    app_commands.Choice(name="المغادرة", value="leave")
])
async def welcomeedit(
    interaction: discord.Interaction,
    kind: app_commands.Choice[str],
    text: str = None,
    image: str = None,
    color_hex: str = None
):
    if not await require_admin(interaction):
        return

    settings = get_settings(interaction.guild_id)
    prefix = "welcome" if kind.value == "welcome" else "leave"

    if text is not None:
        settings[f"{prefix}_text"] = text[:1800]

    if image is not None:
        if image.lower() in ("remove", "delete", "حذف"):
            settings[f"{prefix}_image"] = ""
        elif is_url(image):
            settings[f"{prefix}_image"] = image
        else:
            return await interaction.response.send_message(
                "رابط الصورة يجب أن يبدأ بـ https:// أو اكتب remove.",
                ephemeral=True
            )

    if color_hex is not None:
        settings[f"{prefix}_color"] = color_hex.replace("#", "")

    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(
        "✅ تم حفظ الإعدادات.",
        ephemeral=True
    )


@bot.tree.command(name="welcomepreview", description="معاينة الترحيب")
async def welcomepreview(interaction: discord.Interaction):
    settings = get_settings(interaction.guild_id)
    await interaction.response.send_message(
        embed=member_embed(
            interaction.user,
            settings["welcome_text"],
            settings["welcome_image"],
            settings["welcome_color"]
        ),
        ephemeral=True
    )


# ---------- Suggestions ----------

class SuggestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="مؤيد",
        emoji="👍",
        style=discord.ButtonStyle.success,
        custom_id="turki_suggestion_up"
    )
    async def up(self, interaction, button):
        await interaction.response.send_message(
            "تم تسجيل تفاعلك مع الاقتراح.", ephemeral=True
        )

    @discord.ui.button(
        label="غير مؤيد",
        emoji="👎",
        style=discord.ButtonStyle.secondary,
        custom_id="turki_suggestion_down"
    )
    async def down(self, interaction, button):
        await interaction.response.send_message(
            "تم تسجيل تفاعلك مع الاقتراح.", ephemeral=True
        )


@bot.tree.command(name="suggestionsetup", description="تحديد روم الاقتراحات")
async def suggestionsetup(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    settings["suggestion_channel"] = channel.id
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(
        f"تم تحديد روم الاقتراحات: {channel.mention}",
        ephemeral=True
    )


@bot.tree.command(name="suggest", description="إرسال اقتراح")
async def suggest(interaction: discord.Interaction, text: str):
    settings = get_settings(interaction.guild_id)
    channel_id = settings.get("suggestion_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None

    if not channel:
        return await interaction.response.send_message(
            "الإدارة لم تحدد روم الاقتراحات.", ephemeral=True
        )

    embed = discord.Embed(
        title="💡 اقتراح جديد",
        description=text[:4000],
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(
        name=str(interaction.user),
        icon_url=interaction.user.display_avatar.url
    )
    await channel.send(embed=embed, view=SuggestionView())
    await interaction.response.send_message(
        "✅ تم إرسال اقتراحك.", ephemeral=True
    )


# ---------- Moderation ----------

@bot.tree.command(name="warn", description="تحذير عضو")
@app_commands.default_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "بدون سبب"
):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(
            "لا تملك صلاحية التحذير.", ephemeral=True
        )

    with connect() as conn:
        conn.execute("""
        INSERT INTO warnings(guild_id, user_id, moderator_id, reason, created_at)
        VALUES(?, ?, ?, ?, ?)
        """, (
            str(interaction.guild_id),
            str(member.id),
            str(interaction.user.id),
            reason,
            datetime.now(timezone.utc).isoformat()
        ))

    await interaction.response.send_message(
        f"⚠️ تم تحذير {member.mention}. السبب: {reason}"
    )


@bot.tree.command(name="warnings", description="عرض تحذيرات عضو")
@app_commands.default_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(
            "لا تملك الصلاحية.", ephemeral=True
        )

    with connect() as conn:
        rows = conn.execute("""
        SELECT reason, moderator_id, created_at FROM warnings
        WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10
        """, (str(interaction.guild_id), str(member.id))).fetchall()

    if not rows:
        return await interaction.response.send_message(
            "لا توجد تحذيرات مسجلة.", ephemeral=True
        )

    text = "\n".join(
        f"• {r['reason']} — <@{r['moderator_id']}>"
        for r in rows
    )
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="clearwarnings", description="مسح تحذيرات عضو")
@app_commands.default_permissions(administrator=True)
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "للإدارة العليا فقط.", ephemeral=True
        )

    with connect() as conn:
        conn.execute(
            "DELETE FROM warnings WHERE guild_id=? AND user_id=?",
            (str(interaction.guild_id), str(member.id))
        )
    await interaction.response.send_message("✅ تم مسح التحذيرات.")


@bot.tree.command(name="kick", description="طرد عضو")
@app_commands.default_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "بدون سبب"
):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message(
            "لا تملك صلاحية الطرد.", ephemeral=True
        )
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(
            f"👢 تم طرد {member.mention}. السبب: {reason}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "تعذر الطرد؛ تحقق من ترتيب الرتب.", ephemeral=True
        )


@bot.tree.command(name="ban", description="حظر عضو")
@app_commands.default_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "بدون سبب"
):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(
            "لا تملك صلاحية الحظر.", ephemeral=True
        )
    try:
        await member.ban(reason=reason, delete_message_seconds=0)
        await interaction.response.send_message(
            f"🔨 تم حظر {member.mention}. السبب: {reason}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "تعذر الحظر؛ تحقق من ترتيب الرتب.", ephemeral=True
        )


@bot.tree.command(name="timeout", description="إسكات عضو بالدقائق")
@app_commands.default_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "بدون سبب"
):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(
            "لا تملك صلاحية الإسكات.", ephemeral=True
        )
    try:
        await member.timeout(
            timedelta(minutes=minutes), reason=reason
        )
        await interaction.response.send_message(
            f"🔇 تم إسكات {member.mention} لمدة {minutes} دقيقة."
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "تعذر الإسكات؛ تحقق من ترتيب الرتب.", ephemeral=True
        )


@bot.tree.command(name="purge", description="حذف رسائل من الروم")
@app_commands.default_permissions(manage_messages=True)
async def purge(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            "لا تملك صلاحية حذف الرسائل.", ephemeral=True
        )
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "هذا الأمر للرومات الكتابية فقط.", ephemeral=True
        )
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(
        f"🧹 تم حذف {len(deleted)} رسالة.", ephemeral=True
    )


@bot.tree.command(name="lock", description="قفل الروم")
@app_commands.default_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(
            "لا تملك صلاحية إدارة الرومات.", ephemeral=True
        )
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "استخدم الأمر داخل روم كتابي.", ephemeral=True
        )
    overwrite = interaction.channel.overwrites_for(
        interaction.guild.default_role
    )
    overwrite.send_messages = False
    await interaction.channel.set_permissions(
        interaction.guild.default_role, overwrite=overwrite
    )
    await interaction.response.send_message("🔒 تم قفل الروم.")


@bot.tree.command(name="unlock", description="فتح الروم")
@app_commands.default_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(
            "لا تملك صلاحية إدارة الرومات.", ephemeral=True
        )
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "استخدم الأمر داخل روم كتابي.", ephemeral=True
        )
    overwrite = interaction.channel.overwrites_for(
        interaction.guild.default_role
    )
    overwrite.send_messages = None
    await interaction.channel.set_permissions(
        interaction.guild.default_role, overwrite=overwrite
    )
    await interaction.response.send_message("🔓 تم فتح الروم.")


@bot.tree.command(name="setlogs", description="تحديد روم السجلات")
async def setlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    settings["log_channel"] = channel.id
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(
        f"تم تحديد روم السجلات: {channel.mention}", ephemeral=True
    )


@bot.tree.command(name="serverinfo", description="معلومات السيرفر")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(
        title=guild.name,
        description=f"الأعضاء: {guild.member_count}\nالرومات: {len(guild.channels)}",
        color=discord.Color.blurple()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="معلومات عضو")
async def userinfo(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    embed = discord.Embed(
        title=str(member),
        description=f"ID: {member.id}",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="إنشاء الحساب",
        value=discord.utils.format_dt(member.created_at, style="D")
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="عرض صورة العضو")
async def avatar(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    embed = discord.Embed(title=f"صورة {member}")
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="helpme", description="عرض قائمة أوامر البوت")
async def helpme(interaction: discord.Interaction):
    embed = discord.Embed(
        title="TURKI SYSTEMS",
        description=(
            "**التكت**\n"
            "`/ticketedit` `/ticketbutton` `/ticketpreview` `/ticketsetup`\n\n"
            "**الترحيب**\n"
            "`/welcomesetup` `/welcomeedit` `/welcomepreview`\n\n"
            "**الاقتراحات والسجلات**\n"
            "`/suggestionsetup` `/suggest` `/setlogs`\n\n"
            "**الإدارة**\n"
            "`/warn` `/warnings` `/clearwarnings` `/kick` `/ban` "
            "`/timeout` `/purge` `/lock` `/unlock`\n\n"
            "**عام**\n"
            "`/serverinfo` `/userinfo` `/avatar`"
        ),
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------- Startup ----------

@bot.event
async def on_ready():
    setup_db()
    bot.add_view(TicketCloseView())
    bot.add_view(SuggestionView())

    for row in connect().execute("SELECT guild_id, data FROM settings").fetchall():
        try:
            settings = json.loads(row["data"])
            bot.add_view(TicketPanelView(settings["ticket_buttons"]))
        except (KeyError, ValueError, TypeError):
            pass

    try:
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()
    except Exception as error:
        print("Command sync error:", error)

    print(f"TURKI SYSTEMS online as {bot.user}")


if not TOKEN:
    print("ضع DISCORD_TOKEN داخل Replit Secrets.")
else:
    setup_db()
    bot.run(TOKEN)
