import asyncio
import logging
import os
import shutil
from typing import Any

import discord
import yt_dlp
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"


def get_command_prefix(_bot: commands.Bot, message: discord.Message) -> str:
    content = message.content.strip()
    first_word = content.split(maxsplit=1)
    if first_word and first_word[0] == "ش":
        return ""
    if content in {"وقف", "ك", "س"}:
        return ""
    return PREFIX


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord_music_bot")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=get_command_prefix, intents=intents)

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
voice_connection_locks: dict[int, asyncio.Lock] = {}
voice_targets: dict[int, int] = {}
voice_reconnect_tasks: dict[int, asyncio.Task[None]] = {}


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


async def send_safely(
    channel: discord.abc.Messageable, message: str
) -> None:
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


def user_shares_bot_voice_channel(ctx: commands.Context) -> bool:
    return bool(
        ctx.guild
        and ctx.voice_client
        and ctx.author.voice
        and ctx.author.voice.channel == ctx.voice_client.channel
    )


@bot.event
async def on_ready() -> None:
    logger.info("تم تسجيل الدخول باسم %s", bot.user)
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user}")
    print("البوت يعمل وجاهز بكامل الكفاءة!")


async def reconnect_to_voice(guild_id: int, channel_id: int) -> None:
    for attempt in range(1, 4):
        await asyncio.sleep(2**attempt)
        if voice_targets.get(guild_id) != channel_id:
            return

        guild = bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            voice_targets.pop(guild_id, None)
            return

        lock = voice_connection_locks.setdefault(guild_id, asyncio.Lock())
        try:
            async with lock:
                if voice_targets.get(guild_id) != channel_id:
                    return

                voice_client = guild.voice_client
                if voice_client and voice_client.is_connected():
                    if voice_client.channel.id == channel_id:
                        return
                    await voice_client.move_to(channel, timeout=25.0)
                else:
                    if voice_client:
                        await voice_client.disconnect(force=True)
                    await channel.connect(timeout=25.0, reconnect=True)

            if queues.get(guild_id):
                await play_next(guild)
            return
        except Exception:
            logger.exception("Voice reconnection attempt %s failed", attempt)


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if not bot.user or member.id != bot.user.id or before.channel == after.channel:
        return

    guild_id = member.guild.id
    target_id = voice_targets.get(guild_id)
    if target_id is None or (after.channel and after.channel.id == target_id):
        return

    current_task = voice_reconnect_tasks.get(guild_id)
    if current_task and not current_task.done():
        return

    task = asyncio.create_task(reconnect_to_voice(guild_id, target_id))
    voice_reconnect_tasks[guild_id] = task

    def clear_task(done: asyncio.Task[None]) -> None:
        if voice_reconnect_tasks.get(guild_id) is done:
            voice_reconnect_tasks.pop(guild_id, None)

    task.add_done_callback(clear_task)


@bot.command(name="ادخل")
@commands.guild_only()
async def join_voice(ctx: commands.Context) -> None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("ادخل رومًا صوتيًا أولًا ثم اكتب `!ادخل`.")
        return

    channel = ctx.author.voice.channel
    bot_member = ctx.guild.me
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.connect:
        await ctx.send(
            "ما أقدر أدخل هذا الروم. اطلب من مسؤول السيرفر السماح للبوت "
            "بصلاحية **View Channel** و **Connect** في إعدادات الروم."
        )
        return

    await ctx.send(f"⏳ أحاول دخول الروم الصوتي **{channel.name}**...")
    lock = voice_connection_locks.setdefault(ctx.guild.id, asyncio.Lock())
    try:
        async with lock:
            voice_client = ctx.voice_client
            if voice_client and voice_client.is_connected():
                if voice_client.channel != channel:
                    voice_targets[ctx.guild.id] = channel.id
                    await voice_client.move_to(channel, timeout=25.0)
            else:
                if voice_client:
                    await voice_client.disconnect(force=True)
                await channel.connect(timeout=25.0, reconnect=True)
            voice_targets[ctx.guild.id] = channel.id
    except Exception:
        logger.exception("Unexpected error while joining the voice channel")
        await ctx.send("تعذر دخول الروم بسبب خطأ غير متوقع.")
        return

    await ctx.send(f"✅ دخلت الروم الصوتي: **{channel.name}**")


