import asyncio
import io
import logging
import os

import discord
from PIL import Image

import config
import core
import market
import render

# تسجيل الأوامر
import cmds_general  # noqa: F401
import cmds_games    # noqa: F401
import cmds_bank     # noqa: F401

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bank")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


async def market_loop():
    while True:
        try:
            market.maybe_tick()
        except Exception:
            log.exception("market tick failed")
        await asyncio.sleep(15)


@client.event
async def on_ready():
    # الشعار تلقائياً من صورة البوت، أو من assets/logo.png لو موجود
    logo = None
    if os.path.exists(config.LOGO_FILE):
        logo = Image.open(config.LOGO_FILE)
    else:
        try:
            data = await client.user.display_avatar.replace(size=256, format="png").read()
            logo = Image.open(io.BytesIO(data))
        except Exception:
            log.warning("ما قدرت أجيب صورة البوت، بستخدم حرف بدلها")
    render.set_brand(config.BANK_NAME or client.user.name, logo)
    market.ensure()
    if not getattr(client, "_market_task", None):
        client._market_task = asyncio.create_task(market_loop())
    log.info("جاهز: %s", client.user)


@client.event
async def on_message(message):
    await core.dispatch(client, message)


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit("حط التوكن: export DISCORD_TOKEN=xxxx")
    client.run(config.TOKEN)
