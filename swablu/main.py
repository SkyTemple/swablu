import asyncio
import logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
from asyncio import sleep

from discord import Member
from tornado.web import Application

from swablu.config import discord_client, PORT, DISCORD_BOT_USER_TOKEN, get_template_dir, DISCORD_GUILD_ID, \
    get_static_dir, COOKIE_SECRET
from swablu.roles import scan_roles, check_for, get_role
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
        await loop()


@discord_client.event
async def on_member_update(before: Member, after: Member):
    if after.guild.id == DISCORD_GUILD_ID:
        await check_for(after, get_role(after.guild))


logger.info('Starting!')

app = Application(routes, template_path=get_template_dir(), static_path=get_static_dir(), cookie_secret=COOKIE_SECRET)
app.listen(int(PORT))
aloop = asyncio.get_event_loop()
asyncio.ensure_future(discord_client.start(DISCORD_BOT_USER_TOKEN), loop=aloop)
aloop.run_forever()
