
import os
import sqlite3
import random
import asyncio
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

# =========================
# TURKI SYSTEMS - SETTINGS
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

if not TOKEN:
    raise RuntimeError("أضف DISCORD_TOKEN في Secrets في Replit")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

DB = "turki_systems.db"


# =========================
# DATABASE
# =========================

def db():
    return sqlite3.connect(DB)


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER,
                name TEXT,
                value TEXT,
                PRIMARY KEY (guild_id, name)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                moderator_id INTEGER,
                reason TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                guild_id INTEGER,
                user_id INTEGER,
                balance INTEGER DEFAULT 0,
                last_daily TEXT DEFAULT '',
                PRIMARY KEY (guild_id, user_id)
            )
        """)


def setting(guild_id, name, default=None):
    with db() as con:
        row = con.execute(
            "SELECT value FROM settings WHERE guild_id=? AND name=?",
            (guild_id, name)
        ).fetchone()
    return row[0] if row else default


def set_setting(guild_id, name, value):
    with db() as con:
        con.execute("""
            INSERT INTO settings (guild_id, name, value)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, name)
            DO UPDATE SET value=excluded.value
        """, (guild_id, name, str(value)))


def get_balance(guild_id, user_id):
    with db() as con:
        con.execute("""
            INSERT OR IGNORE INTO economy (guild_id, user_id, balance)
            VALUES (?, ?, 0)
        """, (guild_id, user_id))
        row = con.execute(
            "SELECT balance FROM economy WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        ).fetchone()
    return row[0]


def change_balance(guild_id, user_id, amount):
    get_balance(guild_id, user_id)
    with db() as con:
        con.execute("""
            UPDATE economy SET balance = balance + ?
            WHERE guild_id=? AND user_id=?
        """, (amount, guild_id, user_id))


# =========================
# BOT + SLASH SYNC
# =========================

class TurkiBot(commands.Bot):
    async def setup_hook(self):
        init_db()

        self.add_view(TicketOpenView())
        self.add_view(TicketCloseView())

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)

            # مزامنة أوامر الكود الحالي مباشرة مع السيرفر
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            # إزالة النسخ العامة القديمة التابعة لهذا البوت
            self.tree.clear_commands(guild=None)
            await self.tree.sync()

            print(f"تمت مزامنة {len(synced)} أمرًا في السيرفر {GUILD_ID}")
        else:
            synced = await self.tree.sync()
            print(f"تمت مزامنة {len(synced)} أمرًا بشكل عام")

        print("TURKI SYSTEMS: انتهت مزامنة الأوامر")


bot = TurkiBot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"تم تشغيل البوت: {bot.user}")
    print(f"ID: {bot.user.id}")


# =========================
# TICKETS
# =========================

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="فتح تكت",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="turki:ticket_open"
    )
    async def open_ticket(self, interaction: discord.Interaction, button):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "استخدم الزر داخل السيرفر.", ephemeral=True
            )

        existing = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{interaction.user.id}"
        )

        if existing:
            return await interaction.response.send_message(
                f"عندك تكت مفتوح بالفعل: {existing.mention}",
                ephemeral=True
            )

        category = None
        category_id = setting(guild.id, "ticket_category")
        if category_id:
            category = guild.get_channel(int(category_id))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )
        }

        staff_role_id = setting(guild.id, "ticket_staff_role")
        if staff_role_id:
            role = guild.get_role(int(staff_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.id}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "ما عندي صلاحية إنشاء الرومات. تأكد من صلاحياتي وترتيب الرتب.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🎫 تكت جديد",
            description=(
                f"أهلًا {interaction.user.mention}\n"
                "اكتب طلبك هنا، والإدارة بتساعدك."
            ),
            color=discord.Color.blurple()
        )
        await channel.send(
            embed=embed,
            view=TicketCloseView()
        )
        await interaction.response.send_message(
            f"تم فتح التكت: {channel.mention}",
            ephemeral=True
        )


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="إغلاق التكت",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="turki:ticket_close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "تعذر تحديد روم التكت.", ephemeral=True
            )

        if not channel.name.startswith("ticket-"):
            return await interaction.response.send_message(
                "هذا الزر مخصص لرومات التكت.", ephemeral=True
            )

        if not (
            interaction.user.guild_permissions.manage_channels
            or channel.name == f"ticket-{interaction.user.id}"
        ):
            return await interaction.response.send_message(
                "ما عندك صلاحية إغلاق هذا التكت.", ephemeral=True
            )

        await interaction.response.send_message(
            "سيتم إغلاق التكت بعد 5 ثوانٍ."
        )
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket closed by {interaction.user}")


@bot.tree.command(name="ticket_setup", description="إنشاء لوحة التكت")
@app_commands.describe(
    channel="الروم الذي تُرسل فيه اللوحة",
    staff_role="رتبة فريق التكت، اختيارية",
    category="تصنيف رومات التكت، اختياري",
    title="عنوان اللوحة",
    description="وصف اللوحة",
    button_label="اسم زر فتح التكت"
)
@app_commands.checks.has_permissions(administrator=True)
async def ticket_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    staff_role: discord.Role = None,
    category: discord.CategoryChannel = None,
    title: str = "الدعم الفني",
    description: str = "اضغط الزر بالأسفل لفتح تكت جديد.",
    button_label: str = "فتح تكت"
):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "هذا الأمر داخل السيرفر فقط.", ephemeral=True
        )

    set_setting(interaction.guild.id, "ticket_staff_role",
                staff_role.id if staff_role else "")
    set_setting(interaction.guild.id, "ticket_category",
                category.id if category else "")

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blurple()
    )

    view = TicketOpenView()
    view.children[0].label = button_label

    await channel.send(embed=embed, view=view)
    await interaction.response.send_message(
        f"تم إرسال لوحة التكت في {channel.mention}.",
        ephemeral=True
    )


# =========================
# WELCOME + LEAVE
# =========================

@bot.tree.command(name="welcome_setup", description="إعداد الترحيب والمغادرة")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    channel="روم الترحيب والمغادرة",
    image_url="رابط صورة اختياري"
)
async def welcome_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    image_url: str = ""
):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "هذا الأمر داخل السيرفر فقط.", ephemeral=True
        )

    set_setting(interaction.guild.id, "welcome_channel", channel.id)
    set_setting(interaction.guild.id, "welcome_image", image_url)
    await interaction.response.send_message(
        f"تم ضبط الترحيب والمغادرة في {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(name="welcome_test", description="تجربة رسالة الترحيب")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_test(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "هذا الأمر داخل السيرفر فقط.", ephemeral=True
        )

    channel_id = setting(interaction.guild.id, "welcome_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None

    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message(
            "استخدم /welcome_setup أولًا.", ephemeral=True
        )

    embed = discord.Embed(
        title="أهلًا بك!",
        description=f"نرحب بـ {interaction.user.mention} في {interaction.guild.name}",
        color=discord.Color.green()
    )
    image_url = setting(interaction.guild.id, "welcome_image")
    if image_url:
        embed.set_image(url=image_url)

    await channel.send(embed=embed)
    await interaction.response.send_message(
        "تم إرسال رسالة التجربة.", ephemeral=True
    )


@bot.event
async def on_member_join(member):
    channel_id = setting(member.guild.id, "welcome_channel")
    channel = member.guild.get_channel(int(channel_id)) if channel_id else None

    if isinstance(channel, discord.TextChannel):
        embed = discord.Embed(
            title="👋 عضو جديد!",
            description=(
                f"أهلًا {member.mention}\n"
                f"أنت العضو رقم **{member.guild.member_count}** في السيرفر."
            ),
            color=discord.Color.green()
        )
        image_url = setting(member.guild.id, "welcome_image")
        if image_url:
            embed.set_image(url=image_url)
        await channel.send(embed=embed)


@bot.event
async def on_member_remove(member):
    channel_id = setting(member.guild.id, "welcome_channel")
    channel = member.guild.get_channel(int(channel_id)) if channel_id else None

    if isinstance(channel, discord.TextChannel):
        embed = discord.Embed(
            title="👋 غادر عضو",
            description=f"غادر **{member}** السيرفر.",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)


# =========================
# SUGGESTIONS
# =========================

@bot.tree.command(name="suggestion_setup", description="تحديد روم الاقتراحات")
@app_commands.checks.has_permissions(administrator=True)
async def suggestion_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "هذا الأمر داخل السيرفر فقط.", ephemeral=True
        )

    set_setting(interaction.guild.id, "suggestion_channel", channel.id)
    await interaction.response.send_message(
        f"تم تحديد روم الاقتراحات: {channel.mention}",
        ephemeral=True
    )


@bot.tree.command(name="suggest", description="إرسال اقتراح")
@app_commands.describe(text="اكتب اقتراحك")
async def suggest(interaction: discord.Interaction, text: str):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "استخدم الأمر داخل السيرفر.", ephemeral=True
        )

    channel_id = setting(interaction.guild.id, "suggestion_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None

    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message(
            "الإدارة تحتاج تستخدم /suggestion_setup أولًا.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="💡 اقتراح جديد",
        description=text,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"مقدم الاقتراح: {interaction.user}")
    message = await channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await interaction.response.send_message(
        "تم إرسال اقتراحك، شكرًا لك!", ephemeral=True
    )


# =========================
# MODERATION
# =========================

@bot.tree.command(name="ban", description="حظر عضو")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "لم يتم تحديد السبب"
):
    if member.id == interaction.user.id:
        return await interaction.response.send_message(
            "ما تقدر تحظر نفسك.", ephemeral=True
        )
    try:
        await member.ban(reason=f"{reason} | By {interaction.user}")
        await interaction.response.send_message(
            f"تم حظر {member.mention}.\nالسبب: {reason}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "ما عندي صلاحية الحظر، أو رتبة العضو أعلى من رتبتي.",
            ephemeral=True
        )


@bot.tree.command(name="kick", description="طرد عضو")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "لم يتم تحديد السبب"
):
    try:
        await member.kick(reason=f"{reason} | By {interaction.user}")
        await interaction.response.send_message(
            f"تم طرد {member.mention}.\nالسبب: {reason}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "ما عندي صلاحية الطرد، أو رتبة العضو أعلى من رتبتي.",
            ephemeral=True
        )


@bot.tree.command(name="unban", description="إلغاء حظر باستخدام ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    if not user_id.isdigit():
        return await interaction.response.send_message(
            "أدخل ID صحيحًا.", ephemeral=True
        )

    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(
            user, reason=f"Unban by {interaction.user}"
        )
        await interaction.response.send_message(
            f"تم إلغاء حظر {user.mention}."
        )
    except discord.NotFound:
        await interaction.response.send_message(
            "المستخدم غير محظور أو أن الـ ID غير صحيح.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "ما عندي صلاحية إلغاء الحظر.", ephemeral=True
        )


@bot.tree.command(name="timeout", description="إعطاء عضو مهلة")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(minutes="المدة بالدقائق")
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "لم يتم تحديد السبب"
):
    try:
        await member.timeout(
            timedelta(minutes=minutes),
            reason=f"{reason} | By {interaction.user}"
        )
        await interaction.response.send_message(
            f"تم إعطاء {member.mention} مهلة لمدة {minutes} دقيقة."
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "ما عندي صلاحية إعطاء المهلة.", ephemeral=True
        )


@bot.tree.command(name="untimeout", description="إزالة المهلة عن عضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None, reason=f"By {interaction.user}")
        await interaction.response.send_message(
            f"تمت إزالة المهلة عن {member.mention}."
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "ما عندي صلاحية إزالة المهلة.", ephemeral=True
        )


@bot.tree.command(name="warn", description="تحذير عضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "لم يتم تحديد السبب"
):
    with db() as con:
        con.execute("""
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason)
            VALUES (?, ?, ?, ?)
        """, (
            interaction.guild.id,
            member.id,
            interaction.user.id,
            reason
        ))

    await interaction.response.send_message(
        f"⚠️ تم تحذير {member.mention}.\nالسبب: {reason}"
    )


@bot.tree.command(name="warnings", description="عرض تحذيرات عضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    with db() as con:
        rows = con.execute("""
            SELECT id, reason, moderator_id FROM warnings
            WHERE guild_id=? AND user_id=?
            ORDER BY id DESC LIMIT 10
        """, (interaction.guild.id, member.id)).fetchall()

    if not rows:
        return await interaction.response.send_message(
            f"ما فيه تحذيرات مسجلة لـ {member.mention}.",
            ephemeral=True
        )

    lines = [
        f"**#{row[0]}** — {row[1]} (بواسطة <@{row[2]}>)"
        for row in rows
    ]
    await interaction.response.send_message(
        f"تحذيرات {member.mention}:\n" + "\n".join(lines),
        ephemeral=True
    )


@bot.tree.command(name="clearwarns", description="مسح تحذيرات عضو")
@app_commands.checks.has_permissions(moderate_members=True)
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    with db() as con:
        con.execute(
            "DELETE FROM warnings WHERE guild_id=? AND user_id=?",
            (interaction.guild.id, member.id)
        )
    await interaction.response.send_message(
        f"تم مسح تحذيرات {member.mention}."
    )


@bot.tree.command(name="clear", description="حذف رسائل من الروم")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="عدد الرسائل، من 1 إلى 100")
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100]
):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(
        f"تم حذف {len(deleted)} رسالة.",
        ephemeral=True
    )


@bot.tree.command(name="slowmode", description="تحديد التباطؤ بالروم")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(
    interaction: discord.Interaction,
    seconds: app_commands.Range[int, 0, 21600]
):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(
        f"تم ضبط التباطؤ على {seconds} ثانية."
    )


@bot.tree.command(name="lock", description="قفل الروم")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(
        interaction.guild.default_role,
        send_messages=False
    )
    await interaction.response.send_message("🔒 تم قفل الروم.")


@bot.tree.command(name="unlock", description="فتح الروم")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(
        interaction.guild.default_role,
        send_messages=None
    )
    await interaction.response.send_message("🔓 تم فتح الروم.")


# =========================
# ANNOUNCEMENTS + POLLS
# =========================

@bot.tree.command(name="announce", description="إرسال إعلان")
@app_commands.checks.has_permissions(manage_guild=True)
async def announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    text: str
):
    embed = discord.Embed(
        title=title,
        description=text,
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f"بواسطة {interaction.user}")
    await channel.send(embed=embed)
    await interaction.response.send_message(
        f"تم إرسال الإعلان في {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(name="poll", description="إنشاء تصويت")
@app_commands.checks.has_permissions(manage_messages=True)
async def poll(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str
):
    embed = discord.Embed(
        title=f"📊 {question}",
        description=f"👍 {option1}\n\n👎 {option2}",
        color=discord.Color.blurple()
    )
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await interaction.response.send_message(
        "تم إنشاء التصويت.", ephemeral=True
    )


# =========================
# ECONOMY
# =========================

@bot.tree.command(name="balance", description="عرض رصيدك أو رصيد عضو")
async def balance(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    amount = get_balance(interaction.guild.id, member.id)
    await interaction.response.send_message(
        f"💰 رصيد {member.mention}: **{amount:,}**"
    )


@bot.tree.command(name="daily", description="استلام المكافأة اليومية")
async def daily(interaction: discord.Interaction):
    import datetime

    today = datetime.date.today().isoformat()
    get_balance(interaction.guild.id, interaction.user.id)

    with db() as con:
        row = con.execute("""
            SELECT last_daily FROM economy
            WHERE guild_id=? AND user_id=?
        """, (interaction.guild.id, interaction.user.id)).fetchone()

        if row and row[0] == today:
            return await interaction.response.send_message(
                "استلمت مكافأتك اليومية بالفعل. ارجع بكرة.",
                ephemeral=True
            )

        reward = 1000
        con.execute("""
            UPDATE economy
            SET balance=balance+?, last_daily=?
            WHERE guild_id=? AND user_id=?
        """, (
            reward, today, interaction.guild.id, interaction.user.id
        ))

    await interaction.response.send_message(
        f"🎁 استلمت مكافأتك اليومية: **{reward:,}**"
    )


@bot.tree.command(name="pay", description="تحويل رصيد لعضو")
async def pay(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: app_commands.Range[int, 1, 1000000000]
):
    if member.bot or member.id == interaction.user.id:
        return await interaction.response.send_message(
            "اختر عضوًا آخر غير البوت.", ephemeral=True
        )

    balance_now = get_balance(interaction.guild.id, interaction.user.id)
    if balance_now < amount:
        return await interaction.response.send_message(
            "رصيدك ما يكفي.", ephemeral=True
        )

    change_balance(interaction.guild.id, interaction.user.id, -amount)
    change_balance(interaction.guild.id, member.id, amount)

    await interaction.response.send_message(
        f"تم تحويل **{amount:,}** إلى {member.mention}."
    )


@bot.tree.command(name="work", description="العمل للحصول على رصيد")
async def work(interaction: discord.Interaction):
    amount = random.randint(100, 1000)
    change_balance(interaction.guild.id, interaction.user.id, amount)
    await interaction.response.send_message(
        f"💼 اشتغلت وربحت **{amount:,}**."
    )


@bot.tree.command(name="leaderboard", description="أعلى الأعضاء في الرصيد")
async def leaderboard(interaction: discord.Interaction):
    with db() as con:
        rows = con.execute("""
            SELECT user_id, balance FROM economy
            WHERE guild_id=?
            ORDER BY balance DESC LIMIT 10
        """, (interaction.guild.id,)).fetchall()

    if not rows:
        return await interaction.response.send_message(
            "ما فيه أرصدة مسجلة حتى الآن."
        )

    lines = [
        f"**{i}.** <@{row[0]}> — **{row[1]:,}**"
        for i, row in enumerate(rows, 1)
    ]
    await interaction.response.send_message(
        "🏆 **قائمة الأغنى**\n" + "\n".join(lines)
    )


# =========================
# GENERAL + FUN
# =========================

@bot.tree.command(name="ping", description="معرفة سرعة استجابة البوت")
async def ping(interaction: discord.Interaction):
    ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong: **{ms}ms**")


@bot.tree.command(name="serverinfo", description="معلومات السيرفر")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(
        title=guild.name,
        color=discord.Color.blurple()
    )
    embed.add_field(name="عدد الأعضاء", value=str(guild.member_count))
    embed.add_field(name="عدد الرومات", value=str(len(guild.channels)))
    embed.add_field(name="معرّف السيرفر", value=str(guild.id))
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
        title=f"معلومات {member}",
        color=discord.Color.blurple()
    )
    embed.add_field(name="ID", value=str(member.id))
    embed.add_field(
        name="تاريخ إنشاء الحساب",
        value=discord.utils.format_dt(member.created_at, style="D"),
        inline=False
    )
    if member.joined_at:
        embed.add_field(
            name="تاريخ دخول السيرفر",
            value=discord.utils.format_dt(member.joined_at, style="D"),
            inline=False
        )
    embed.set_thumbnail(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="عرض صورة عضو")
async def avatar(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user
    embed = discord.Embed(
        title=f"صورة {member}",
        color=discord.Color.blurple()
    )
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rps", description="لعبة حجر ورقة مقص")
@app_commands.choices(choice=[
    app_commands.Choice(name="حجر", value="حجر"),
    app_commands.Choice(name="ورقة", value="ورقة"),
    app_commands.Choice(name="مقص", value="مقص")
])
async def rps(
    interaction: discord.Interaction,
    choice: app_commands.Choice[str]
):
    bot_choice = random.choice(["حجر", "ورقة", "مقص"])
    if choice.value == bot_choice:
        result = "تعادل!"
    elif (choice.value, bot_choice) in [
        ("حجر", "مقص"),
        ("ورقة", "حجر"),
        ("مقص", "ورقة")
    ]:
        result = "فزت! 🎉"
    else:
        result = "خسرت، حاول مرة ثانية."

    await interaction.response.send_message(
        f"اختيارك: **{choice.value}**\n"
        f"اختياري: **{bot_choice}**\n{result}"
    )


@bot.tree.command(name="guess", description="خمن الرقم من 1 إلى 10")
async def guess(
    interaction: discord.Interaction,
    number: app_commands.Range[int, 1, 10]
):
    answer = random.randint(1, 10)
    if number == answer:
        result = "صحيح! فزت 🎉"
    else:
        result = f"خطأ! الرقم الصحيح هو **{answer}**."
    await interaction.response.send_message(result)


@bot.tree.command(name="help", description="عرض أوامر البوت")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="TURKI SYSTEMS | الأوامر",
        description=(
            "**التكت:** `/ticket_setup`\n"
            "**الترحيب:** `/welcome_setup` `/welcome_test`\n"
            "**الاقتراحات:** `/suggestion_setup` `/suggest`\n"
            "**الإدارة:** `/ban` `/unban` `/kick` `/timeout` "
            "`/untimeout` `/warn` `/warnings` `/clearwarns` "
            "`/clear` `/slowmode` `/lock` `/unlock`\n"
            "**الإعلانات:** `/announce` `/poll`\n"
            "**الاقتصاد:** `/balance` `/daily` `/pay` `/work` `/leaderboard`\n"
            "**عام:** `/ping` `/serverinfo` `/userinfo` `/avatar` `/rps` `/guess`"
        ),
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# ERROR HANDLER
# =========================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "ما عندك الصلاحيات المطلوبة لاستخدام الأمر."
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = "البوت ما عنده الصلاحيات المطلوبة."
    else:
        print(f"Slash command error: {repr(error)}")
        message = "صار خطأ أثناء تنفيذ الأمر. راجع Console في Replit."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# =========================
# START
# =========================

bot.run(TOKEN)
