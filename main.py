import os
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user}")
    print("البوت يعمل بنظام التذاكر وجاهز تماماً!")

@bot.command(name="مرحبا")
async def hello(ctx: commands.Context):
    await ctx.send(f"أهلاً بك يا {ctx.author.mention}! البوت شغال وزي الحلاوة بدون تعقيد.")

# ==================== نظام التذاكر المتكامل (أزرار ولوحة) ====================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.green, custom_id="open_ticket_btn")
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

    @discord.ui.button(label="إغلاق التذكرة 🔒", style=discord.ButtonStyle.red, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 جاري إغلاق التذكرة وحذف الروم...")
        import asyncio
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

@bot.command(name="تذاكر")
@commands.has_permissions(administrator=True)
async def setup_ticket_panel(ctx: commands.Context):
    embed = discord.Embed(
        title="🎫 نظام تذاكر السيرفر",
        description="اضغط على الزر بالأسفل لفتح تذكرة جديدة وسيقوم البوت بإنشاء روم خاص بك.",
        color=discord.Color.dark_embed()
    )
    view = TicketView()
    await ctx.send(embed=embed, view=view)
    try:
        await ctx.message.delete()
    except Exception:
        pass

if not TOKEN:
    raise RuntimeError("الرجاء إضافة DISCORD_TOKEN في متغيرات البيئة Variables.")

bot.run(TOKEN)
