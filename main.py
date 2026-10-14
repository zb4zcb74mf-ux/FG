import os
import json
import sqlite3
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
DB = "turki_systems.db"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


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
            status TEXT,
            ticket_type TEXT,
            reason TEXT,
            claimed_by TEXT,
            opened_at TEXT
        )
        """)
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT")
        except:
            pass
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN reason TEXT")
        except:
            pass
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN claimed_by TEXT")
        except:
            pass
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN opened_at TEXT")
        except:
            pass


def defaults():
    return {
        "ticket_title": "نظام التذاكر",
        "ticket_description": (
            "**Staff Support**\n"
            "**High Support**\n"
            "**Event Support**\n"
            "**Shop Support**\n"
            "**Kick Support**\n\n"
            "• يرجى الالتزام الكامل بالقوانين داخل التذكرة.\n"
            "• جميع الرسائل محفوظة دائمًا لضمان النظام.\n"
            "• ممنوع تمامًا فتح تذكرة بلا سبب واضح.\n"
            "• في حال عدم الرد لمدة 6 ساعات يتم إغلاق التذكرة.\n"
            "• يرجى كتابة موضوعك مباشرة عند فتح التذكرة."
        ),
        "ticket_banner": "",
        "ticket_image": "",
        "ticket_inner_image": "",
        "ticket_color": "2B2D31",
        "ticket_footer": "سيتم فتح قناة خاصة للتواصل مع فريق الدعم",
        "ticket_category": None,
        "ticket_buttons": [
            {"name": "Staff", "emoji": "🛡️", "color": "danger"},
            {"name": "High", "emoji": "✖️", "color": "danger"},
            {"name": "Shop", "emoji": "🛒", "color": "danger"},
            {"name": "Event", "emoji": "🎆", "color": "danger"},
            {"name": "Mod", "emoji": "🟢", "color": "success"}
        ],
        "ticket_counter": 0,
        "welcome_channel": None,
        "welcome_title": "Welcome To Server",
        "welcome_text": (
            "`📚 | Rules • القوانين`\n"
            "`📡 | Social • التواصل`\n"
            "`📢 | Announcement • الاخبار`"
        ),
        "welcome_image": "",
        "welcome_thumbnail": "",
        "welcome_color": "E74C3C",
        "welcome_footer": True,
        "leave_channel": None,
        "leave_text": "غادر {user} السيرفر.",
        "leave_image": "",
        "leave_color": "808080",
        "suggestion_channel": None,
        "log_channel": None
    }


def get_settings(guild_id):
    with connect() as conn:
        row = conn.execute("SELECT data FROM settings WHERE guild_id=?", (str(guild_id),)).fetchone()
    data = defaults()
    if row:
        try:
            data.update(json.loads(row["data"]))
        except:
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
        return discord.Color(int(str(value).strip().replace("#", ""), 16))
    except:
        return discord.Color.blurple()


def is_url(value):
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def is_admin(interaction):
    return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild


async def require_admin(interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ تحتاج صلاحية إدارة السيرفر.", ephemeral=True)
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
            except:
                pass


def ticket_embed(settings):
    embed = discord.Embed(
        title=settings.get("ticket_title", "نظام التذاكر"),
        description=settings.get("ticket_description", ""),
        color=color(settings.get("ticket_color", "2B2D31"))
    )
    banner = settings.get("ticket_banner", "")
    if banner and is_url(banner):
        embed.set_image(url=banner)
    image = settings.get("ticket_image", "")
    if image and is_url(image):
        embed.set_thumbnail(url=image)
    footer = settings.get("ticket_footer", "سيتم فتح قناة خاصة للتواصل مع فريق الدعم")
    if footer:
        embed.set_footer(text=footer)
    return embed


class TicketReasonModal(discord.ui.Modal, title="سبب فتح التذكرة"):
    reason = discord.ui.TextInput(
        label="اشرح سبب فتح التذكرة",
        placeholder="مثال: مشكلة في الدفع، استفسار عن خدمة...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    def __init__(self, ticket_name: str):
        super().__init__()
        self.ticket_name = ticket_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            if not guild:
                return await interaction.response.send_message("خطأ.", ephemeral=True)

            with connect() as conn:
                row = conn.execute("""
                    SELECT channel_id FROM tickets
                    WHERE guild_id=? AND user_id=? AND status='open'
                """, (str(guild.id), str(interaction.user.id))).fetchone()

            if row:
                existing = guild.get_channel(int(row["channel_id"]))
                if existing:
                    return await interaction.response.send_message(
                        f"عندك تذكرة مفتوحة: {existing.mention}", ephemeral=True
                    )

            settings = get_settings(guild.id)
            category_id = settings.get("ticket_category")
            category = guild.get_channel(int(category_id)) if category_id else None
            if not isinstance(category, discord.CategoryChannel):
                category = None

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True, attach_files=True
                )
            }
            if guild.me:
                overwrites[guild.me] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
                )
            for role in guild.roles:
                if role.permissions.administrator or role.permissions.manage_channels:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True
                    )

            settings["ticket_counter"] = int(settings.get("ticket_counter", 0)) + 1
            save_settings(guild.id, settings)

            try:
                channel = await guild.create_text_channel(
                    f"ticket-{settings['ticket_counter']:04d}",
                    category=category,
                    overwrites=overwrites
                )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "❌ البوت يحتاج صلاحية Manage Channels.", ephemeral=True
                )

            now = datetime.now(timezone.utc).isoformat()
            with connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tickets
                    (channel_id, guild_id, user_id, status, ticket_type, reason, claimed_by, opened_at)
                    VALUES(?, ?, ?, 'open', ?, ?, NULL, ?)
                """, (str(channel.id), str(guild.id), str(interaction.user.id), self.ticket_name, self.reason.value, now))

            embed = discord.Embed(
                title=f"🛡️ {self.ticket_name}",
                description=(
                    f"مرحبا بك في الدعم الفني ، يرجى عدم تجاهل التذكرة\n\n"
                    f"👤 **صاحب التذكرة**\n{interaction.user.mention}\n\n"
                    f"📅 **التاريخ**\n{discord.utils.format_dt(datetime.now(timezone.utc), style='F')}\n\n"
                    f"📝 **سبب التذكرة**\n{self.reason.value}"
                ),
                color=color(settings.get("ticket_color", "2B2D31"))
            )
            inner_image = settings.get("ticket_inner_image") or settings.get("ticket_banner") or ""
            if inner_image and is_url(inner_image):
                embed.set_image(url=inner_image)
            embed.set_footer(text="يمكنك إغلاق التذكرة أو استلامها أو استخدام الإجراءات الأخرى")

            await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
            await interaction.response.send_message(f"✅ تم فتح تذكرتك: {channel.mention}", ephemeral=True)
            await log_action(guild, f"🎫 تذكرة جديدة: {channel.mention} بواسطة {interaction.user.mention}")

        except Exception as e:
            print(f"[Ticket Error] {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"❌ حصل خطأ:\n```{e}```", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ حصل خطأ:\n```{e}```", ephemeral=True)
            except:
                pass


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

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketReasonModal(self.ticket_name))


