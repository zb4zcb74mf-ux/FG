import asyncio
import logging
import os
from typing import Any

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord_music_bot")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# إعدادات متقدمة جداً لتخطي حظر السيرفرات السحابية
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "opus",
        "preferredquality": "192",
    }],
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -vn",
    "options": "-af volume=0.5",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_lock = asyncio.Lock()

queues: dict[int, list[tuple[dict[str, str], discord.abc.Messageable]]] = {}
now_playing: dict[int, dict[str, str]] = {}
voice_locks: dict[int, asyncio.Lock] = {}
voice_connection_locks: dict[int, asyncio.Lock] = {}
voice_targets: dict[int, int] = {}
voice_reconnect_tasks: dict[int, asyncio.Task[None]] = {}


async def extract_info(url: str) -> dict[str, Any] | None:
    async with ytdl_lock:
        return await asyncio.to_thread(ytdl.extract_info, url, download=False)


async def find_track(search: str) -> dict[str, str]:
    query = search if search.startswith("http") else f"ytsearch:{search}"
    data = await extract_info(query)
    if not data:
        raise ValueError("لم أجد نتيجة.")

    if data.get("entries"):
        entries = [e for e in data["entries"] if e]
        if not entries:
            raise ValueError("ما لقيت الأغنية.")
        data = entries[0]

    webpage = data.get("webpage_url") or data.get("url")
    stream_url = data.get("url")

    if not webpage:
        raise ValueError("نتيجة البحث لا تحتوي على رابط صالح.")

    return {
        "title": data.get("title") or "أغنية بدون اسم",
        "webpage": webpage,
        "url": stream_url,
    }


async def send_safely(channel: discord.abc.Messageable, message: str) -> None:
    try:
        await channel.send(message)
    except discord.DiscordException:
        logger.exception("Could not send a message to the request channel")


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
                stream_url = track.get("url")
                if not stream_url:
                    stream_data = await extract_info(track["webpage"])
                    if stream_data and stream_data.get("entries"):
                        stream_data = stream_data["entries"][0]
                    stream_url = stream_data.get("url") if stream_data else None

                if not stream_url:
                    raise ValueError("لم أتمكن من الحصول على رابط البث.")

                source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(source, volume=0.6)
                
                now_playing[guild.id] = track

                def after_play(error: Exception | None) -> None:
                    if error:
                        logger.error("Playback error: %s", error)

                    future = asyncio.run_coroutine_threadsafe(
                        advance_after_track(guild, track), bot.loop
                    )

                    def report_failure(done: Any) -> None:
                        try:
                            done.result()
                        except Exception:
                            logger.exception("Could not start the next track")

                    future.add_done_callback(report_failure)

                voice_client.play(source, after=after_play)
                await send_safely(
                    requester_channel,
                    f"🎵 الآن تعمل: **{track['title']}**",
                )
                return
            except Exception:
                logger.exception("Could not play track: %s", track["title"])
                if now_playing.get(guild.id) is track:
                    now_playing.pop(guild.id, None)
                await send_safely(
                    requester_channel,
                    f"تعذر تشغيل **{track['title']}**؛ سأنتقل للأغنية التالية.",
                )


async def advance_after_track(
    guild: discord.Guild, finished_track: dict[str, str]
) -> None:
    if now_playing.get(guild.id) is finished_track:
        now_playing.pop(guild.id, None)
    await play_next(guild)


def user_shares_bot_voice_channel(interaction: discord.Interaction) -> bool:
    return bool(
        interaction.guild
        and interaction.guild.voice_client
        and interaction.user.voice
        and interaction.user.voice.channel == interaction.guild.voice_client.channel
    )


@bot.event
async def on_ready() -> None:
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %s slash commands.", len(synced))
    except Exception:
        logger.exception("Failed to sync slash commands")
    logger.info("تم تسجيل الدخول باسم %s", bot.user)


