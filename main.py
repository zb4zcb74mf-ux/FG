import os
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# آيدي روم اللوق (Log Channel)
LOG_CHANNEL_ID = 1559509848360493087

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"تمت مزامنة الأوامر بنجاح")
    except Exception as e:
        print(e)

# الرد التلقائي على السلام داخل التذاكر
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.name.startswith("ticket-"):
        content = message.content.strip().lower()
        if "السلام عليكم" in message.content or content in ["السلام عليكم", "السلام عليكم ورحمة الله", "سلام عليكم"]:
            await message.reply("وعليكم السلام ورحمة الله وبركاته")

    await bot.process_commands(message)


# ==========================================
# ⚙️ قسم لوحة تحكم / خصائص التذكرة (مفصول لحاله)
# ==========================================

# صندوق كتابة تقرير الإغلاق
class CloseReasonModal(discord.ui.Modal, title="تقرير إغلاق التذكرة"):
    reason = discord.ui.TextInput(
        label="سبب الإغلاق أو التقرير الإداري",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب تفاصيل التقرير أو سبب إغلاق التذكرة هنا...",
        required=True,
        max_length=500
    )

    def __init__(self, ticket_channel, opener_member):
        super().__init__()
        self.ticket_channel = ticket_channel
        self.opener_member = opener_member

    async def on_submit(self, interaction: discord.Interaction):
        closer = interaction.user
        report_text = self.reason.value

        # إرسال اللوق لروم السجلات
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🔒 | تم إغلاق تذكرة جديدة",
                description=f"**روم التذكرة:** {self.ticket_channel.name}\n**صاحب التذكرة:** {self.opener_member.mention}\n**تم الإغلاق بواسطة:** {closer.mention}\n\n**📄 تقرير الإغلاق:**\n{report_text}",
                color=0x000000
            )
            await log_channel.send(embed=log_embed)

        # إرسال الرسالة الخاصة (DM) لصاحب التذكرة
        try:
            dm_embed = discord.Embed(
                title="🔒 تم إغلاق التذكرة",
                description=f"مرحباً {self.opener_member.mention}، تم إغلاق تذكرتك بنجاح.\n\n**📄 تقرير الإدارة:**\n{report_text}",
                color=0x000000
            )
            await self.opener_member.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message("🔒 جاري إغلاق التذكرة وحذف الروم وتسجيل التقرير...", ephemeral=True)
        await self.ticket_channel.delete()

