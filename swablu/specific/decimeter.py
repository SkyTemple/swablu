import logging
from asyncio import sleep
from random import randrange

from discord import Guild, TextChannel, Role, Colour

from swablu.config import discord_client, DISCORD_GUILD_IDS, discord_writes_enabled

MIN_TIME = 720  # min
MAX_TIME = 17280  # min
MIN_APPEAR_TIME = 1  # min
MAX_APPEAR_TIME = 1440  # min
logger = logging.getLogger(__name__)
ROLE_ID = 804438255185559662
COLOR_CODE = 0x3872f1
CHANNEL_ID = 804426600569503815


async def schedule_decimeter():
    if not discord_writes_enabled():
        return
    first = True
    while True:
        if first:
            first = False
            time = randrange(MAX_TIME // 2, MAX_TIME)
        else:
            time = randrange(MIN_TIME, MAX_TIME)
        logger.info(f'Scheduled next Decimeter event in {time} min.')
        await sleep(time * 60)
        await show_decimeter()


async def show_decimeter():
    # Only first guild (SkyTemple) supported
    guild: Guild = discord_client.get_guild(DISCORD_GUILD_IDS[0])
    channel: TextChannel = guild.get_channel(CHANNEL_ID)
    everyone: Role = guild.default_role
    role: Role = guild.get_role(ROLE_ID)
    await channel.set_permissions(everyone, read_messages=True)
    await role.edit(colour=Colour(COLOR_CODE), hoist=True)
    appear_time = randrange(MIN_APPEAR_TIME, MAX_APPEAR_TIME)
    logger.info(f'DECIMETER EVENT! Ends in {appear_time} min.')
    await sleep(appear_time * 60)

    # Something's stirring...
    await channel.send("*Something's stirring...*")
    await sleep(60)
    await channel.send("*Something's approaching...*")
    await sleep(60)
    await channel.send("*It's getting closer!*")
    await sleep(60)
    await channel.send("*It's right nearby!*")
    await sleep(60)

    await channel.set_permissions(everyone, read_messages=False)
    await role.edit(colour=Colour.default(), hoist=False)
    logger.info(f'DECIMETER EVENT ENDED!')
