import asyncio
import logging

from swablu.specific import hacks_mgmnt, eos_dungeons
from swablu.specific.abridged import schedule_abridged

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

from discord import Message
from tornado.web import Application

from swablu.config import discord_client, PORT, DISCORD_BOT_USER_TOKEN, get_template_dir, DISCORD_GUILD_IDS, \
    get_static_dir, COOKIE_SECRET, discord_writes_enabled
from swablu.web import routes


loop_started = False
logger = logging.getLogger(__name__)


@discord_client.event
async def on_ready():
    global loop_started
    logger.info(f'{discord_client.user} has connected to Discord!')
    if not loop_started:
        loop_started = True
        await eos_dungeons.start()


@discord_client.event
async def on_message(message: Message):
    if check_and_remove_message_prefix(message):
        logger.info("Message by " + str(message.author.id) + ": " + message.content)

        if await eos_dungeons.process_message(message):
            return
        if not discord_writes_enabled():
            return
        if message.guild.id in DISCORD_GUILD_IDS:
            await hacks_mgmnt.process_cmd(message)
    else:
        logger.info("Ignoring message by " + str(message.author.id) + ": " + message.content)


def check_and_remove_message_prefix(message: Message) -> bool:
    if message.content.startswith("<@" + str(discord_client.user.id) + "> "):
        message.content = message.content.removeprefix("<@" + str(discord_client.user.id) + "> ")
        return True
    elif message.content.startswith("<@" + str(discord_client.user.id) + ">"):
        message.content = message.content.removeprefix("<@" + str(discord_client.user.id) + ">")
        return True
    else:
        return False


logger.info('Starting!')

app = Application(routes, template_path=get_template_dir(), static_path=get_static_dir(), cookie_secret=COOKIE_SECRET)
app.listen(int(PORT))
aloop = asyncio.get_event_loop()
asyncio.ensure_future(discord_client.start(DISCORD_BOT_USER_TOKEN), loop=aloop)
asyncio.ensure_future(schedule_abridged(), loop=aloop)
aloop.run_forever()
