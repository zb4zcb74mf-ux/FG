"""نواة البوت: تسجيل الأوامر، السياق (Ctx)، والأزرار."""
import asyncio
import io
import logging
import re
import time

import discord
from PIL import Image

import config
import db
import render
import util

log = logging.getLogger("bank")

COMMANDS: dict = {}
_locks: dict[int, asyncio.Lock] = {}
_avatar_cache: dict = {}


def command(*names):
    def deco(fn):
        for n in names:
            COMMANDS[util.norm(n)] = fn
        return fn
    return deco


def lock(uid: int) -> asyncio.Lock:
    return _locks.setdefault(uid, asyncio.Lock())


class Ctx:
    def __init__(self, client, message, args):
        self.client = client
        self.message = message
        self.author = message.author
        self.uid = message.author.id
        self.args = args
        self.mentions = [m for m in message.mentions if not m.bot or m.id == getattr(client.user, "id", 0)]
        self.target = next((m for m in message.mentions if not m.bot), None)

    # ---- بيانات
    @property
    def user(self) -> dict:
        return db.get_user(self.uid)

    def amount_arg(self, balance=None, idx=0):
        """أول وسيط يشبه مبلغ (يتجاوز المنشن)."""
        bal = self.user["balance"] if balance is None else balance
        if idx < len(self.args):
            return util.parse_amount(self.args[idx], bal)
        return None

    # ---- صور
    async def avatar(self, user) -> Image.Image:
        """user: عضو ديسكورد أو رقم."""
        uid = user if isinstance(user, int) else user.id
        hit = _avatar_cache.get(uid)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        img = None
        try:
            obj = user
            if isinstance(user, int):
                obj = self.client.get_user(user) or await self.client.fetch_user(user)
            data = await obj.display_avatar.replace(size=256, format="png").read()
            img = Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:
            img = render.placeholder("?")
        _avatar_cache[uid] = (time.time(), img)
        return img

    async def who(self, user):
        """(اسم، صورة)"""
        if isinstance(user, int):
            obj = self.client.get_user(user)
            if obj is None:
                try:
                    obj = await self.client.fetch_user(user)
                except Exception:
                    obj = None
            name = getattr(obj, "display_name", None) or str(user)
            return name, await self.avatar(user)
        return user.display_name, await self.avatar(user)

    async def me(self):
        return await self.who(self.author)

    # ---- إرسال
    async def card(self, fn, *a, view=None, **kw):
        img = await asyncio.to_thread(fn, *a, **kw)
        return await self._send(file=discord.File(render.to_bytes(img), "card.png"), view=view)

    async def text(self, msg, view=None):
        return await self._send(content=msg, view=view)

    async def _send(self, **kw):
        kw = {k: v for k, v in kw.items() if v is not None}
        return await self.message.reply(mention_author=False, **kw)

    # ---- صلاحيات
    def is_admin(self) -> bool:
        a = self.author
        if a.id in config.ADMIN_IDS:
            return True
        perms = getattr(a, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True
        roles = {r.id for r in getattr(a, "roles", [])}
        return bool(roles & config.PREMIUM_ROLE_IDS)


class OwnerView(discord.ui.View):
    """أزرار يضغطها صاحب الأمر فقط."""

    def __init__(self, owner_id: int, timeout=60):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("هذي الأزرار مو لك 😅", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


async def dispatch(client, message):
    if message.author.bot or not message.content:
        return
    if config.ALLOWED_CHANNEL_IDS and message.channel.id not in config.ALLOWED_CHANNEL_IDS:
        return
    parts = message.content.strip().split()
    if not parts:
        return
    handler = COMMANDS.get(util.norm(parts[0]))
    if handler is None:
        return
    args = [p for p in parts[1:] if not re.fullmatch(r"<@[!&]?\d+>", p)]
    ctx = Ctx(client, message, args)
    try:
        async with lock(ctx.uid):
            await handler(ctx)
    except Exception:
        log.exception("command failed: %s", message.content)
        try:
            await ctx.text("صار خطأ غير متوقع، حاول مرة ثانية 🙏")
        except Exception:
            pass
