import os
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"

# آي دي روم "ديوانيه النقز"
TARGET_VOICE_CHANNEL_ID = 1558075847359860768

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user}")
    print("البوت يعمل بكامل الأنظمة وجاهز!")

@bot.command(name="ادخل")
@commands.guild_only()
async def join_voice(ctx: commands.Context):
    channel = ctx.guild.get_channel(TARGET_VOICE_CHANNEL_ID)
    
    if not channel:
        if ctx.author.voice and ctx.author.voice.channel:
            channel = ctx.author.voice.channel
        else:
            await ctx.send("❌ لم أجد الروم الصوتي المحدد.")
            return

    try:
        if ctx.voice_client:
            if ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send("✅ دخلت روم 'ديوانيه النقز' بنجاح!")
    except Exception as e:
        await ctx.send(f"تعذر دخول الروم الصوتي. الخطأ: {e}")

@bot.command(name="اخرج")
@commands.guild_only()
async def leave_voice(ctx: commands.Context):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 خرجت من الروم الصوتي.")
    else:
        await ctx.send("أنا لست في روم صوتي أساساً.")

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
