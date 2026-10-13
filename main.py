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
        print(f"تم مزامنة {len(synced)} أمر بنجاح")
    except Exception as e:
        print(e)

# القائمة المنسدلة لاختيار القسم وتفتح الروم الخاص
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الدعم الفني", description="للحصول على المساعدة العامة وحل المشاكل", emoji="🛠️"),
            discord.SelectOption(label="الشكاوى والإدارة", description="لتقديم شكوى أو استفسار إداري", emoji="⚠️"),
            discord.SelectOption(label="الاستفسارات", description="للاستفسارات العامة", emoji="💡")
        ]
        super().__init__(placeholder="اضغط هنا لاختيار قسم التذكرة...", min_values=1, max_values=1, options=options)

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

class TicketDropdownView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# أمر الإعداد: يتيح لك كتابة الكلام اللي تبيه ورفع الصورة مباشرة من ديسكورد
@bot.tree.command(name="setup-ticket", description="إنشاء لوحة التذاكر مع تخصيص النص والصورة مباشرة من ديسكورد")
@app_commands.describe(
    message="اكتب النص الذي تريده أن يظهر في اللوحة",
    banner="اختر صورة البانر (التي تظهر أسفل النص)"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, message: str, banner: discord.Attachment):
    
    # تنسيق الإمبد بنفس التصميم النظيف مع النص الذي تكتبه أنت، مع دعم تباعد الأسطر الحقيقي
    formatted_message = message.replace("\\n", "\n")

    embed = discord.Embed(
        description=formatted_message,
        color=0x2b2d31
    )
    
    # إضافة الصورة التي رفعتها من ديسكورد بالأسفل
    embed.set_image(url=banner.url)

    await interaction.channel.send(embed=embed, view=TicketDropdownView())
    await interaction.response.send_message("تم إرسال لوحة التذاكر بنجاح بالتنسيق المخصص!", ephemeral=True)

token = os.getenv("DDD")
bot.run(token)
