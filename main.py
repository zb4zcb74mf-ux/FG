import os
import discord
from discord.ext import commands
from discord import app_commands

# إعداد الصلاحيات الأساسية للبوت
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"تم مزامنة {len(synced)} أمر بنجاح")
    except Exception as e:
        print(e)

# واجهة زر فتح التذكرة
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة", style=discord.ButtonStyle.secondary, emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # الرسالة السرية التي تظهر للشخص عند الضغط على الزر فقط
        await interaction.response.send_message("تم فتح التذكرة بنجاح! سيتم خدمتك قريباً من قبل الفريق.", ephemeral=True)

# أمر إرسال لوحة التذاكر (اكتبه في السيرفر هكذا: /تذكرة)
@bot.tree.command(name="تذكرة", description="إرسال لوحة نظام التذاكر إلى السيرفر")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    # النص المكتوب في لوحة التذاكر (يمكنك تعديله يدوياً بكل حرية)
    embed = discord.Embed(
        description=(
            "مرحباً بك في نظام التذاكر الخاص بالسيرفر\n\n"
            "يرجى اختيار القسم المناسب وكتابة تفاصيل مشكلتك مباشرة قبل دخول الإدارة إلى التذكرة حتى يتمكن الفريق من مراجعتها والرد عليك بأسرع وقت. نرجو منك احترام قوانين السيرفر وأساسيات الدسكورد.\n\n"
            "يرجى ذكر الآتي:\n"
            "• ما هي المشكلة أو الطلب بالتحديد\n"
            "• من هم الأشخاص المرتبطون بالمشكلة\n"
            "• أي صور أو أدلة إن وجدت\n"
            "• متى بدأت المشكلة\n\n"
            "في حال عدم توضيح المشكلة مسبقاً قد يتأخر الرد أو يتم إغلاق التذكرة."
        ),
        color=0x2b2d31  # لون الإمبد (رمادي داكن)
    )
    
    # رابط الصورة (البانر) أسفل النص - استبدل الرابط أدناه برابط صورتك الخاصة
    embed.set_image(url="https://i.imgur.com/your_image_link.png")

    # إرسال اللوحة مع الزر
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("تم إرسال لوحة التذاكر بنجاح!", ephemeral=True)

# تشغيل البوت باستخدام متغير البيئة DDD
token = os.getenv("DDD")
bot.run(token)
