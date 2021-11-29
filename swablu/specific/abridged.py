import logging
from asyncio import sleep
from random import randrange

from discord import Guild, TextChannel, Role

from swablu.config import discord_writes_enabled, discord_client
from swablu.specific.decimeter import MIN_APPEAR_TIME, MAX_APPEAR_TIME
logger = logging.getLogger(__name__)

GUILD_ID = 805613370098974731
DISTORTION_WORLD = 827921045176057887
FLATOT = 839299783688847370
MIN_TIME = 10
MAX_TIME = 20160

MIN_WAIT_TIME = 0
MAX_WAIT_TIME = 21600


async def abridged():
    guild: Guild = discord_client.get_guild(GUILD_ID)
    channel: TextChannel = guild.get_channel(DISTORTION_WORLD)
    smode = randrange(MIN_WAIT_TIME, MAX_WAIT_TIME + 1)
    logger.info(f"Changed distortion world slow mode to {smode}.")
    await channel.edit(slowmode_delay=smode)
    if randrange(0, 10) == 0:
        appear_time = randrange(MIN_APPEAR_TIME, MAX_APPEAR_TIME)
        logger.info(f'FLATOT EVENT! Ends in {appear_time} min.')
        channel: TextChannel = guild.get_channel(FLATOT)
        everyone: Role = guild.default_role
        await channel.set_permissions(everyone, read_messages=True)
        await sleep(appear_time * 60)
        await channel.set_permissions(everyone, read_messages=False)
        logger.info(f'FLATOT EVENT ENDED!')


async def schedule_abridged():
    if not discord_writes_enabled():
        return
    first = True
    while True:
        if first:
            first = False
            time = 0.1
        else:
            time = randrange(MIN_TIME, MAX_TIME)
        logger.info(f'Scheduled next Abridged event in {time} min.')
        await sleep(time * 60)
        await abridged()