class TicketPanelView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=None)
        for index, item in enumerate(items[:25]):
            self.add_item(TicketButton(item, index))


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام", emoji="🛡️", style=discord.ButtonStyle.secondary, custom_id="turki_ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)

        with connect() as conn:
            row = conn.execute("SELECT claimed_by FROM tickets WHERE channel_id=? AND status='open'", (str(interaction.channel.id),)).fetchone()

        if row and row["claimed_by"]:
            return await interaction.response.send_message(f"هالتذكرة مستلمة مسبقًا بواسطة <@{row['claimed_by']}>", ephemeral=True)

        with connect() as conn:
            conn.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?", (str(interaction.user.id), str(interaction.channel.id)))

        await interaction.response.send_message(f"✅ تم استلام التذكرة بواسطة {interaction.user.mention}")
        await log_action(interaction.guild, f"🛡️ استلام التذكرة {interaction.channel.mention} بواسطة {interaction.user.mention}")

    @discord.ui.button(label="إغلاق", emoji="❌", style=discord.ButtonStyle.danger, custom_id="turki_ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        guild = interaction.guild
        if not guild or not isinstance(channel, discord.TextChannel):
            return

        with connect() as conn:
            row = conn.execute("""
                SELECT user_id, ticket_type, reason, claimed_by FROM tickets
                WHERE channel_id=? AND status='open'
            """, (str(channel.id),)).fetchone()

        if not row:
            return await interaction.response.send_message("لم أجد تذكرة مفتوحة هنا.", ephemeral=True)

        staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
        owner_id = row["user_id"]
        if not staff and str(interaction.user.id) != owner_id:
            return await interaction.response.send_message("❌ صاحب التذكرة أو الإدارة فقط.", ephemeral=True)

        with connect() as conn:
            conn.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (str(channel.id),))

        await interaction.response.send_message("🔒 سيتم حذف التذكرة بعد 5 ثوانٍ...")
        await log_action(guild, f"🔒 إغلاق التذكرة `{channel.name}` بواسطة {interaction.user.mention}")

        try:
            member = guild.get_member(int(owner_id)) or await bot.fetch_user(int(owner_id))
            if member:
                dm_embed = discord.Embed(
                    title="تم إغلاق التذكرة 🔒",
                    description=f"مرحبًا {member.mention}، تم حل تذكرتك.",
                    color=discord.Color.green()
                )
                participants = [f"<@{owner_id}>"]
                if row["claimed_by"]:
                    participants.append(f"<@{row['claimed_by']}>")
                dm_embed.add_field(name="قائمة المستخدمين", value="\n".join(f"• {p}" for p in participants), inline=False)
                dm_embed.add_field(name="تم فتح بواسطة", value=f"<@{owner_id}>", inline=True)
                if row["claimed_by"]:
                    dm_embed.add_field(name="تم استلام بواسطة", value=f"<@{row['claimed_by']}>", inline=True)
                dm_embed.add_field(name="تم إغلاق بواسطة", value=interaction.user.mention, inline=True)
                if row["reason"]:
                    dm_embed.add_field(name="سبب التذكرة", value=row["reason"][:300], inline=False)
                dm_embed.set_footer(text=guild.name)
                dm_embed.timestamp = datetime.now(timezone.utc)
                await member.send(embed=dm_embed)
        except:
            pass

        await asyncio.sleep(5)
        try:
            await channel.delete()
        except:
            pass

    @discord.ui.button(label="إجراءات أخرى", emoji="⋯", style=discord.ButtonStyle.secondary, custom_id="turki_ticket_more")
    async def more(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("قريبًا...", ephemeral=True)


@bot.tree.command(name="ticketedit", description="تعديل تصميم لوحة التكت")
@app_commands.describe(title="عنوان", description="وصف", banner="بانر", image="صورة مصغرة", inner_image="صورة داخل التذكرة", color_hex="لون", footer="فوتر")
async def ticketedit(interaction: discord.Interaction, title: str = None, description: str = None, banner: str = None, image: str = None, inner_image: str = None, color_hex: str = None, footer: str = None):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    if title is not None:
        settings["ticket_title"] = title[:256]
    if description is not None:
        settings["ticket_description"] = description[:4000]
    if footer is not None:
        settings["ticket_footer"] = footer[:2000]
    for key, value in (("ticket_banner", banner), ("ticket_image", image), ("ticket_inner_image", inner_image)):
        if value is None:
            continue
        if value.lower() in ("remove", "delete", "حذف"):
            settings[key] = ""
        elif is_url(value):
            settings[key] = value
        else:
            return await interaction.response.send_message("رابط غير صحيح", ephemeral=True)
    if color_hex is not None:
        settings["ticket_color"] = color_hex.replace("#", "")
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message("✅ تم الحفظ", embed=ticket_embed(settings), ephemeral=True)


@bot.tree.command(name="ticketbutton", description="إضافة أو حذف زر")
@app_commands.choices(action=[app_commands.Choice(name="إضافة", value="add"), app_commands.Choice(name="حذف", value="remove")])
@app_commands.choices(style=[app_commands.Choice(name="أزرق", value="primary"), app_commands.Choice(name="رمادي", value="secondary"), app_commands.Choice(name="أخضر", value="success"), app_commands.Choice(name="أحمر", value="danger")])
async def ticketbutton(interaction: discord.Interaction, action: app_commands.Choice[str], name: str, emoji: str = None, style: app_commands.Choice[str] = None):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    buttons = settings.get("ticket_buttons", [])
    if action.value == "add":
        if len(buttons) >= 25:
            return await interaction.response.send_message("الحد 25 زر", ephemeral=True)
        buttons.append({"name": name[:80], "emoji": emoji, "color": style.value if style else "primary"})
    else:
        found = next((b for b in buttons if b["name"].lower() == name.lower()), None)
        if not found:
            return await interaction.response.send_message("ما لقيت الزر", ephemeral=True)
        buttons.remove(found)
    settings["ticket_buttons"] = buttons
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message("✅ تم التحديث", ephemeral=True)


@bot.tree.command(name="ticketpreview", description="معاينة لوحة التكت")
async def ticketpreview(interaction: discord.Interaction):
    settings = get_settings(interaction.guild_id)
    await interaction.response.send_message(embed=ticket_embed(settings), view=TicketPanelView(settings.get("ticket_buttons", [])), ephemeral=True)


@bot.tree.command(name="ticketsetup", description="نشر لوحة التكت")
async def ticketsetup(interaction: discord.Interaction, channel: discord.TextChannel, category: discord.CategoryChannel = None):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    settings["ticket_category"] = category.id if category else None
    save_settings(interaction.guild_id, settings)
    await channel.send(embed=ticket_embed(settings), view=TicketPanelView(settings.get("ticket_buttons", [])))
    await interaction.response.send_message(f"✅ تم النشر في {channel.mention}", ephemeral=True)


def replace_vars(text, member):
    return text.replace("{mention}", member.mention).replace("{user}", str(member)).replace("{server}", member.guild.name).replace("{count}", str(member.guild.member_count or 0)).replace("{name}", member.display_name).replace("{id}", str(member.id))


def member_embed(member, settings, is_welcome=True):
    if is_welcome:
        title = settings.get("welcome_title", "Welcome To Server")
        description = settings.get("welcome_text", "")
        image = settings.get("welcome_image", "")
        thumbnail = settings.get("welcome_thumbnail", "")
        hex_color = settings.get("welcome_color", "E74C3C")
        show_footer = settings.get("welcome_footer", True)
    else:
        title = "غادر السيرفر"
        description = replace_vars(settings.get("leave_text", "غادر {user} السيرفر."), member)
        image = settings.get("leave_image", "")
        thumbnail = ""
        hex_color = settings.get("leave_color", "808080")
        show_footer = False

    embed = discord.Embed(title=title, description=replace_vars(description, member) if is_welcome else description, color=color(hex_color))
    if thumbnail and is_url(thumbnail):
        embed.set_thumbnail(url=thumbnail)
    else:
        embed.set_thumbnail(url=member.display_avatar.url)
    if image and is_url(image):
        embed.set_image(url=image)
    if is_welcome and show_footer:
        embed.set_footer(text=str(member.guild.member_count or 0))
    return embed


@bot.event
async def on_member_join(member):
    settings = get_settings(member.guild.id)
    channel_id = settings.get("welcome_channel")
    if channel_id:
        channel = member.guild.get_channel(int(channel_id))
        if channel:
            await channel.send(embed=member_embed(member, settings, True))


@bot.event
async def on_member_remove(member):
    settings = get_settings(member.guild.id)
    channel_id = settings.get("leave_channel")
    if channel_id:
        channel = member.guild.get_channel(int(channel_id))
        if channel:
            await channel.send(embed=member_embed(member, settings, False))


@bot.tree.command(name="welcomesetup", description="تحديد رومات الترحيب")
async def welcomesetup(interaction: discord.Interaction, welcome_channel: discord.TextChannel, leave_channel: discord.TextChannel = None):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    settings["welcome_channel"] = welcome_channel.id
    settings["leave_channel"] = leave_channel.id if leave_channel else None
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message("✅ تم", ephemeral=True)


@bot.tree.command(name="welcomeedit", description="تعديل الترحيب")
@app_commands.choices(kind=[app_commands.Choice(name="الترحيب", value="welcome"), app_commands.Choice(name="المغادرة", value="leave")])
async def welcomeedit(interaction: discord.Interaction, kind: app_commands.Choice[str], title: str = None, text: str = None, image: str = None, thumbnail: str = None, color_hex: str = None):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    if kind.value == "welcome":
        if title: settings["welcome_title"] = title[:256]
        if text: settings["welcome_text"] = text[:2000]
        if image:
            settings["welcome_image"] = "" if image.lower() in ("remove", "حذف") else image if is_url(image) else settings["welcome_image"]
        if thumbnail:
            settings["welcome_thumbnail"] = "" if thumbnail.lower() in ("remove", "حذف") else thumbnail if is_url(thumbnail) else settings["welcome_thumbnail"]
        if color_hex: settings["welcome_color"] = color_hex.replace("#", "")
    else:
        if text: settings["leave_text"] = text[:1800]
        if image:
            settings["leave_image"] = "" if image.lower() in ("remove", "حذف") else image if is_url(image) else settings["leave_image"]
        if color_hex: settings["leave_color"] = color_hex.replace("#", "")
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message("✅ تم", ephemeral=True)


@bot.tree.command(name="welcomepreview", description="معاينة الترحيب")
async def welcomepreview(interaction: discord.Interaction):
    settings = get_settings(interaction.guild_id)
    await interaction.response.send_message(embed=member_embed(interaction.user, settings, True), ephemeral=True)


class SuggestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="مؤيد", emoji="👍", style=discord.ButtonStyle.success, custom_id="turki_suggestion_up")
    async def up(self, interaction, button):
        await interaction.response.send_message("تم", ephemeral=True)

    @discord.ui.button(label="غير مؤيد", emoji="👎", style=discord.ButtonStyle.secondary, custom_id="turki_suggestion_down")
    async def down(self, interaction, button):
        await interaction.response.send_message("تم", ephemeral=True)


