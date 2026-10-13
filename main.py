import os
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # مزامنة الأوامر مع ديسكورد عشان تظهر مباشرة لما تكتب /
        await self.tree.sync()
        print("تم مزامنة أوامر الـ Slash Commands بنجاح!")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user}")

# ==================== كلاس أزرار التذاكر ====================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.green, custom_id="open_ticket_main")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        try:
            ticket_channel = await guild.create_text_channel(
                f"tkt-{member.name}",
                overwrites=overwrites
            )
            
            close_view = TicketCloseView()
            embed = discord.Embed(
                title="🎫 تذكرة جديدة",
                description=f"مرحباً بك {member.mention}! أطلعنا على مشكلتك وسيقوم الفريق بمساعدتك قريباً.",
                color=discord.Color.blue()
            )
            await ticket_channel.send(content=member.mention, embed=embed, view=close_view)
            await interaction.response.send_message(f"✅ تم فتح تذكرتك بنجاح: {ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء فتح التذكرة: {e}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التذكرة 🔒", style=discord.ButtonStyle.red, custom_id="close_ticket_main")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 جاري إغلاق التذكرة وحذف الروم...")
        import asyncio
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

# ==================== أوامر الـ Slash Commands ====================

@bot.tree.command(name="setup-ticket", description="إنشاء اللوحة الكبيرة للتذاكر")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 نظام تذاكر السيرفر",
        description="اضغط على الزر بالأسفل لفتح تذكرة جديدة وسيقوم البوت بإنشاء روم خاص بك.",
        color=discord.Color.dark_embed()
    )
    view = TicketView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ تم إنشاء لوحة التذاكر الكبيرة بنجاح!", ephemeral=True)

@bot.tree.command(name="setup-mini-ticket", description="إنشاء اللوحة المصغرة الفخمة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_mini_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✨ التذكرة السريعة",
        description="تحتاج مساعدة سريعة؟ اضغط الزر أدناه لفتح تذكرة فورية.",
        color=discord.Color.blurple()
    )
    view = TicketView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ تم إنشاء اللوحة المصغرة بنجاح!", ephemeral=True)

if not TOKEN:
    raise RuntimeError("الرجاء إضافة DISCORD_TOKEN في متغيرات البيئة Variables.")

bot.run(TOKEN)
