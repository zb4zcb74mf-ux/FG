import os
import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import describe

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 📌 آيدي روم اللوق (Log Channel)
LOG_CHANNEL_ID = 1559509848360493087

# 📌 آيدي رتبة الدعم الفني / الإدارة
STAFF_ROLE_ID = 1559513400101310475

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        bot.add_view(TicketSelectView(None))
        synced = await bot.tree.sync()
        print(f"تمت مزامنة جميع الأوامر بنجاح ({len(synced)} أمر)")
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
# 🎨 أمر الإمبد الجديد (للكتابة اليدوية بخط أسود)
# ==========================================
@bot.tree.command(name="embed", description="إرسال إمبد مخصص مع نصك وصورتك بخط جانبي أسود")
@describe(
    text="اكتب الكلام الذي تريده داخل الإمبد",
    image="اختر الصورة التي تظهر في أسفل الإمبد"
)
async def custom_embed(interaction: discord.Interaction, text: str, image: discord.Attachment):
    formatted_text = text.replace("\\n", "\n")

    embed = discord.Embed(
        description=formatted_text,
        color=0x000000  # خط جانبي أسود فخم
    )
    embed.set_image(url=image.url)

    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("تم إرسال الإمبد بنجاح!", ephemeral=True)


# ==========================================
# ⚙️ قسم لوحة تحكم / خصائص التذكرة
# ==========================================

class CloseReasonModal(discord.ui.Modal, title="تقرير إغلاق التذكرة"):
    reason = discord.ui.TextInput(
        label="سبب الإغلاق أو التقرير الإداري",
        style=discord.TextStyle.paragraph,
        placeholder="اكتب تفاصيل التقرير أو سبب إغلاق التذكرة هنا...",
        required=True,
        max_length=500
    )

    def __init__(self, ticket_channel):
        super().__init__()
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        closer = interaction.user
        report_text = self.reason.value

        opener_mention = "العضو"
        if self.ticket_channel.topic:
            for part in self.ticket_channel.topic.split("|"):
                if "صاحب التذكرة:" in part:
                    opener_mention = part.replace("صاحب التذكرة:", "").strip()

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🔒 | تم إغلاق تذكرة جديدة",
                description=f"**روم التذكرة:** {self.ticket_channel.name}\n**صاحب التذكرة:** {opener_mention}\n**تم الإغلاق بواسطة:** {closer.mention}\n\n**📄 تقرير الإغلاق:**\n{report_text}",
                color=0x000000
            )
            await log_channel.send(embed=log_embed)

        try:
            if "!" in opener_mention:
                member_id = int(opener_mention.replace("<@!", "").replace(">", ""))
            else:
                member_id = int(opener_mention.replace("<@", "").replace(">", ""))
            
            opener_member = interaction.guild.get_member(member_id)
            if opener_member:
                dm_embed = discord.Embed(
                    title="🔒 تم إغلاق التذكرة",
                    description=f"مرحباً {opener_member.mention}، تم إغلاق تذكرتك بنجاح.\n\n**📄 تقرير الإدارة:**\n{report_text}",
                    color=0x000000
                )
                await opener_member.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message("🔒 جاري إغلاق التذكرة وحذف الروم وتسجيل التقرير...", ephemeral=True)
        await self.ticket_channel.delete()

class TicketSettingsSelect(discord.ui.Select):
    def __init__(self, ticket_channel):
        self.ticket_channel = ticket_channel
        options = [
            discord.SelectOption(label="إغلاق / فتح التذكرة", description="قم بإغلاق أو إعادة فتح هذه التذكرة", emoji="🔒"),
            discord.SelectOption(label="معلومات التذكرة", description="عرض معلومات تفصيلية حول التذكرة", emoji="❓"),
            discord.SelectOption(label="طلب نسخة من التذكرة", description="احصل على نسخة محفوظة من محتويات التذكرة", emoji="📁"),
            discord.SelectOption(label="طلب مساعدة مشرف / تذكير العضو", description="اطلب تدخل مشرف أو ذكر العضو المعني", emoji="📢"),
            discord.SelectOption(label="حذف التذكرة", description="حذف التذكرة بشكل دائم", emoji="🗑️")
        ]
        super().__init__(placeholder="⚙️ | خصائص التذكرة", min_values=1, max_values=1, options=options, custom_id="ticket_settings_dropdown")

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if "إغلاق" in choice:
            await interaction.response.send_modal(CloseReasonModal(self.ticket_channel))
        elif "معلومات" in choice:
            await interaction.response.send_message(f"ℹ️ هذه التذكرة تخص الروم: {self.ticket_channel.name}", ephemeral=True)
        elif "نسخة" in choice:
            await interaction.response.send_message("📁 تم طلب نسخة من محادثات التذكرة بنجاح.", ephemeral=True)
        elif "مساعدة" in choice:
            await interaction.response.send_message("📢 تم تنبيه الإدارة والمشرفين للتدخل في التذكرة.", ephemeral=True)
        elif "حذف" in choice:
            await interaction.response.send_message("🗑️ جاري حذف التذكرة نهائياً...", ephemeral=True)
            await self.ticket_channel.delete()

