import os
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"تمت مزامنة الأوامر بنجاح")
    except Exception as e:
        print(e)

# القائمة المنسدلة لاختيار القسم (أقسام taqat الاحترافية)
class TicketSelect(discord.ui.Select):
    def __init__(self):
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

        embed = discord.Embed(
            title=f"🎫 تذكرة جديدة - {selected_category}",
            description=f"مرحباً بك {member.mention}!\nتم فتح التذكرة في قسم **{selected_category}**.\nيرجى كتابة تفاصيل طلبك بوضوح تام، وسيقوم الفريق المعني بالرد عليك في أقرب وقت.",
            color=0x000000
        )

        class CloseView(discord.ui.View):
            @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒")
            async def close_ticket(self, inter: discord.Interaction, btn: discord.ui.Button):
                await inter.response.send_message("جاري إغلاق التذكرة وحذف الروم...")
                await ticket_channel.delete()

        await ticket_channel.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"تم فتح تذكرتك بنجاح في الروم: {ticket_channel.mention}", ephemeral=True)

class TicketSelectView(discord.ui.View):
    def __init__(self, banner_url: str):
        super().__init__(timeout=None)
        self.banner_url = banner_url
        self.add_item(TicketSelect())

# الزر الرئيسي الذي يفتح الرسالة المؤقتة الفخمة
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

# ----------------- الأمر الأول: اللوحة الكبيرة (بالتنسيق الرايق والخطوط الفاصلة) -----------------
@bot.tree.command(name="setup-ticket", description="إنشاء اللوحة الكبيرة والتفصيلية للتذاكر")
@app_commands.describe(banner="اختر صورة البانر الكبيرة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, banner: discord.Attachment):
    
    # التنسيق الاحترافي مع الخطوط والنقاط المرتبة
    ticket_text = (
        "مرحبًا بك في نظام التذاكر الخاص بـ AT Community\n\n"
        "━━━━━━━━━━━━━━━\n"
        "يرجى اختيار القسم المناسب وكتابة تفاصيل مشكلتك مباشرة قبل دخول الإدارة إلى التذكرة حتى يتمكن الفريق من مراجعتها والرد عليك بأسرع وقت، كما نرجو منك احترام قوانين السيرفر وكذلك قواعد وأساسيات الدسكورد.\n\n"
        "📌 **يرجى ذكر الآتي:**\n"
        "• ما هي المشكلة أو الطلب؟\n"
        "• من هم الأشخاص المرتبطون بها؟\n"
        "• أي صور أو مقاطع أو أدلة إن وجدت.\n"
        "• متى بدأت أو متى حدثت؟\n\n"
        "━━━━━━━━━━━━━━━\n"
        "⚠️ **ملاحظة هامة:** في حال عدم توضيح المشكلة مسبقاً قد يتأخر الرد أو يتم إغلاق التذكرة."
    )

    embed = discord.Embed(
        description=ticket_text,
        color=0x000000
    )
    embed.set_image(url=banner.url)

    await interaction.channel.send(
        embed=embed, 
        view=MainTicketButtonView(banner.url, "من هنا يمكنك فتح التذكرة التي تريدها، يرجى اختيار الفئة المناسبة:")
    )
    await interaction.response.send_message("تم إرسال اللوحة الكبيرة بالتنسيق الرايق بنجاح!", ephemeral=True)


# ----------------- الأمر الثاني: اللوحة المصغرة الفخمة -----------------
@bot.tree.command(name="setup-mini-ticket", description="إنشاء اللوحة المصغرة الفخمة")
@app_commands.describe(
    message="اكتب النص المختصر",
    banner="اختر صورة البانر الكبيرة",
    icon="اختر صورة الأيقونة المصغرة"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_mini_ticket(interaction: discord.Interaction, message: str, banner: discord.Attachment, icon: discord.Attachment):
    
    formatted_message = message.replace("\\n", "\n")

    embed = discord.Embed(
        description=formatted_message,
        color=0x000000
    )
    
    embed.set_thumbnail(url=icon.url)
    embed.set_image(url=banner.url)

    await interaction.channel.send(
        embed=embed, 
        view=MainTicketButtonView(banner.url, formatted_message)
    )
    await interaction.response.send_message("تم إرسال اللوحة المصغرة بنجاح!", ephemeral=True)

token = os.getenv("DDD")
bot.run(token)