# القائمة المنسدلة لخصائص التذكرة
class TicketSettingsSelect(discord.ui.Select):
    def __init__(self, ticket_channel, opener_member):
        self.ticket_channel = ticket_channel
        self.opener_member = opener_member
        options = [
            discord.SelectOption(label="إغلاق / فتح التذكرة", description="قم بإغلاق أو إعادة فتح هذه التذكرة", emoji="🔒"),
            discord.SelectOption(label="معلومات التذكرة", description="عرض معلومات تفصيلية حول التذكرة", emoji="❓"),
            discord.SelectOption(label="طلب نسخة من التذكرة", description="احصل على نسخة محفوظة من محتويات التذكرة", emoji="📁"),
            discord.SelectOption(label="طلب مساعدة مشرف / تذكير العضو", description="اطلب تدخل مشرف أو ذكر العضو المعني", emoji="📢"),
            discord.SelectOption(label="حذف التذكرة", description="حذف التذكرة بشكل دائم", emoji="🗑️")
        ]
        super().__init__(placeholder="⚙️ | خصائص التذكرة", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if "إغلاق" in choice:
            await interaction.response.send_modal(CloseReasonModal(self.ticket_channel, self.opener_member))
        elif "معلومات" in choice:
            await interaction.response.send_message(f"ℹ️ هذه التذكرة تخص العضو: {self.opener_member.mention} في الروم: {self.ticket_channel.name}", ephemeral=True)
        elif "نسخة" in choice:
            await interaction.response.send_message("📁 تم طلب نسخة من محادثات التذكرة بنجاح.", ephemeral=True)
        elif "مساعدة" in choice:
            await interaction.response.send_message("📢 تم تنبيه الإدارة والمشرفين للتدخل في التذكرة.", ephemeral=True)
        elif "حذف" in choice:
            await interaction.response.send_message("🗑️ جاري حذف التذكرة نهائياً...", ephemeral=True)
            await self.ticket_channel.delete()

class TicketSettingsView(discord.ui.View):
    def __init__(self, ticket_channel, opener_member):
        super().__init__(timeout=None)
        self.add_item(TicketSettingsSelect(ticket_channel, opener_member))


# ==========================================
# 🎫 نظام أزرار وأقسام التذاكر الأساسية
# ==========================================

# أزرار التحكم داخل الروم (استلام + زر خصائص التذكرة)
class InsideTicketControlView(discord.ui.View):
    def __init__(self, ticket_channel, opener_member):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.opener_member = opener_member
        self.claimed_by = None

    @discord.ui.button(label="استلام التذكرة", style=discord.ButtonStyle.secondary, emoji="👮‍♂️")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.claimed_by = interaction.user
        button.disabled = True
        button.label = f"تم الاستلام بواسطة {interaction.user.name}"
        button.style = discord.ButtonStyle.success
        
        embed = discord.Embed(
            description=f"✅ **تم استلام التذكرة بواسطة** {interaction.user.mention}",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
        await interaction.message.edit(view=self)

    @discord.ui.button(label="⚙️ | خصائص التذكرة", style=discord.ButtonStyle.secondary)
    async def settings_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        # استدعاء لوحة التحكم الخاصة بالخصائص
        await interaction.response.send_message(
            "اختر الإجراء المطلوب من القائمة أدناه:",
            view=TicketSettingsView(self.ticket_channel, self.opener_member),
            ephemeral=True
        )

# القائمة المنسدلة لاختيار الفئات
class TicketSelect(discord.ui.Select):
    def __init__(self, banner_url):
        self.banner_url = banner_url
        options = [
            discord.SelectOption(label="مسؤولين السيرفر", description="Administrator", emoji="👑"),
            discord.SelectOption(label="الادارة العليا", description="High Staff", emoji="🛡️"),
            discord.SelectOption(label="تكت الادارة", description="Staff Ticket", emoji="🎫"),
            discord.SelectOption(label="الدعم الفني للايفنت", description="Event Support", emoji="🎉"),
            discord.SelectOption(label="الدعم الفني للكيك", description="Kick Support", emoji="🎮"),
            discord.SelectOption(label="الدعم الفني للبنات", description="Girls Support", emoji="🌸")
        ]
        super().__init__(placeholder="اختر فئة التذكرة", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        selected_category = self.values[0]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            overwrites=overwrites,
            topic=f"قسم التذكرة: {selected_category} | صاحب التذكرة: {member.mention}"
        )

        ticket_inner_text = (
            "ملاحظة :\n\n"
            "• لست بحاجة لإنتظار رد من الإدارة، يُفضل كتابة سبب فتحك للتذكرة لتسهيل التواصل\n"
            "• يُرجى عدم إزعاج الفريق الإداري والتصرف بجدية، سيتم الرد عليك عند توفر مسؤول"
        )

        embed = discord.Embed(
            title=f"🎫 تذكرة جديدة",
            description=ticket_inner_text,
            color=0x000000
        )
        embed.set_image(url=self.banner_url)

        await ticket_channel.send(
            content=f"مرحباً بك {member.mention}",
            embed=embed, 
            view=InsideTicketControlView(ticket_channel, member)
        )
        
        await interaction.response.send_message(f"تم فتح تذكرتك بنجاح في الروم: {ticket_channel.mention}", ephemeral=True)

class TicketSelectView(discord.ui.View):
    def __init__(self, banner_url: str):
        super().__init__(timeout=None)
        self.banner_url = banner_url
        self.add_item(TicketSelect(banner_url))

# الزر الرئيسي المؤقت
class MainTicketButtonView(discord.ui.View):
    def __init__(self, banner_url: str, custom_message: str):
        super().__init__(timeout=None)
        self.banner_url = banner_url
        self.custom_message = custom_message

    @discord.ui.button(label="اختر فئة التذكرة", style=discord.ButtonStyle.secondary, emoji="🎫")
    async def open_selection(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=self.custom_message,
            color=0x000000
        )
        embed.set_image(url=self.banner_url)

        await interaction.response.send_message(
            embed=embed,
            view=TicketSelectView(self.banner_url),
            ephemeral=True
        )

# أوامر الإعداد
@bot.tree.command(name="setup-ticket", description="إنشاء اللوحة الكبيرة للتذاكر")
@app_commands.describe(banner="اختر صورة البانر الكبيرة الخاصة بك")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, banner: discord.Attachment):
    ticket_text = (
        "مرحبًا بك في نظام التذاكر الخاص بـ AT Community\n\n"
        "يرجى اختيار القسم المناسب وكتابة تفاصيل مشكلتك مباشرة قبل دخول الإدارة إلى التذكرة حتى يتمكن الفريق من مراجعتها والرد عليك بأسرع وقت كذا لك نرجو منك احترام قوانين السيرفر كذالك قواعد واساسيات الدسكورد\n\n"
        "يرجى ذكر:\n"
        "• ما هي المشكلة أو الطلب\n"
        "• من هم الأشخاص المرتبطون بها\n"
        "• أي صور أو مقاطع أو أدلة إن وجدت\n"
        "• متى بدأت أو متى حدثت\n\n"
        "في حال عدم توضيح المشكلة مسبقا قد يتأخر الرد أو يتم إغلاق التذكرة"
    )

    embed = discord.Embed(description=ticket_text, color=0x000000)
    embed.set_image(url=banner.url)

    await interaction.channel.send(
        embed=embed, 
        view=MainTicketButtonView(banner.url, "من هنا يمكنك فتح التذكرة التي تريدها")
    )
    await interaction.response.send_message("تم إرسال اللوحة بنجاح!", ephemeral=True)

@bot.tree.command(name="setup-mini-ticket", description="إنشاء اللوحة المصغرة الفخمة")
@app_commands.describe(message="اكتب النص المختصر", banner="اختر صورة البانر", icon="اختر الأيقونة المصغرة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_mini_ticket(interaction: discord.Interaction, message: str, banner: discord.Attachment, icon: discord.Attachment):
    formatted_message = message.replace("\\n", "\n")
    embed = discord.Embed(description=formatted_message, color=0x000000)
    embed.set_thumbnail(url=icon.url)
    embed.set_image(url=banner.url)

    await interaction.channel.send(
        embed=embed, 
        view=MainTicketButtonView(banner.url, formatted_message)
    )
    await interaction.response.send_message("تم إرسال اللوحة المصغرة بنجاح!", ephemeral=True)

token = os.getenv("DDD")
bot.run(token)
