
import os
import random
import sqlite3
import time
import discord
from discord import app_commands
from discord.ext import commands

# ==========================================
# TURKI SYSTEMS | Single-file Discord Bot
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")
DB_FILE = "turki_systems.db"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------- DATABASE ----------------

def connect():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel INTEGER,
            leave_channel INTEGER,
            welcome_text TEXT DEFAULT 'يا هلا {mention} نورت السيرفر!',
            welcome_image TEXT,
            leave_text TEXT DEFAULT 'غادر السيرفر {name}.',
            ticket_category INTEGER,
            ticket_logs INTEGER,
            staff_role INTEGER,
            ticket_title TEXT DEFAULT 'TURKI SUPPORT',
            ticket_description TEXT DEFAULT 'اختر الزر لفتح تذكرة.',
            ticket_image TEXT,
            suggestion_channel INTEGER,
            log_channel INTEGER,
            auto_role INTEGER
        );

        CREATE TABLE IF NOT EXISTS tickets (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER,
            opener_id INTEGER,
            claimed_by INTEGER
        );

        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            created_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS economy (
            guild_id INTEGER,
            user_id INTEGER,
            balance INTEGER DEFAULT 0,
            last_daily INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            content TEXT,
            status TEXT DEFAULT 'قيد المراجعة'
        );
        """)


def cfg(guild_id):
    with connect() as con:
        row = con.execute(
            "SELECT * FROM settings WHERE guild_id=?", (guild_id,)
        ).fetchone()
        return dict(row) if row else {}


def set_cfg(guild_id, **values):
    allowed = {
        "welcome_channel", "leave_channel", "welcome_text",
        "welcome_image", "leave_text", "ticket_category",
        "ticket_logs", "staff_role", "ticket_title",
        "ticket_description", "ticket_image",
        "suggestion_channel", "log_channel", "auto_role"
    }
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO settings(guild_id) VALUES(?)",
            (guild_id,)
        )
        for key, value in values.items():
            if key in allowed:
                con.execute(
                    f"UPDATE settings SET {key}=? WHERE guild_id=?",
                    (value, guild_id)
                )


def get_account(guild_id, user_id):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO economy(guild_id,user_id) VALUES(?,?)",
            (guild_id, user_id)
        )
        row = con.execute(
            "SELECT * FROM economy WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        ).fetchone()
        return dict(row)


def staff_check(interaction):
    settings = cfg(interaction.guild_id)
    user = interaction.user
    if user.guild_permissions.administrator:
        return True
    if user.guild_permissions.manage_channels:
        return True
    role_id = settings.get("staff_role")
    return bool(
        role_id and any(
            role.id == role_id for role in getattr(user, "roles", [])
        )
    )


async def log_action(guild, message):
    settings = cfg(guild.id)
    channel = guild.get_channel(settings.get("log_channel") or 0)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(message)
        except discord.HTTPException:
            pass


# ---------------- EMBEDS ----------------

def make_embed(title, description, color=0x46BEEB):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="TURKI SYSTEMS")
    return embed


# ---------------- TICKET SYSTEM ----------------

class TicketOpenView(discord.ui.View):
    def __init__(self, label="فتح تذكرة", emoji="🎫"):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label=label[:80],
            emoji=emoji or None,
            style=discord.ButtonStyle.primary,
            custom_id="turki:ticket_open"
        )
        button.callback = self.open_ticket
        self.add_item(button)

    async def open_ticket(self, interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                "استخدم الزر داخل السيرفر.", ephemeral=True
            )

        settings = cfg(guild.id)
        with connect() as con:
            row = con.execute(
                "SELECT channel_id FROM tickets "
                "WHERE guild_id=? AND opener_id=?",
                (guild.id, interaction.user.id)
            ).fetchone()

        if row:
            old_channel = guild.get_channel(row["channel_id"])
            if old_channel:
                return await interaction.response.send_message(
                    f"لديك تذكرة مفتوحة: {old_channel.mention}",
                    ephemeral=True
                )

        category = guild.get_channel(settings.get("ticket_category") or 0)
        role = guild.get_role(settings.get("staff_role") or 0)

        overwrites = {
            guild.default_role:
                discord.PermissionOverwrite(view_channel=False),
            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True
            )

        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}"[:90],
                category=(
                    category
                    if isinstance(category, discord.CategoryChannel)
                    else None
                ),
                overwrites=overwrites,
                reason="TURKI ticket system"
            )

            with connect() as con:
                con.execute(
                    "INSERT INTO tickets(channel_id,guild_id,opener_id) "
                    "VALUES(?,?,?)",
                    (channel.id, guild.id, interaction.user.id)
                )

            embed = make_embed(
                "TURKI SUPPORT",
                f"أهلًا {interaction.user.mention}!\n\n"
                "اكتب طلبك بالتفصيل وسيساعدك فريق الدعم.\n\n"
                f"**صاحب التذكرة:** {interaction.user.mention}\n"
                "**الحالة:** بانتظار الدعم"
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

            await channel.send(
                content=role.mention if role else None,
                embed=embed,
                view=TicketManageView()
            )
            await interaction.response.send_message(
                f"تم فتح تذكرتك: {channel.mention}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "البوت لا يملك صلاحية إدارة القنوات.",
                ephemeral=True
            )


class TicketManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="استلام التذكرة", emoji="🛡️",
        style=discord.ButtonStyle.success,
        custom_id="turki:ticket_claim"
    )
    async def claim(self, interaction, button):
        if not interaction.guild:
            return

        if not staff_check(interaction):
            return await interaction.response.send_message(
                "هذا الزر لفريق الدعم فقط.", ephemeral=True
            )

        with connect() as con:
            cur = con.execute(
                "UPDATE tickets SET claimed_by=? "
                "WHERE channel_id=? AND guild_id=?",
                (
                    interaction.user.id,
                    interaction.channel_id,
                    interaction.guild_id
                )
            )

        if not cur.rowcount:
            return await interaction.response.send_message(
                "هذه القناة ليست تذكرة مسجلة.", ephemeral=True
            )

        await interaction.response.send_message(
            f"استلم {interaction.user.mention} التذكرة."
        )

    @discord.ui.button(
        label="إغلاق التذكرة", emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="turki:ticket_close"
    )
    async def close(self, interaction, button):
        if not interaction.guild:
            return

        with connect() as con:
            row = con.execute(
                "SELECT opener_id FROM tickets WHERE channel_id=?",
                (interaction.channel_id,)
            ).fetchone()

        if not row:
            return await interaction.response.send_message(
                "هذه القناة ليست تذكرة مسجلة.", ephemeral=True
            )

        if (
            interaction.user.id != row["opener_id"]
            and not staff_check(interaction)
        ):
            return await interaction.response.send_message(
                "الإغلاق متاح لصاحب التذكرة أو فريق الدعم.",
                ephemeral=True
            )

        channel = interaction.channel
        settings = cfg(interaction.guild_id)
        log_channel = interaction.guild.get_channel(
            settings.get("ticket_logs") or 0
        )

        await interaction.response.send_message("جاري إغلاق التذكرة...")

        if isinstance(log_channel, discord.TextChannel):
            try:
                await log_channel.send(
                    f"🔒 أُغلقت `{channel.name}` بواسطة "
                    f"{interaction.user.mention}"
                )
            except discord.HTTPException:
                pass

        with connect() as con:
            con.execute(
                "DELETE FROM tickets WHERE channel_id=?",
                (channel.id,)
            )

        await channel.delete(reason="TURKI ticket closed")


@bot.tree.command(name="ticket_setup", description="إنشاء لوحة التكت")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    title="عنوان اللوحة",
    description="وصف اللوحة",
    image_url="رابط الصورة المباشر",
    category="كاتيجوري التكت",
    staff_role="رتبة فريق الدعم",
    logs_channel="روم سجل التكت",
    button_name="اسم الزر",
    emoji="إيموجي الزر"
)
async def ticket_setup(
    interaction: discord.Interaction,
    title: str = "TURKI SUPPORT",
    description: str = "اختر الزر لفتح تذكرة.",
    image_url: str = "",
    category: discord.CategoryChannel = None,
    staff_role: discord.Role = None,
    logs_channel: discord.TextChannel = None,
    button_name: str = "فتح تذكرة",
    emoji: str = "🎫"
):
    if not interaction.guild or not isinstance(
        interaction.channel, discord.TextChannel
    ):
        return await interaction.response.send_message(
            "استخدم الأمر داخل روم نصي.", ephemeral=True
        )

    set_cfg(
        interaction.guild_id,
        ticket_title=title[:256],
        ticket_description=description[:4000],
        ticket_image=image_url or None,
        ticket_category=category.id if category else None,
        staff_role=staff_role.id if staff_role else None,
        ticket_logs=logs_channel.id if logs_channel else None
    )

    embed = make_embed(title, description)
    if image_url:
        embed.set_image(url=image_url)

    await interaction.channel.send(
        embed=embed,
        view=TicketOpenView(button_name, emoji)
    )
    await interaction.response.send_message(
        "تم نشر لوحة التكت.", ephemeral=True
    )


@bot.tree.command(name="ticket_panel", description="نشر لوحة التكت المحفوظة")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(
        interaction.channel, discord.TextChannel
    ):
        return await interaction.response.send_message(
            "استخدم الأمر داخل روم نصي.", ephemeral=True
        )

    settings = cfg(interaction.guild_id)
    embed = make_embed(
        settings.get("ticket_title") or "TURKI SUPPORT",
        settings.get("ticket_description") or "اختر الزر لفتح تذكرة."
    )
    if settings.get("ticket_image"):
        embed.set_image(url=settings["ticket_image"])

    await interaction.channel.send(embed=embed, view=TicketOpenView())
    await interaction.response.send_message(
        "تم نشر اللوحة بالإعدادات المحفوظة.", ephemeral=True
    )


# ---------------- WELCOME & LEAVE ----------------

@bot.tree.command(name="welcome_setup", description="إعداد الترحيب والمغادرة")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    welcome_channel="روم الترحيب",
    welcome_text="استخدم {mention} و{name} و{count}",
    image_url="رابط صورة الترحيب",
    leave_channel="روم المغادرة",
    leave_text="رسالة المغادرة وتدعم {name}",
    auto_role="رتبة تلقائية اختيارية"
)
async def welcome_setup(
    interaction: discord.Interaction,
    welcome_channel: discord.TextChannel,
    welcome_text: str = "يا هلا {mention} نورت السيرفر! أنت العضو رقم {count}",
    image_url: str = "",
    leave_channel: discord.TextChannel = None,
    leave_text: str = "غادر السيرفر {name}.",
    auto_role: discord.Role = None
):
    set_cfg(
        interaction.guild_id,
        welcome_channel=welcome_channel.id,
        welcome_text=welcome_text[:1800],
        welcome_image=image_url or None,
        leave_channel=leave_channel.id if leave_channel else None,
        leave_text=leave_text[:1800],
        auto_role=auto_role.id if auto_role else None
    )
    await interaction.response.send_message(
        "تم إعداد الترحيب والمغادرة.", ephemeral=True
    )


@bot.event
async def on_member_join(member):
    settings = cfg(member.guild.id)

    role = member.guild.get_role(settings.get("auto_role") or 0)
    if role:
        try:
            await member.add_roles(role, reason="TURKI auto role")
        except discord.HTTPException:
            pass

    channel = member.guild.get_channel(
        settings.get("welcome_channel") or 0
    )
    if isinstance(channel, discord.TextChannel):
        template = settings.get("welcome_text") or "يا هلا {mention}!"
        try:
            text = template.format(
                mention=member.mention,
                name=member.display_name,
                count=member.guild.member_count
            )
        except (KeyError, ValueError):
            text = f"يا هلا {member.mention}!"

        embed = make_embed("WELCOME TO THE SERVER", text)
        embed.set_thumbnail(url=member.display_avatar.url)
        if settings.get("welcome_image"):
            embed.set_image(url=settings["welcome_image"])
        await channel.send(embed=embed)


@bot.event
async def on_member_remove(member):
    settings = cfg(member.guild.id)
    channel = member.guild.get_channel(
        settings.get("leave_channel") or 0
    )
    if not isinstance(channel, discord.TextChannel):
        return

    template = settings.get("leave_text") or "غادر السيرفر {name}."
    try:
        text = template.format(name=member.display_name)
    except (KeyError, ValueError):
        text = f"غادر السيرفر {member.display_name}."

    embed = make_embed("MEMBER LEFT", text, 0x777777)
    embed.set_thumbnail(url=member.display_avatar.url)
    await channel.send(embed=embed)


# ---------------- MODERATION ----------------

@bot.tree.command(name="ban", description="حظر عضو")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "لم يتم تحديد السبب"
):
    if member.id == interaction.user.id:
        return await interaction.response.send_message(
            "لا يمكنك حظر نفسك.", ephemeral=True
        )
    try:
        await member.ban(reason=f"{reason} | بواسطة {interaction.user}")
        await interaction.response.send_message(
            f"تم حظر {member.mention}. السبب: {reason}"
        )
        await log_action(
            interaction.guild,
            f"🔨 حظر: {member} بواسطة {interaction.user} | {reason}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "لا أملك صلاحية حظر هذا العضو.", ephemeral=True
        )


@bot.tree.command(name="unban", description="فك حظر باستخدام ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(
            user, reason=f"بواسطة {interaction.user}"
        )
        await interaction.response.send_message(
            f"تم فك حظر {user.mention}."
        )
    except (ValueError, discord.NotFound):
        await interaction.response.send_message(
            "لم أجد هذا المستخدم ضمن المحظورين.", ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "لا أملك صلاحية فك الحظر.", ephemeral=True
        )


@bot.tree.command(name="kick", description="طرد عضو")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "لم يتم تحديد السبب"
):
    try:
        await member.kick(reason=f"{reason} | بواسطة {interaction.user}")
        await interaction.response.send_message(
            f"تم طرد {member.mention}. السبب: {reason}"
        )
        await log_action(
            interaction.guild,
            f"👢 طرد: {member} بواسطة {interaction.user} | {reason}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "لا أملك صلاحية طرد هذا العضو.", ephemeral=True
        )


@bot.tree.command(name="timeout", description="إعطاء تايم أوت بالدقائق")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(minutes="المدة بالدقائق")
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "لم يتم تحديد السبب"
):
    try:
        until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(
            f"تم إعطاء {member.mention} تايم أوت لمدة {minutes} دقيقة."
        )
    except AttributeError:
        from datetime import timedelta
        try:
            await member.timeout(
                discord.utils.utcnow() + timedelta(minutes=minutes),
                reason=reason
            )
            await interaction.response.send_message(
                f"تم إعطاء {member.mention} تايم أوت لمدة {minutes} دقيقة."
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "لا أملك صلاحية التايم أوت.", ephemeral=True
            )
    except discord.Forbidden:
        await interaction.response.send_message(
            "لا أملك صلاحية التايم أوت.", ephemeral=True
        )


@bot.tree.command(name="untimeout", description="إزالة التايم أوت")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(
    interaction: discord.Interaction,
    member: discord.Member
):
    try:
        await member.timeout(None)
        await interaction.response.send_message(
            f"تمت إزالة التايم أوت عن {member.mention}."
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "لا أملك صلاحية تنفيذ الأمر.", ephemeral=True
        )


@bot.tree.command(name="warn", description="تحذير عضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "لم يتم تحديد السبب"
):
    with connect() as con:
        con.execute(
            "INSERT INTO warnings(guild_id,user_id,moderator_id,reason,created_at) "
            "VALUES(?,?,?,?,?)",
            (
                interaction.guild_id, member.id, interaction.user.id,
                reason, int(time.time())
            )
        )
        count = con.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?",
            (interaction.guild_id, member.id)
        ).fetchone()[0]

    await interaction.response.send_message(
        f"تم تحذير {member.mention}. عدد تحذيراته: {count}\nالسبب: {reason}"
    )
    await log_action(
        interaction.guild,
        f"⚠️ تحذير {member.mention} بواسطة {interaction.user.mention}: {reason}"
    )


@bot.tree.command(name="warnings", description="عرض تحذيرات عضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    with connect() as con:
        rows = con.execute(
            "SELECT reason,moderator_id,created_at FROM warnings "
            "WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
            (interaction.guild_id, member.id)
        ).fetchall()

    if not rows:
        return await interaction.response.send_message(
            "لا توجد تحذيرات مسجلة لهذا العضو.", ephemeral=True
        )

    lines = [
        f"• {row['reason']} — <@{row['moderator_id']}>"
        for row in rows
    ]
    await interaction.response.send_message(
        embed=make_embed(
            f"تحذيرات {member}",
            "\n".join(lines)
        ),
        ephemeral=True
    )


@bot.tree.command(name="clear", description="مسح رسائل من الروم")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "هذا الأمر يعمل في الرومات النصية.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(
        f"تم مسح {len(deleted)} رسالة.", ephemeral=True
    )


@bot.tree.command(name="slowmode", description="تحديد الوضع البطيء")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(
    interaction: discord.Interaction,
    seconds: app_commands.Range[int, 0, 21600]
):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message(
            "هذا الأمر للرومات النصية.", ephemeral=True
        )
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(
        f"تم ضبط الوضع البطيء على {seconds} ثانية."
    )


@bot.tree.command(name="lock", description="قفل الروم الحالي")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    channel = interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(
        interaction.guild.default_role, overwrite=overwrite
    )
    await interaction.response.send_message("🔒 تم قفل الروم.")


@bot.tree.command(name="unlock", description="فتح الروم الحالي")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    channel = interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(
        interaction.guild.default_role, overwrite=overwrite
    )
    await interaction.response.send_message("🔓 تم فتح الروم.")


# ---------------- SUGGESTIONS ----------------

@bot.tree.command(name="suggest", description="إرسال اقتراح")
@app_commands.describe(text="اكتب اقتراحك")
async def suggest(interaction: discord.Interaction, text: str):
    settings = cfg(interaction.guild_id)
    channel = interaction.guild.get_channel(
        settings.get("suggestion_channel") or 0
    )
    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message(
            "الإدارة لم تحدد روم الاقتراحات بعد.", ephemeral=True
        )

    with connect() as con:
        cur = con.execute(
            "INSERT INTO suggestions(guild_id,user_id,content) VALUES(?,?,?)",
            (interaction.guild_id, interaction.user.id, text)
        )
        suggestion_id = cur.lastrowid

    embed = make_embed(
        f"اقتراح #{suggestion_id}",
        f"**صاحب الاقتراح:** {interaction.user.mention}\n\n{text}"
    )
    message = await channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await interaction.response.send_message(
        "تم إرسال اقتراحك للإدارة.", ephemeral=True
    )


@bot.tree.command(name="suggestion_setup", description="تحديد روم الاقتراحات")
@app_commands.checks.has_permissions(administrator=True)
async def suggestion_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    set_cfg(interaction.guild_id, suggestion_channel=channel.id)
    await interaction.response.send_message(
        f"تم تحديد روم الاقتراحات: {channel.mention}",
        ephemeral=True
    )


# ---------------- ANNOUNCEMENTS & POLLS ----------------

@bot.tree.command(name="announce", description="إرسال إعلان")
@app_commands.checks.has_permissions(manage_guild=True)
async def announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    message: str
):
    embed = make_embed(title, message)
    await channel.send(embed=embed)
    await interaction.response.send_message(
        "تم إرسال الإعلان.", ephemeral=True
    )


@bot.tree.command(name="poll", description="إنشاء تصويت بخيارين")
@app_commands.checks.has_permissions(manage_messages=True)
async def poll(
    interaction: discord.Interaction,
    question: str,
    option_one: str,
    option_two: str
):
    embed = make_embed(
        f"📊 {question}",
        f"👍 **{option_one}**\n\n👎 **{option_two}**"
    )
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await interaction.response.send_message(
        "تم إنشاء التصويت.", ephemeral=True
    )


# ---------------- ECONOMY ----------------

@bot.tree.command(name="balance", description="عرض رصيدك أو رصيد عضو")
async def balance(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    account = get_account(interaction.guild_id, member.id)
    await interaction.response.send_message(
        embed=make_embed(
            "💰 المحفظة",
            f"الرصيد لدى {member.mention}: **{account['balance']:,}**"
        )
    )


@bot.tree.command(name="daily", description="استلام المكافأة اليومية")
async def daily(interaction: discord.Interaction):
    account = get_account(interaction.guild_id, interaction.user.id)
    now = int(time.time())
    cooldown = 86400
    remaining = cooldown - (now - account["last_daily"])

    if remaining > 0:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return await interaction.response.send_message(
            f"ارجع بعد {hours} ساعة و{minutes} دقيقة.",
            ephemeral=True
        )

    reward = random.randint(100, 500)
    with connect() as con:
        con.execute(
            "UPDATE economy SET balance=balance+?,last_daily=? "
            "WHERE guild_id=? AND user_id=?",
            (reward, now, interaction.guild_id, interaction.user.id)
        )

    await interaction.response.send_message(
        f"🎁 استلمت مكافأتك اليومية: **{reward}**"
    )


@bot.tree.command(name="pay", description="تحويل رصيد لعضو")
async def pay(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 100000000]
):
    if member.id == interaction.user.id or member.bot:
        return await interaction.response.send_message(
            "اختر عضوًا آخر.", ephemeral=True
        )

    sender = get_account(interaction.guild_id, interaction.user.id)
    get_account(interaction.guild_id, member.id)

    if sender["balance"] < amount:
        return await interaction.response.send_message(
            "رصيدك لا يكفي.", ephemeral=True
        )

    with connect() as con:
        con.execute(
            "UPDATE economy SET balance=balance-? "
            "WHERE guild_id=? AND user_id=?",
            (amount, interaction.guild_id, interaction.user.id)
        )
        con.execute(
            "UPDATE economy SET balance=balance+? "
            "WHERE guild_id=? AND user_id=?",
            (amount, interaction.guild_id, member.id)
        )

    await interaction.response.send_message(
        f"تم تحويل **{amount:,}** إلى {member.mention}."
    )


@bot.tree.command(name="work", description="العمل لكسب المال")
async def work(interaction: discord.Interaction):
    reward = random.randint(50, 250)
    get_account(interaction.guild_id, interaction.user.id)

    with connect() as con:
        con.execute(
            "UPDATE economy SET balance=balance+? "
            "WHERE guild_id=? AND user_id=?",
            (reward, interaction.guild_id, interaction.user.id)
        )

    jobs = [
        "اشتغلت في متجر",
        "أنجزت مهمة",
        "ساعدت أحد الأعضاء",
        "عملت في مشروع"
    ]
    await interaction.response.send_message(
        f"💼 {random.choice(jobs)} وربحت **{reward}**."
    )


@bot.tree.command(name="leaderboard", description="أغنى أعضاء السيرفر")
async def leaderboard(interaction: discord.Interaction):
    with connect() as con:
        rows = con.execute(
            "SELECT user_id,balance FROM economy WHERE guild_id=? "
            "ORDER BY balance DESC LIMIT 10",
            (interaction.guild_id,)
        ).fetchall()

    if not rows:
        return await interaction.response.send_message(
            "لا توجد أرصدة حتى الآن."
        )

    lines = [
        f"**{i}.** <@{row['user_id']}> — {row['balance']:,}"
        for i, row in enumerate(rows, start=1)
    ]
    await interaction.response.send_message(
        embed=make_embed("🏆 أغنى أعضاء السيرفر", "\n".join(lines))
    )


# ---------------- LEVELS ----------------

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    # خبرة بسيطة لكل رسالة؛ لا تعمل دون تفعيل Message Content Intent.
    account = get_account(message.guild.id, message.author.id)
    gained = random.randint(5, 15)
    new_xp = account["xp"] + gained
    new_level = new_xp // 100

    with connect() as con:
        con.execute(
            "UPDATE economy SET xp=?,level=? "
            "WHERE guild_id=? AND user_id=?",
            (new_xp, new_level, message.guild.id, message.author.id)
        )

    if new_level > account["level"]:
        try:
            await message.channel.send(
                f"🎉 {message.author.mention} وصل للمستوى **{new_level}**!"
            )
        except discord.HTTPException:
            pass

    await bot.process_commands(message)


@bot.tree.command(name="rank", description="عرض مستوى عضو")
async def rank(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    account = get_account(interaction.guild_id, member.id)
    await interaction.response.send_message(
        embed=make_embed(
            "⭐ مستوى العضو",
            f"العضو: {member.mention}\n"
            f"المستوى: **{account['level']}**\n"
            f"الخبرة: **{account['xp']} XP**"
        )
    )


# ---------------- GAMES ----------------

@bot.tree.command(name="rps", description="حجر ورقة مقص")
@app_commands.choices(choice=[
    app_commands.Choice(name="حجر", value="حجر"),
    app_commands.Choice(name="ورقة", value="ورقة"),
    app_commands.Choice(name="مقص", value="مقص")
])
async def rps(
    interaction: discord.Interaction,
    choice: app_commands.Choice[str]
):
    options = ["حجر", "ورقة", "مقص"]
    bot_choice = random.choice(options)
    player = choice.value

    if player == bot_choice:
        result = "تعادل!"
    elif (
        (player == "حجر" and bot_choice == "مقص")
        or (player == "ورقة" and bot_choice == "حجر")
        or (player == "مقص" and bot_choice == "ورقة")
    ):
        result = "فزت! 🎉"
    else:
        result = "فاز البوت هذه المرة!"

    await interaction.response.send_message(
        embed=make_embed(
            "✊ حجر ورقة مقص",
            f"اختيارك: **{player}**\n"
            f"اختياري: **{bot_choice}**\n\n**{result}**"
        )
    )


@bot.tree.command(name="guess", description="خمن رقمًا من 1 إلى 10")
async def guess(
    interaction: discord.Interaction,
    number: app_commands.Range[int, 1, 10]
):
    answer = random.randint(1, 10)
    if number == answer:
        text = "صحيح! فزت 🎉"
    else:
        text = f"خطأ! الرقم الصحيح كان **{answer}**."
    await interaction.response.send_message(text)


# ---------------- INFORMATION ----------------

@bot.tree.command(name="ping", description="سرعة استجابة البوت")
async def ping(interaction: discord.Interaction):
    ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong: **{ms} ms**")


@bot.tree.command(name="serverinfo", description="معلومات السيرفر")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = make_embed(
        f"معلومات {guild.name}",
        f"**الأعضاء:** {guild.member_count}\n"
        f"**الرومات:** {len(guild.channels)}\n"
        f"**الرتب:** {len(guild.roles)}\n"
        f"**معرّف السيرفر:** {guild.id}"
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
    embed = make_embed(
        f"معلومات {member}",
        f"**الاسم:** {member.mention}\n"
        f"**ID:** `{member.id}`\n"
        f"**البوت:** {'نعم' if member.bot else 'لا'}\n"
        f"**تاريخ إنشاء الحساب:** "
        f"{discord.utils.format_dt(member.created_at, style='D')}\n"
        f"**انضم للسيرفر:** "
        f"{discord.utils.format_dt(member.joined_at, style='D') if member.joined_at else 'غير معروف'}"
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="عرض صورة عضو")
async def avatar(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    embed = make_embed(f"Avatar — {member}", "")
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="عرض قائمة أوامر TURKI")
async def help_command(interaction: discord.Interaction):
    embed = make_embed(
        "TURKI SYSTEMS | الأوامر",
        "**الإدارة:** `/ban` `/unban` `/kick` `/timeout` `/untimeout` "
        "`/warn` `/warnings` `/clear` `/lock` `/unlock` `/slowmode`\n\n"
        "**التكت:** `/ticket_setup` `/ticket_panel`\n\n"
        "**الترحيب:** `/welcome_setup`\n\n"
        "**المجتمع:** `/suggestion_setup` `/suggest` `/announce` `/poll`\n\n"
        "**الاقتصاد:** `/balance` `/daily` `/pay` `/work` `/leaderboard`\n\n"
        "**المستويات:** `/rank`\n\n"
        "**الألعاب:** `/rps` `/guess`\n\n"
        "**المعلومات:** `/ping` `/serverinfo` `/userinfo` `/avatar`"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------- STARTUP ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | TURKI SYSTEMS")

@bot.tree.error
async def on_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "ليس لديك الصلاحيات المطلوبة لهذا الأمر."
    else:
        print("Command error:", repr(error))
        message = "حدث خطأ. تحقق من صلاحيات البوت والإعدادات."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def main():
    init_db()
    bot.add_view(TicketOpenView())
    bot.add_view(TicketManageView())
    await bot.start(TOKEN)


if not TOKEN:
    raise RuntimeError(
        "أضف DISCORD_TOKEN إلى Secrets في Replit."
    )

import asyncio
asyncio.run(main())