@bot.tree.command(name="suggestionsetup", description="روم الاقتراحات")
async def suggestionsetup(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    settings["suggestion_channel"] = channel.id
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(f"تم: {channel.mention}", ephemeral=True)


@bot.tree.command(name="suggest", description="إرسال اقتراح")
async def suggest(interaction: discord.Interaction, text: str):
    settings = get_settings(interaction.guild_id)
    channel_id = settings.get("suggestion_channel")
    channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
    if not channel:
        return await interaction.response.send_message("ما تم تحديد روم الاقتراحات", ephemeral=True)
    embed = discord.Embed(title="💡 اقتراح جديد", description=text[:4000], color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
    embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    await channel.send(embed=embed, view=SuggestionView())
    await interaction.response.send_message("✅ تم إرسال اقتراحك", ephemeral=True)


@bot.tree.command(name="warn", description="تحذير")
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    with connect() as conn:
        conn.execute("INSERT INTO warnings(guild_id, user_id, moderator_id, reason, created_at) VALUES(?,?,?,?,?)",
                     (str(interaction.guild_id), str(member.id), str(interaction.user.id), reason, datetime.now(timezone.utc).isoformat()))
    await interaction.response.send_message(f"⚠️ تم تحذير {member.mention}")


@bot.tree.command(name="warnings", description="عرض التحذيرات")
@app_commands.default_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    with connect() as conn:
        rows = conn.execute("SELECT reason, moderator_id FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                            (str(interaction.guild_id), str(member.id))).fetchall()
    if not rows:
        return await interaction.response.send_message("لا توجد تحذيرات", ephemeral=True)
    text = "\n".join(f"• {r['reason']} — <@{r['moderator_id']}>" for r in rows)
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="clearwarnings", description="مسح التحذيرات")
@app_commands.default_permissions(administrator=True)
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    with connect() as conn:
        conn.execute("DELETE FROM warnings WHERE guild_id=? AND user_id=?", (str(interaction.guild_id), str(member.id)))
    await interaction.response.send_message("✅ تم المسح")


@bot.tree.command(name="kick", description="طرد")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 تم طرد {member.mention}")
    except:
        await interaction.response.send_message("تعذر الطرد", ephemeral=True)


@bot.tree.command(name="ban", description="حظر")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 تم حظر {member.mention}")
    except:
        await interaction.response.send_message("تعذر الحظر", ephemeral=True)


@bot.tree.command(name="timeout", description="إسكات")
@app_commands.default_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "بدون سبب"):
    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"🔇 تم إسكات {member.mention} لمدة {minutes} دقيقة")
    except:
        await interaction.response.send_message("تعذر الإسكات", ephemeral=True)


