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

# القائمة المنسدلة لاختيار القسم (نفس أقسام taqat)
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
            color=0x2b2d31
        )

        class CloseView(discord.ui.View):
            @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒")
            async def close_ticket(self, inter: discord.Interaction, btn: discord.ui.Button):
                await inter.response.send_message("جاري إغلاق التذكرة وحذف الروم...")
                await ticket_channel.delete()

        await ticket_channel.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"تم فتح تذكرتك بنجاح في الروم: {ticket_channel.mention}", ephemeral=True)

class TicketSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# الزر الرئيسي الذي يفتح القائمة المنسدلة عند الضغط عليه
class MainTicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="اختر فئة التذكرة", style=discord.ButtonStyle.secondary, emoji="🎫")
    async def open_selection(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "من هنا يمكنك فتح التذكرة التي تريدها، يرجى اختيار الفئة المناسبة:",
            view=TicketSelectView(),
            ephemeral=True
        )

# أمر إرسال اللوحة مع النص الذي أرسلته بالتنسيق المرتب وصورة البانر من ديسكورد
@bot.tree.command(name="setup-ticket", description="إنشاء لوحة التذاكر الاحترافية")
@app_commands.describe(banner="اختر صورة البانر (التي تظهر في أسفل اللوحة)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, banner: discord.Attachment):
    
    # النص الذي طلبته منسق وجاهز بداخل الإمبد تماماً
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

    embed = discord.Embed(
        description=ticket_text,
        color=0x2b2d31  # اللون الجانبي الأنيق للإمبد
    )
    
    # وضع صورة البانر في الأسفل مثل التصميم المطلوب
    embed.set_image(url=banner.url)

    await interaction.channel.send(embed=embed, view=MainTicketButtonView())
    await interaction.response.send_message("تم إرسال لوحة التذاكر بنجاح وبنفس التنسيق المطلوب!", ephemeral=True)

token = os.getenv("DDD")
bot.run(token)
