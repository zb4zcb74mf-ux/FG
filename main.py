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

# 1. القائمة المنسدلة للأقسام الرئيسية
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الدعم الفني", description="للحصول على المساعدة العامة وحل المشاكل", emoji="🛠️"),
            discord.SelectOption(label="الشكاوى والإدارة", description="لتقديم شكوى أو استفسار إداري", emoji="⚠️"),
            discord.SelectOption(label="الاستفسارات العامة", description="للاستفسار عن أي شيء يخص السيرفر", emoji="💡"),
            discord.SelectOption(label="الشراكات والإعلانات", description="لطلبات الشراكة أو الإعلان", emoji="🤝")
        ]
        super().__init__(placeholder="القائمة المنسدلة: اختر قسم التذكرة...", min_values=1, max_values=1, options=options)

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
            topic=f"تذكرة قسم: {selected_category} | العضو: {member.mention}"
        )

        embed = discord.Embed(
            title=f"🎫 تذكرة جديدة - {selected_category}",
            description=f"مرحباً بك {member.mention}!\nتم فتح التذكرة في قسم **{selected_category}**. يرجى كتابة تفاصيل طلبك بوضوح وسيقوم الفريق بمتابعتك قريباً.",
            color=0x2b2d31
        )

        class CloseView(discord.ui.View):
            @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒")
            async def close_ticket(self, inter: discord.Interaction, btn: discord.ui.Button):
                await inter.response.send_message("جاري إغلاق التذكرة وحذف الروم...")
                await ticket_channel.delete()

        await ticket_channel.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"تم فتح تذكرتك بنجاح في الروم: {ticket_channel.mention}", ephemeral=True)

# 2. الأزرار السريعة الإضافية تحت القائمة المنسدلة
class TicketButtonsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())  # إضافة القائمة المنسدلة أولاً

    @discord.ui.button(label="فتح تذكرة سريعة", style=discord.ButtonStyle.secondary, emoji="🎫", row=1)
    async def quick_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(
            name=f"quick-{member.name}",
            overwrites=overwrites,
            topic=f"تذكرة سريعة | العضو: {member.mention}"
        )

        embed = discord.Embed(
            title="🎫 تذكرة سريعة جديدة",
            description=f"مرحباً بك {member.mention}!\nيرجى كتابة تفاصيل طلبك مباشرة.",
            color=0x2b2d31
        )

        class CloseView(discord.ui.View):
            @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, emoji="🔒")
            async def close_ticket(self, inter: discord.Interaction, btn: discord.ui.Button):
                await inter.response.send_message("جاري إغلاق التذكرة وحذف الروم...")
                await ticket_channel.delete()

        await ticket_channel.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"تم فتح التذكرة السريعة في: {ticket_channel.mention}", ephemeral=True)

# 3. أمر إرسال لوحة التذاكر الاحترافية مع إمكانية وضع رابط الصورة من ديسكورد مباشرة
@bot.tree.command(name="setup-ticket", description="إرسال لوحة التذاكر الاحترافية مع تخصيص رابط الصورة من ديسكورد")
@app_commands.describe(image_url="ضع هنا رابط الصورة المباشر المأخوذ من ديسكورد (Copy Link)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, image_url: str):
    
    # النص الاحترافي والتنسيق المطلوب بالتفصيل
    embed = discord.Embed(
        description=(
            "مرحباً بك في نظام التذاكر الخاص بـ Community\n\n"
            "يرجى اختيار القسم المناسب وكتابة تفاصيل مشكلتك مباشرة قبل دخول الإدارة إلى التذكرة حتى يتمكن الفريق من mراجعتها والرد عليك بأسرع وقت كذالك نرجو منك احترام قوانين السيرفر كذالك قواعد واساسيات الدسكورد\n\n"
            "يرجى ذكر:\n"
            "• ما هي المشكلة أو الطلب\n"
            "• من هم الأشخاص المرتبطون بها\n"
            "• أي صور أو مقاطع أو أدلة إن وجدت\n"
            "• متى بدأت أو متى حدثت\n\n"
            "في حال عدم توضيح المشكلة مسبقا قد يتأخر الرد أو يتم إغلاق التذكرة"
        ),
        color=0x2b2d31
    )
    
    # وضع رابط الصورة الذي نسخته أنت من ديسكورد مباشرة
    embed.set_image(url=image_url)

    await interaction.channel.send(embed=embed, view=TicketButtonsView())
    await interaction.response.send_message("تم إرسال لوحة التذاكر الاحترافية بنجاح!", ephemeral=True)

token = os.getenv("DDD")
bot.run(token)
