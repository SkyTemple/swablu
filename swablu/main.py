import asyncio
import logging

from swablu.specific import reputation, hacks_mgmnt, general_memes, eos_dungeons
from swablu.specific.abridged import schedule_abridged

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
from asyncio import sleep

from discord import Member, Message, TextChannel
from tornado.web import Application

from swablu.config import discord_client, PORT, DISCORD_BOT_USER_TOKEN, get_template_dir, DISCORD_GUILD_IDS, \
    get_static_dir, COOKIE_SECRET, discord_writes_enabled
from swablu.roles import scan_roles, check_for, get_role, using_skytemple, using_dreamnexus, skytemple_app_id, \
    dreamnexus_app_id
from swablu.web import routes


loop_started = False
logger = logging.getLogger(__name__)


async def loop():
    while True:
        await scan_roles()
        await sleep(1800)


@discord_client.event
async def on_ready():
    global loop_started
    logger.info(f'{discord_client.user} has connected to Discord!')
    if not loop_started:
        loop_started = True
        await eos_dungeons.start()
        await loop()


@discord_client.event
async def on_member_update(before: Member, after: Member):
    # Only second guild (DreamNexus) supported
    if len(DISCORD_GUILD_IDS > 1) and after.guild.id == DISCORD_GUILD_IDS[1]:
        await check_for(after, get_role(after.guild, using_dreamnexus), dreamnexus_app_id)


@discord_client.event
async def on_message(message: Message):
    if await eos_dungeons.process_message(message):
        return
    if not discord_writes_enabled():
        return
    if message.guild.id in DISCORD_GUILD_IDS:
        await reputation.process_cmd(message)
        await hacks_mgmnt.process_cmd(message)
        await general_memes.process_cmd(message)
    else:
        await general_memes.process_cmd(message)


logger.info('Starting!')

app = Application(routes, template_path=get_template_dir(), static_path=get_static_dir(), cookie_secret=COOKIE_SECRET)
app.listen(int(PORT))
aloop = asyncio.get_event_loop()
asyncio.ensure_future(discord_client.start(DISCORD_BOT_USER_TOKEN), loop=aloop)
asyncio.ensure_future(schedule_abridged(), loop=aloop)
aloop.run_forever()