class TicketSettingsView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.add_item(TicketSettingsSelect(ticket_channel))


# ==========================================
# 🎫 نظام أزرار وأقسام التذاكر الأساسية
# ==========================================

class InsideTicketControlView(discord.ui.View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.claimed_by = None

    @discord.ui.button(label="استلام التذكرة", style=discord.ButtonStyle.secondary, emoji="👮‍♂️", custom_id="claim_ticket_btn")
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

    @discord.ui.button(label="⚙️ | خصائص التذكرة", style=discord.ButtonStyle.secondary, custom_id="settings_menu_btn")
    async def settings_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "اختر الإجراء المطلوب من القائمة أدناه:",
            view=TicketSettingsView(self.ticket_channel),
            ephemeral=True
        )

class TicketSelect(discord.ui.Select):
    def __init__(self, inner_image_url):
        self.inner_image_url = inner_image_url
        options = [
            discord.SelectOption(label="مسؤولين السيرفر", description="Administrator", emoji="👑"),
            discord.SelectOption(label="الادارة العليا", description="High Staff", emoji="🛡️"),
            discord.SelectOption(label="تكت الادارة", description="Staff Ticket", emoji="🎫"),
            discord.SelectOption(label="الدعم الفني للايفنت", description="Event Support", emoji="🎉"),
            discord.SelectOption(label="الدعم الفني للكيك", description="Kick Support", emoji="🎮"),
            discord.SelectOption(label="الدعم الفني للبنات", description="Girls Support", emoji="🌸")
        ]
        super().__init__(placeholder="اختر فئة التذكرة", min_values=1, max_values=1, options=options, custom_id="main_ticket_select")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        selected_category = self.values[0]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        if STAFF_ROLE_ID != 0:
            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

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
        if self.inner_image_url:
            embed.set_image(url=self.inner_image_url)

        await ticket_channel.send(
            content=f"مرحباً بك {member.mention}",
            embed=embed, 
            view=InsideTicketControlView(ticket_channel)
        )
        
        await interaction.response.send_message(f"تم فتح تذكرتك بنجاح في الروم: {ticket_channel.mention}", ephemeral=True)

class TicketSelectView(discord.ui.View):
    def __init__(self, inner_image_url: str):
        super().__init__(timeout=None)
        self.inner_image_url = inner_image_url
        if inner_image_url:
            self.add_item(TicketSelect(inner_image_url))

class MainTicketButtonView(discord.ui.View):
    def __init__(self, inner_image_url: str, custom_message: str):
        super().__init__(timeout=None)
        self.inner_image_url = inner_image_url
        self.custom_message = custom_message

    @discord.ui.button(label="اختر فئة التذكرة", style=discord.ButtonStyle.secondary, emoji="🎫", custom_id="open_main_ticket_btn")
    async def open_selection(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=self.custom_message,
            color=0x000000
        )
        if self.inner_image_url:
            embed.set_image(url=self.inner_image_url)

        await interaction.response.send_message(
            embed=embed,
            view=TicketSelectView(self.inner_image_url),
            ephemeral=True
        )

# أوامر إعداد التذاكر
@bot.tree.command(name="setup-ticket", description="إنشاء اللوحة الكبيرة للتذاكر")
@app_commands.describe(
    banner="صورة البانر في اللوحة الأساسية",
    inner_image="صورة اللوحة الداخلية التي تظهر داخل التذكرة"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, banner: discord.Attachment, inner_image: discord.Attachment):
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
        view=MainTicketButtonView(inner_image.url, "من هنا يمكنك فتح التذكرة التي تريدها")
    )
    await interaction.response.send_message("تم إرسال اللوحة بنجاح!", ephemeral=True)

@bot.tree.command(name="setup-mini-ticket", description="إنشاء اللوحة المصغرة الفخمة")
@app_commands.describe(
    message="اكتب النص المختصر",
    banner="صورة البانر في اللوحة الأساسية",
    icon="الأيقونة المصغرة",
    inner_image="صورة اللوحة الداخلية التي تظهر داخل التذكرة"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_mini_ticket(interaction: discord.Interaction, message: str, banner: discord.Attachment, icon: discord.Attachment, inner_image: discord.Attachment):
    formatted_message = message.replace("\\n", "\n")
    embed = discord.Embed(description=formatted_message, color=0x000000)
    embed.set_thumbnail(url=icon.url)
    embed.set_image(url=banner.url)

    await interaction.channel.send(
        embed=embed, 
        view=MainTicketButtonView(inner_image.url, formatted_message)
    )
    await interaction.response.send_message("تم إرسال اللوحة المصغرة بنجاح!", ephemeral=True)

token = os.getenv("DDD")
bot.run(token)
