import asyncio
import logging
import os
import subprocess
import sys
from typing import Any

# تثبيت مكتبة pynacl تلقائياً من داخل الكود لضمان عدم ظهور خطأ الصوت أبداً
try:
    import nacl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynacl"])

import discord
import yt_dlp
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord_bot")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# إعدادات الصوت والـ YTDL المتوافقة
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "scsearch1",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -af volume=0.5",
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_lock = asyncio.Lock()

queues: dict[int, list[tuple[dict[str, str], discord.abc.Messageable]]] = {}
now_playing: dict[int, dict[str, str]] = {}
voice_locks: dict[int, asyncio.Lock] = {}


async def extract_info(url: str) -> dict[str, Any] | None:
    async with ytdl_lock:
        return await asyncio.to_thread(ytdl.extract_info, url, download=False)


async def find_track(search: str) -> dict[str, str]:
    data = await extract_info(search)
    if not data:
        raise ValueError("لم أجد نتيجة.")

    if data.get("entries") is not None:
        data = next((entry for entry in data["entries"] if entry), None)
    if not data:
        raise ValueError("ما لقيت الأغنية. جرّب اسمًا ثانيًا.")

    webpage = data.get("webpage_url")
    if not webpage:
        raise ValueError("نتيجة البحث لا تحتوي على رابط صالح.")

    return {
        "title": data.get("title") or "أغنية بدون اسم",
        "webpage": webpage,
    }


async def send_safely(channel: discord.abc.Messageable, message: str) -> None:
    try:
        await channel.send(message)
    except discord.DiscordException:
        logger.exception("Could not send message")


async def play_next(guild: discord.Guild) -> None:
    lock = voice_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = queues.setdefault(guild.id, [])
        if not queue:
            if not voice_client.is_playing() and not voice_client.is_paused():
                now_playing.pop(guild.id, None)
            return

        while queue:
            track, requester_channel = queue.pop(0)
            try:
                stream = await extract_info(track["webpage"])
                stream_url = stream.get("url") if stream else None
                if not stream_url:
                    raise ValueError("لم أتمكن من الحصول على رابط البث.")

                source = discord.FFmpegOpusAudio(stream_url, **FFMPEG_OPTIONS)
                now_playing[guild.id] = track

                def after_play(error: Exception | None) -> None:
                    if error:
                        logger.error("Playback error: %s", error)
                    future = asyncio.run_coroutine_threadsafe(
                        advance_after_track(guild, track), bot.loop
                    )
                    try:
                        future.result()
                    except Exception:
                        logger.exception("Could not advance track")

                voice_client.play(source, after=after_play)
                await send_safely(requester_channel, f"🎵 الآن تعمل: **{track['title']}**")
                return
            except Exception:
                logger.exception("Could not play track: %s", track["title"])
                if now_playing.get(guild.id) is track:
                    now_playing.pop(guild.id, None)
                await send_safely(requester_channel, f"تعذر تشغيل **{track['title']}**؛ سأنتقل للأغنية التالية.")


async def advance_after_track(guild: discord.Guild, finished_track: dict[str, str]) -> None:
    if now_playing.get(guild.id) is finished_track:
        now_playing.pop(guild.id, None)
    await play_next(guild)


@bot.event
async def on_ready() -> None:
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user}")
    logger.info("Bot is ready as %s", bot.user)


# ==================== أوامر الصوت ====================

@bot.command(name="ادخل")
@commands.guild_only()
async def join_voice(ctx: commands.Context) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("ادخل رومًا صوتيًا أولًا ثم اكتب `!ادخل`.")
        return

    channel = ctx.author.voice.channel
    try:
        if ctx.voice_client:
            if ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"✅ دخلت الروم الصوتي: **{channel.name}**")
    except Exception as e:
        await ctx.send(f"تعذر دخول الروم الصوتي. الخطأ: {e}")


@bot.command(name="ش")
@commands.guild_only()
async def play_song(ctx: commands.Context, *, search: str | None = None) -> None:
    if not search:
        await ctx.send("اكتب اسم الأغنية بعد الأمر، مثل: `!ش راب`")
        return
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("ادخل رومًا صوتيًا أولًا.")
        return

    try:
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.voice_client.move_to(ctx.author.voice.channel)
    except Exception:
        await ctx.send("تعذر دخول الروم الصوتي.")
        return

    await ctx.send(f"🔎 أبحث عن: **{search}**...")
    try:
        track = await find_track(search)
    except Exception:
        await ctx.send("ما لقيت الأغنية أو تعذر جلبها. جرّب اسمًا آخر.")
        return

    queues.setdefault(ctx.guild.id, []).append((track, ctx.channel))
    voice_client = ctx.voice_client
    if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(ctx.guild)
    else:
        await ctx.send(f"➕ أُضيفت إلى الطابور: **{track['title']}**")


@bot.command(name="وقف")
@commands.guild_only()
async def pause_song(ctx: commands.Context) -> None:
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ تم إيقاف الأغنية مؤقتًا.")
    else:
        await ctx.send("ما فيه أغنية تعمل حاليًا.")


@bot.command(name="كمل")
@commands.guild_only()
async def resume_song(ctx: commands.Context) -> None:
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ تم استكمال الأغنية.")
    else:
        await ctx.send("ما فيه أغنية متوقفة حاليًا.")


@bot.command(name="سكب")
@commands.guild_only()
async def skip_song(ctx: commands.Context) -> None:
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("⏭️ تم تخطي الأغنية.")
    else:
        await ctx.send("ما فيه أغنية لتخطيها.")


@bot.command(name="اخرج")
@commands.guild_only()
async def leave_voice(ctx: commands.Context) -> None:
    if not ctx.voice_client:
        await ctx.send("أنا لست في روم صوتي.")
        return

    await ctx.voice_client.disconnect()
    queues.pop(ctx.guild.id, None)
    now_playing.pop(ctx.guild.id, None)
    await ctx.send("👋 خرجت من الروم الصوتي.")


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
