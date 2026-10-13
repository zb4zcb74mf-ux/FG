import os
import asyncio
import discord
from discord.ext import commands
import yt_dlp

# إعداد الصلاحيات (Intents) الأساسية للبوت
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True

# تعريف البوت والبادئة (!)
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user}")
    print("البوت يعمل وجاهز بكامل الكفاءة!")

# ==========================================
# 🎵 قسم الأوامر الصوتية والأغاني (بالعربي)
# ==========================================

# أمر دخول الروم الصوتي: !ادخل
@bot.command(name="ادخل")
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"تم الدخول إلى الروم الصوتي: **{channel.name}** 🎵")
    else:
        await ctx.send("يجب أن تكون في روم صوتي أولاً لكي أتمكن من الدخول!")

# أمر تشغيل الأغنية: !شغل [اسم الأغنية]
@bot.command(name="شغل")
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("يجب أن تكون في روم صوتي أولاً لتشغيل الأغاني!")
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    
    voice_client = ctx.voice_client
    
    ytdl_format_options = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
    }
    
    ffmpeg_options = {
        'options': '-vn'
    }
    
    ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
    
    await ctx.send(f"🔍 جاري البحث عن: **{query}**...")
    
    try:
        info = ytdl.extract_info(f"ytsearch:{query}", download=False)
        if 'entries' in info:
            info = info['entries'][0]
        
        url = info['url']
        title = info['title']
        
        source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
        
        if voice_client.is_playing():
            voice_client.stop()
            
        voice_client.play(source, after=lambda e: print(f'انتهى التشغيل: {e}' if e else ''))
        await ctx.send(f"🎶 جاري تشغيل الآن: **{title}**")
        
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء تشغيل الأغنية: {e}")

# أمر خروج البوت: !اطلع
@bot.command(name="اطلع")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("تم الخروج من الروم الصوتي.")
    else:
        await ctx.send("أنا لست في أي روم صوتي أساساً!")

# ==========================================
# 🎫 قسم نظام التذاكر والـ Embeds
# ==========================================

@bot.command(name="embed")
async def send_embed(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="🎫 نظام التذاكر والدعم الفني",
        description="إذا احتجت لأي مساعدة أو لديك استفسار، يرجى فتح تذكرة جديدة بالضغط على الزر أدناه.",
        color=discord.Color.blue()
    )
    embed.add_field(name="تعليمات:", value="• يرجى عدم فتح تذكرة عبثاً.\n• توضيح مشكلتك مباشرة لتسهيل الخدمة.", inline=False)
    embed.set_footer(text="سيرفر الدعم الفني")

    view = TicketView()
    await ctx.send(embed=embed, view=view)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة 🎫", style=discord.ButtonStyle.green, custom_id="open_ticket_btn")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="TICKETS")

        if not category:
            category = await guild.create_category("TICKETS")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel_name = f"ticket-{interaction.user.name}"
        ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        await interaction.response.send_message(f"تم إنشاء تذكرتك بنجاح: {ticket_channel.mention}", ephemeral=True)
        
        close_view = CloseTicketView()
        await ticket_channel.send(f"أهلاً بك {interaction.user.mention}، فريق الإدارة سيساعدك قريباً.\nلإغلاق التذكرة اضغط على الزر أدناه.", view=close_view)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التذكرة 🔒", style=discord.ButtonStyle.red, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("جاري إغلاق التذكرة خلال ثوانٍ...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

# ==========================================
# تشغيل البوت مع التحقق من التوكن
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("خطأ: لم يتم العثور على متغير البيئة DISCORD_TOKEN!")
else:
    bot.run(TOKEN)