@bot.tree.command(name="purge", description="حذف رسائل")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 تم حذف {len(deleted)} رسالة", ephemeral=True)


@bot.tree.command(name="lock", description="قفل الروم")
@app_commands.default_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔒 تم القفل")


@bot.tree.command(name="unlock", description="فتح الروم")
@app_commands.default_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔓 تم الفتح")


@bot.tree.command(name="setlogs", description="روم السجلات")
async def setlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await require_admin(interaction):
        return
    settings = get_settings(interaction.guild_id)
    settings["log_channel"] = channel.id
    save_settings(interaction.guild_id, settings)
    await interaction.response.send_message(f"تم: {channel.mention}", ephemeral=True)


@bot.tree.command(name="serverinfo", description="معلومات السيرفر")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=guild.name, description=f"الأعضاء: {guild.member_count}\nالرومات: {len(guild.channels)}", color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="معلومات عضو")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=str(member), description=f"ID: {member.id}", color=discord.Color.blurple())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="إنشاء الحساب", value=discord.utils.format_dt(member.created_at, "D"))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="صورة العضو")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"صورة {member}")
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="helpme", description="الأوامر")
async def helpme(interaction: discord.Interaction):
    embed = discord.Embed(
        title="TURKI SYSTEMS",
        description=(
            "**التكت**\n`/ticketedit` `/ticketbutton` `/ticketpreview` `/ticketsetup`\n\n"
            "**الترحيب**\n`/welcomesetup` `/welcomeedit` `/welcomepreview`\n\n"
            "**أخرى**\n`/suggestionsetup` `/suggest` `/setlogs`\n\n"
            "**إدارة**\n`/warn` `/warnings` `/kick` `/ban` `/timeout` `/purge` `/lock` `/unlock`"
        ),
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    setup_db()
    bot.add_view(TicketControlView())
    bot.add_view(SuggestionView())
    for row in connect().execute("SELECT data FROM settings").fetchall():
        try:
            settings = json.loads(row["data"])
            bot.add_view(TicketPanelView(settings.get("ticket_buttons", [])))
        except:
            pass
    try:
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()
    except Exception as e:
        print("Sync error:", e)
    print(f"TURKI SYSTEMS online as {bot.user}")


if not TOKEN:
    print("ضع DISCORD_TOKEN في Secrets")
else:
    setup_db()
    bot.run(TOKEN)
