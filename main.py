import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# القائمة المنسدلة لاختيار القسم داخل التذكرة
class TicketSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الدعم الفني", description="لحل المشاكل التقنية والبقز", emoji="🛠️"),
            discord.SelectOption(label="إدارة السيرفر", description="للشكاوى والاستفسارات الإدارية", emoji="🛡️"),
            discord.SelectOption(label="الشراكات والتعاون", description="طلبات الرعاية والتبادل", emoji="🤝")
        ]
        super().__init__(placeholder="اختر قسم التذكرة المناسب...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"تم اختيار قسم: **{self.values[0]}**. جاري إنشاء التذكرة...", ephemeral=True)

class TicketDropdownView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# أزرار لوحة التحكم الرئيسية (فتح التذكرة)
class TicketMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.secondary, custom_id="open_ticket_main")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "الرجاء اختيار القسم المطلوب لتوجيه تذكرتك بالشكل الصحيح:",
            view=TicketDropdownView(),
            ephemeral=True
        )

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.command()
async def ticket(ctx):
    description = (
        "مرحباً بك في نظام التذاكر الخاص بـ Community\n\n"
        "يرجى اختيار القسم المناسب وكتابة تفاصيل مشكلتك مباشرة قبل دخول الإدارة إلى التذكرة حتى يتمكن الفريق من مراجعتها والرد عليك بأسرع وقت.\n\n"
        "يرجى ذكر:\n"
        "• ما هي المشكلة أو الطلب\n"
        "• من هم الأشخاص المرتبطون بها\n"
        "• أي صور أو مقاطع أو أدلة إن وجدت\n"
        "• متى بدأت أو متى حدثت"
    )
    
    embed = discord.Embed(
        description=description,
        color=0x2b2d31
    )
    
    # استبدل الرابط أدناه برابط الصورة المباشر اللي تبيه يظهر تحت النص
    embed.set_image(url="https://example.com/your-image.png")

    await ctx.send(embed=embed, view=TicketMainView())

# تشغيل البوت باستخدام متغير البيئة DDD
bot.run(os.getenv("DDD"))
