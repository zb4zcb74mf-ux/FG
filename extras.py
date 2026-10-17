"""
Taqat extras: أذكار وأدعية تلقائية + إشعارات تيك توك + نقل رسائلك عبر البوت كما هي.
التحميل: داخل setup_hook في الملف الأساسي أضف:
    await bot.load_extension("extras")
المتطلبات: pip install yt-dlp
"""
import asyncio
import datetime
import json
import os
import random
import time
from typing import Literal, Optional

import discord
from discord.ext import commands, tasks

FILE = "extras.json"
TZ = datetime.timezone(datetime.timedelta(hours=3))   # توقيت السعودية (بدون تغيير صيفي)
GOLD = 0xD4AF37
C_OK, C_ERR = 0x3DDC84, 0xFF5555

# ---------------------------------------------------------------- المحتوى
MORNING = [
    "أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ",
    "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ",
    "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ (3 مرات)",
    "رَضِيتُ بِاللَّهِ رَبًّا، وَبِالْإِسْلَامِ دِينًا، وَبِمُحَمَّدٍ ﷺ نَبِيًّا (3 مرات)",
    "حَسْبِيَ اللَّهُ لَا إِلَهَ إِلَّا هُوَ عَلَيْهِ تَوَكَّلْتُ وَهُوَ رَبُّ الْعَرْشِ الْعَظِيمِ (7 مرات)",
    "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ (100 مرة)",
    "📖 لا تنسى: آية الكرسي، والإخلاص والمعوذتين (3 مرات)",
]
EVENING = [
    "أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ، وَالْحَمْدُ لِلَّهِ، لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ",
    "اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ الْمَصِيرُ",
    "أَعُوذُ بِكَلِمَاتِ اللَّهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ (3 مرات)",
    "بِسْمِ اللَّهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ (3 مرات)",
    "حَسْبِيَ اللَّهُ لَا إِلَهَ إِلَّا هُوَ عَلَيْهِ تَوَكَّلْتُ وَهُوَ رَبُّ الْعَرْشِ الْعَظِيمِ (7 مرات)",
    "أَسْتَغْفِرُ اللَّهَ وَأَتُوبُ إِلَيْهِ (100 مرة)",
    "📖 لا تنسى: آية الكرسي، والإخلاص والمعوذتين (3 مرات)",
]
DUAS = [
    "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ",
    "رَبِّ اشْرَحْ لِي صَدْرِي وَيَسِّرْ لِي أَمْرِي",
    "اللَّهُمَّ إِنَّكَ عَفُوٌّ تُحِبُّ الْعَفْوَ فَاعْفُ عَنِّي",
    "يَا حَيُّ يَا قَيُّومُ بِرَحْمَتِكَ أَسْتَغِيثُ",
    "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ",
    "لَا إِلَهَ إِلَّا أَنْتَ سُبْحَانَكَ إِنِّي كُنْتُ مِنَ الظَّالِمِينَ",
    "اللَّهُمَّ أَعِنِّي عَلَى ذِكْرِكَ وَشُكْرِكَ وَحُسْنِ عِبَادَتِكَ",
    "اللَّهُمَّ صَلِّ وَسَلِّمْ عَلَى نَبِيِّنَا مُحَمَّدٍ",
    "لَا حَوْلَ وَلَا قُوَّةَ إِلَّا بِاللَّهِ",
    "سُبْحَانَ اللَّهِ، وَالْحَمْدُ لِلَّهِ، وَلَا إِلَهَ إِلَّا اللَّهُ، وَاللَّهُ أَكْبَرُ",
    "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ، سُبْحَانَ اللَّهِ الْعَظِيمِ",
    "أَسْتَغْفِرُ اللَّهَ الْعَظِيمَ وَأَتُوبُ إِلَيْهِ",
    "رَبِّ زِدْنِي عِلْمًا",
    "رَبَّنَا لَا تُزِغْ قُلُوبَنَا بَعْدَ إِذْ هَدَيْتَنَا وَهَبْ لَنَا مِنْ لَدُنْكَ رَحْمَةً إِنَّكَ أَنْتَ الْوَهَّابُ",
    "اللَّهُمَّ يَا مُقَلِّبَ الْقُلُوبِ ثَبِّتْ قَلْبِي عَلَى دِينِكَ",
]
FRIDAY = "🕌 اليوم الجمعة: أكثر من الصلاة على النبي ﷺ، واقرأ سورة الكهف، وتحرَّ ساعة الإجابة."