@bot.command(name="ش")
@commands.guild_only()
async def play_song(ctx: commands.Context, *, search: str | None = None) -> None:
    if not search:
        await ctx.send("اكتب اسم الأغنية بعد الأمر، مثل: `ش اسم الأغنية`")
        return
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("ادخل رومًا صوتيًا أولًا.")
        return

    try:
        if not ctx.voice_client:
            voice_client = await ctx.author.voice.channel.connect()
        else:
            voice_client = ctx.voice_client
            if voice_client.channel != ctx.author.voice.channel:
                voice_targets[ctx.guild.id] = ctx.author.voice.channel.id
                await voice_client.move_to(ctx.author.voice.channel)
        voice_targets[ctx.guild.id] = ctx.author.voice.channel.id
    except Exception:
        logger.exception("Could not connect to the requested voice channel")
        await ctx.send("تعذر دخول الروم الصوتي.")
        return

    await ctx.send(f"🔎 أبحث عن: **{search}**...")
    try:
        track = await find_track(search)
    except Exception:
        logger.exception("Track lookup failed for %r", search)
        await ctx.send("ما لقيت الأغنية أو تعذر جلبها. جرّب اسمًا آخر.")
        return

    queues.setdefault(ctx.guild.id, []).append((track, ctx.channel))
    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(ctx.guild)
    else:
        await ctx.send(f"➕ أُضيفت إلى الطابور: **{track['title']}**")


@bot.command(name="وقف")
@commands.guild_only()
async def pause_song(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if not user_shares_bot_voice_channel(ctx):
        await ctx.send("يجب أن تكون في نفس الروم الصوتي مع البوت.")
    elif voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ تم إيقاف الأغنية مؤقتًا.")
    else:
        await ctx.send("ما فيه أغنية تعمل حاليًا.")


@bot.command(name="ك", aliases=["كمل"])
@commands.guild_only()
async def resume_song(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if not user_shares_bot_voice_channel(ctx):
        await ctx.send("يجب أن تكون في نفس الروم الصوتي مع البوت.")
    elif voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ تم استكمال الأغنية.")
    else:
        await ctx.send("ما فيه أغنية متوقفة مؤقتًا.")


@bot.command(name="س", aliases=["سكب"])
@commands.guild_only()
async def skip_song(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if not user_shares_bot_voice_channel(ctx):
        await ctx.send("يجب أن تكون في نفس الروم الصوتي مع البوت.")
    elif voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await ctx.send("⏭️ تم تخطي الأغنية.")
    else:
        await ctx.send("ما فيه أغنية لتخطيها.")


@bot.command(name="طابور")
@commands.guild_only()
async def show_queue(ctx: commands.Context) -> None:
    queue = queues.get(ctx.guild.id, [])
    current = now_playing.get(ctx.guild.id)
    heading = f"🎵 تعمل الآن: **{current['title']}**\n" if current else ""

    if not queue:
        await ctx.send(heading or "قائمة الانتظار فارغة.")
        return

    lines = [
        f"{index}. {track['title']}"
        for index, (track, _channel) in enumerate(queue[:15], 1)
    ]
    await ctx.send(heading + "**قائمة الانتظار:**\n" + "\n".join(lines))


@bot.command(name="اخرج")
@commands.guild_only()
async def leave_voice(ctx: commands.Context) -> None:
    voice_targets.pop(ctx.guild.id, None)
    reconnect_task = voice_reconnect_tasks.pop(ctx.guild.id, None)
    if reconnect_task and not reconnect_task.done():
        reconnect_task.cancel()

    if not ctx.voice_client:
        await ctx.send("أنا لست في روم صوتي.")
        return

    await ctx.voice_client.disconnect()
    queues.pop(ctx.guild.id, None)
    now_playing.pop(ctx.guild.id, None)
    await ctx.send("👋 خرجت من الروم الصوتي.")


@bot.event
async def on_command_error(
    ctx: commands.Context, error: commands.CommandError
) -> None:
    if isinstance(error, (commands.NoPrivateMessage, commands.CommandNotFound)):
        return
    logger.exception("Command failed", exc_info=error)


if not TOKEN:
    raise RuntimeError("أضف توكن البوت في Variables باسم DISCORD_TOKEN.")

bot.run(TOKEN)