@bot.tree.command(name="ادخل", description="دخول الروم الصوتي")
@app_commands.guild_only()
async def join_voice(interaction: discord.Interaction) -> None:
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("ادخل رومًا صوتيًا أولًا.", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    bot_member = interaction.guild.me
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.connect:
        await interaction.response.send_message(
            "ما أقدر أدخل هذا الروم. تأكد من صلاحيات View Channel و Connect.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    lock = voice_connection_locks.setdefault(interaction.guild.id, asyncio.Lock())
    try:
        async with lock:
            voice_client = interaction.guild.voice_client
            if voice_client and voice_client.is_connected():
                if voice_client.channel != channel:
                    voice_targets[interaction.guild.id] = channel.id
                    await voice_client.move_to(channel, timeout=25.0)
            else:
                if voice_client:
                    await voice_client.disconnect(force=True)
                await channel.connect(timeout=25.0, reconnect=True)
            voice_targets[interaction.guild.id] = channel.id
    except Exception:
        logger.exception("Error while joining voice channel")
        await interaction.followup.send("تعذر دخول الروم الصوتي.", ephemeral=True)
        return

    await interaction.followup.send(f"✅ دخلت الروم الصوتي: **{channel.name}**", ephemeral=True)


@bot.tree.command(name="شغل", description="تشغيل أغنية بالاسم أو الرابط")
@app_commands.describe(search="اسم الأغنية أو الرابط")
@app_commands.guild_only()
async def play_song(interaction: discord.Interaction, search: str) -> None:
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("ادخل رومًا صوتيًا أولًا.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        voice_client = interaction.guild.voice_client
        target_channel = interaction.user.voice.channel
        if not voice_client:
            voice_client = await target_channel.connect()
        else:
            if voice_client.channel != target_channel:
                voice_targets[interaction.guild.id] = target_channel.id
                await voice_client.move_to(target_channel)
        voice_targets[interaction.guild.id] = target_channel.id
    except Exception:
        logger.exception("Could not connect to voice channel")
        await interaction.followup.send("تعذر دخول الروم الصوتي.", ephemeral=True)
        return

    try:
        track = await find_track(search)
    except Exception as exc:
        logger.warning("Track lookup failed for %r: %s", search, exc)
        await interaction.followup.send("ما لقيت الأغنية أو تعذر جلبها.", ephemeral=True)
        return

    queues.setdefault(interaction.guild.id, []).append((track, interaction.channel))
    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(interaction.guild)
        await interaction.followup.send(f"▶️ جاري تشغيل: **{track['title']}**")
    else:
        await interaction.followup.send(f"➕ أُضيفت إلى الطابور: **{track['title']}**")


@bot.tree.command(name="وقف", description="إيقاف الأغنية مؤقتًا")
@app_commands.guild_only()
async def pause_song(interaction: discord.Interaction) -> None:
    voice_client = interaction.guild.voice_client
    if not user_shares_bot_voice_channel(interaction):
        await interaction.response.send_message("يجب أن تكون في نفس الروم الصوتي مع البوت.", ephemeral=True)
    elif voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ تم إيقاف الأغنية مؤقتًا.")
    else:
        await interaction.response.send_message("ما فيه أغنية تعمل حاليًا.", ephemeral=True)


@bot.tree.command(name="كمل", description="استكمال الأغنية المتوقفة")
@app_commands.guild_only()
async def resume_song(interaction: discord.Interaction) -> None:
    voice_client = interaction.guild.voice_client
    if not user_shares_bot_voice_channel(interaction):
        await interaction.response.send_message("يجب أن تكون في نفس الروم الصوتي مع البوت.", ephemeral=True)
    elif voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ تم استكمال الأغنية.")
    else:
        await interaction.response.send_message("ما فيه أغنية متوقفة مؤقتًا.", ephemeral=True)


@bot.tree.command(name="س", description="تخطي الأغنية الحالية")
@app_commands.guild_only()
async def skip_song(interaction: discord.Interaction) -> None:
    voice_client = interaction.guild.voice_client
    if not user_shares_bot_voice_channel(interaction):
        await interaction.response.send_message("يجب أن تكون في نفس الروم الصوتي مع البوت.", ephemeral=True)
    elif voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await interaction.response.send_message("⏭️ تم تخطي الأغنية.")
    else:
        await interaction.response.send_message("ما فيه أغنية لتخطيها.", ephemeral=True)


@bot.tree.command(name="قائمة", description="عرض قائمة الانتظار")
@app_commands.guild_only()
async def show_queue(interaction: discord.Interaction) -> None:
    queue = queues.get(interaction.guild.id, [])
    current = now_playing.get(interaction.guild.id)
    heading = f"🎵 تعمل الآن: **{current['title']}**\n" if current else ""

    if not queue:
        await interaction.response.send_message(heading or "قائمة الانتظار فارغة.", ephemeral=False)
        return

    lines = [
        f"{index}. {track['title']}"
        for index, (track, _channel) in enumerate(queue[:15], 1)
    ]
    await interaction.response.send_message(heading + "**قائمة الانتظار:**\n" + "\n".join(lines), ephemeral=False)


@bot.tree.command(name="اخرج", description="إخراج البوت من الروم الصوتي")
@app_commands.guild_only()
async def leave_voice(interaction: discord.Interaction) -> None:
    voice_targets.pop(interaction.guild.id, None)
    reconnect_task = voice_reconnect_tasks.pop(interaction.guild.id, None)
    if reconnect_task and not reconnect_task.done():
        reconnect_task.cancel()

    if not interaction.guild.voice_client:
        await interaction.response.send_message("أنا لست في روم صوتي.", ephemeral=True)
        return

    await interaction.guild.voice_client.disconnect()
    queues.pop(interaction.guild.id, None)
    now_playing.pop(interaction.guild.id, None)
    await interaction.response.send_message("👋 خرجت من الروم الصوتي.")


if not TOKEN:
    raise RuntimeError("أضف توكن البوت في متغيرات البيئة باسم DISCORD_TOKEN.")

bot.run(TOKEN)