# ---------------------------------------------------------------- التخزين
def _load() -> dict:
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)

DB = _load()

def save():
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, ensure_ascii=False, indent=2)

def cfg(gid: int) -> dict:
    g = DB.setdefault(str(gid), {})
    a = g.setdefault("azkar", {})
    a.setdefault("channel", None)
    a.setdefault("hours", 0)
    a.setdefault("last_dua", 0)
    a.setdefault("morning", {"on": True, "time": "05:30"})
    a.setdefault("evening", {"on": True, "time": "17:30"})
    a.setdefault("last", {})
    a.setdefault("custom", [])
    t = g.setdefault("tiktok", {})
    t.setdefault("user", None)
    t.setdefault("channel", None)
    t.setdefault("role", None)
    t.setdefault("seen", [])
    r = g.setdefault("relay", {})
    r.setdefault("source", None)
    r.setdefault("target", None)
    return g

def E(title, desc=None, color=C_OK):
    return discord.Embed(title=title, description=desc, color=color,
                         timestamp=discord.utils.utcnow())

# ---------------------------------------------------------------- تيك توك
def fetch_tiktok(user: str):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "playlistend": 6, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"https://www.tiktok.com/@{user}", download=False)
    out = []
    for e in (info.get("entries") or []):
        vid = str(e.get("id") or "")
        if not vid:
            continue
        url = e.get("url") or ""
        if not url.startswith("http"):
            url = f"https://www.tiktok.com/@{user}/video/{vid}"
        out.append((vid, url))
    return out

def clean_user(s: str) -> str:
    s = s.strip().rstrip("/")
    if "tiktok.com/" in s:
        s = s.split("tiktok.com/")[-1].split("?")[0].split("/")[0]
    return s.lstrip("@")

# ---------------------------------------------------------------- الكوج
class Extras(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.azkar_loop.start()
        self.tiktok_loop.start()

    async def cog_unload(self):
        self.azkar_loop.cancel()
        self.tiktok_loop.cancel()

    # ------------------------------------------------ الأذكار
    def session_embed(self, key: str, now: datetime.datetime) -> discord.Embed:
        morning = key == "morning"
        items = MORNING if morning else EVENING
        e = E("🌅 أذكار الصباح" if morning else "🌙 أذكار المساء",
              "\n\n".join(f"• {x}" for x in items), GOLD)
        if morning and now.weekday() == 4:
            e.add_field(name="\u200b", value=FRIDAY, inline=False)
        e.set_footer(text="تقبّل الله منا ومنكم")
        return e

    def dua_embed(self, gid: int) -> discord.Embed:
        pool = DUAS + cfg(gid)["azkar"]["custom"]
        return E("🤲 دعاء", f"**{random.choice(pool)}**", GOLD)

    @tasks.loop(minutes=1)
    async def azkar_loop(self):
        now = datetime.datetime.now(TZ)
        today, hm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
        for guild in self.bot.guilds:
            a = cfg(guild.id)["azkar"]
            ch = guild.get_channel(a["channel"]) if a["channel"] else None
            if not ch:
                continue
            try:
                for key in ("morning", "evening"):
                    s = a[key]
                    if s["on"] and hm == s["time"] and a["last"].get(key) != today:
                        a["last"][key] = today
                        save()
                        await ch.send(embed=self.session_embed(key, now))
                if a["hours"] and time.time() - a["last_dua"] >= a["hours"] * 3600:
                    a["last_dua"] = time.time()
                    save()
                    await ch.send(embed=self.dua_embed(guild.id))
            except discord.HTTPException:
                pass

    @azkar_loop.before_loop
    async def _b1(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="azkarchannel", description="تحديد روم الأذكار التلقائية")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def azkarchannel(self, ctx, channel: discord.TextChannel):
        cfg(ctx.guild.id)["azkar"]["channel"] = channel.id
        save()
        await ctx.send(embed=E("✅ روم الأذكار", channel.mention))

    @commands.hybrid_command(name="azkarinterval", description="دعاء عشوائي كل X ساعة (0 للإيقاف)")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def azkarinterval(self, ctx, hours: int):
        if not 0 <= hours <= 72:
            return await ctx.send(embed=E("❌ رقم غير صحيح", "من 0 إلى 72 ساعة.", C_ERR), ephemeral=True)
        a = cfg(ctx.guild.id)["azkar"]
        a["hours"], a["last_dua"] = hours, time.time()
        save()
        await ctx.send(embed=E("✅ تم", f"دعاء كل **{hours}** ساعة" if hours else "الأدعية الدورية متوقفة"))

    @commands.hybrid_command(name="azkarsession", description="أذكار الصباح/المساء: تشغيل/إيقاف ووقتها (مثال 05:30)")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def azkarsession(self, ctx, which: Literal["morning", "evening"], enabled: bool, at: str = None):
        s = cfg(ctx.guild.id)["azkar"][which]
        if at:
            try:
                datetime.datetime.strptime(at, "%H:%M")
            except ValueError:
                return await ctx.send(embed=E("❌ وقت غير صحيح", "اكتبه هكذا: `05:30` (توقيت السعودية).", C_ERR), ephemeral=True)
            s["time"] = at
        s["on"] = enabled
        save()
        await ctx.send(embed=E("✅ تم", f"{'الصباح' if which == 'morning' else 'المساء'}: "
                                         f"{'🟢 مفعّل' if enabled else '🔴 متوقف'} — الساعة `{s['time']}`"))

    @commands.hybrid_command(name="azkaradd", description="إضافة دعاء/ذكر من عندك للأدعية العشوائية")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def azkaradd(self, ctx, *, text: str):
        c = cfg(ctx.guild.id)["azkar"]["custom"]
        if len(c) >= 100:
            return await ctx.send(embed=E("❌ وصلت الحد", "الحد الأقصى 100.", C_ERR), ephemeral=True)
        c.append(text.replace("\\n", "\n")[:1000])
        save()
        await ctx.send(embed=E("✅ تمت الإضافة", text[:500]))

    @commands.hybrid_command(name="azkarnow", description="إرسال ذكر الآن للتجربة")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def azkarnow(self, ctx, kind: Literal["morning", "evening", "dua"] = "dua"):
        e = self.dua_embed(ctx.guild.id) if kind == "dua" else self.session_embed(kind, datetime.datetime.now(TZ))
        await ctx.send(embed=e)

    # ------------------------------------------------ تيك توك
    @tasks.loop(minutes=10)
    async def tiktok_loop(self):
        for guild in self.bot.guilds:
            t = cfg(guild.id)["tiktok"]
            ch = guild.get_channel(t["channel"]) if t["channel"] else None
            if not t["user"] or not ch:
                continue
            try:
                vids = await asyncio.to_thread(fetch_tiktok, t["user"])
            except Exception as err:
                print(f"[tiktok] {t['user']}: {err}")
                continue
            new = [v for v in vids if v[0] not in t["seen"]]
            if not new:
                continue
            role = guild.get_role(t["role"]) if t["role"] else None
            for vid, url in reversed(new):          # الأقدم أول
                t["seen"].append(vid)
                try:
                    await ch.send(
                        f"{role.mention + ' ' if role else ''}🎬 **فيديو جديد في تيك توك!**\n{url}",
                        allowed_mentions=discord.AllowedMentions(roles=True))
                except discord.HTTPException:
                    pass
            t["seen"] = t["seen"][-60:]
            save()

    @tiktok_loop.before_loop
    async def _b2(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="tiktokset", description="إشعار عند نزول فيديو جديد في حساب تيك توك")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def tiktokset(self, ctx, username: str, channel: discord.TextChannel, role: discord.Role = None):
        if ctx.interaction:
            await ctx.defer()
        user = clean_user(username)
        try:
            vids = await asyncio.to_thread(fetch_tiktok, user)
        except Exception as err:
            return await ctx.send(embed=E(
                "❌ ما قدرت أقرأ الحساب",
                f"تأكد من اليوزر، وحدّث المكتبة: `pip install -U yt-dlp`\n```{str(err)[:300]}```", C_ERR))
        t = cfg(ctx.guild.id)["tiktok"]
        t.update(user=user, channel=channel.id, role=role.id if role else None,
                 seen=[v[0] for v in vids])      # الفيديوهات الحالية ما تنرسل، الجديد بس
        save()
        await ctx.send(embed=E("✅ تم تفعيل إشعارات تيك توك",
                               f"الحساب: **@{user}**\nالروم: {channel.mention}\n"
                               f"المنشن: {role.mention if role else 'بدون'}\nالفحص كل 10 دقايق."))

    @commands.hybrid_command(name="tiktokoff", description="إيقاف إشعارات تيك توك")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def tiktokoff(self, ctx):
        cfg(ctx.guild.id)["tiktok"].update(user=None, channel=None, role=None, seen=[])
        save()
        await ctx.send(embed=E("✅ تم إيقاف إشعارات تيك توك"))

    # ------------------------------------------------ تكلّم عبر البوت
    @commands.hybrid_command(name="relayset", description="روم سرّي: أي شي تكتبه فيه البوت يرسله كما هو في روم ثاني")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def relayset(self, ctx, source: discord.TextChannel, target: discord.TextChannel):
        r = cfg(ctx.guild.id)["relay"]
        r["source"], r["target"] = source.id, target.id
        save()
        await ctx.send(embed=E("✅ تم تفعيل التحدث عبر البوت",
                               f"اكتب في {source.mention} ← يطلع في {target.mention} باسم البوت.\n"
                               "يدعم النص والإيموجي والصور والملفات.\n"
                               "⚠️ خلّ روم الكتابة مخفي إلا عنك وعن الإدارة."))

    @commands.hybrid_command(name="relayoff", description="إيقاف التحدث عبر البوت")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def relayoff(self, ctx):
        r = cfg(ctx.guild.id)["relay"]
        r["source"] = r["target"] = None
        save()
        await ctx.send(embed=E("✅ تم الإيقاف"))

    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        if m.author.bot or not m.guild or not isinstance(m.author, discord.Member):
            return
        r = cfg(m.guild.id)["relay"]
        if not r["source"] or m.channel.id != r["source"]:
            return
        if not m.author.guild_permissions.manage_guild:
            return
        ctx = await self.bot.get_context(m)
        if ctx.valid:                       # أمر عادي، لا تنقله
            return
        target = m.guild.get_channel(r["target"]) if r["target"] else None
        if not target or (not m.content and not m.attachments):
            return
        files = []
        for a in m.attachments:
            try:
                files.append(await a.to_file(spoiler=a.is_spoiler()))
            except discord.HTTPException:
                pass
        ref = None
        if m.reference and isinstance(m.reference.resolved, discord.Message) \
                and m.reference.resolved.channel.id == target.id:
            ref = m.reference.resolved      # لو رديت على رسالة في الروم الهدف، البوت يرد عليها
        try:
            await target.send(
                m.content or None, files=files, reference=ref, mention_author=False,
                allowed_mentions=discord.AllowedMentions(
                    everyone=m.author.guild_permissions.mention_everyone, roles=True, users=True))
            await m.delete()
        except discord.HTTPException as err:
            await m.channel.send(embed=E("❌ ما قدرت أرسل", str(err)[:300], C_ERR), delete_after=8)

async def setup(bot: commands.Bot):
    await bot.add_cog(Extras(bot))
