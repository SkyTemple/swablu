import asyncio
import logging

from swablu.specific import reputation, hacks_mgmnt
from swablu.specific.decimeter import schedule_decimeter

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
from asyncio import sleep

from discord import Member, Message, TextChannel, User
from tornado.web import Application

from swablu.config import discord_client, PORT, DISCORD_BOT_USER_TOKEN, get_template_dir, DISCORD_GUILD_ID, \
    get_static_dir, COOKIE_SECRET
from swablu.roles import scan_roles, check_for, get_role
from swablu.web import routes
import re

loop_started = False
logger = logging.getLogger(__name__)

ANNOUNCEMENT_THREAD_ARCHIVE_DURATION = 1440 # 24 hours

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


@discord_client.event
async def on_message(message: Message):
    if isinstance(message.channel, TextChannel) and message.channel.name == 'welcome' and message.content == '🎉?':
        greet_count = 0
        async with message.channel.typing():
            async for message in message.channel.history(limit=None):
                message: Message
                greet_count += sum([r.count for r in message.reactions if r.emoji == '🎉'])
            await message.channel.send(f'Members have greeted {greet_count} times! 🎉')
    elif message.content.lower() == 'no u' and message.author.id != 789984504839929876:
        await message.channel.send('no u')
    elif isinstance(message.channel, TextChannel) and message.channel.name == 'announcements' \
        or message.channel.name == 'hack-announcements':
            first_line = message.content.partition("\n")[0]
            first_line = re.sub(r"<.*>", "", first_line) # Attempt to get rid special tokens like emotes, tags etc.

            name = f"Discussion | {first_line}" if len(first_line) > 0 else "Announcement discussion"
            # Thread names can only be 100 characters long
            name = (name[:97] + '...') if len(name) > 97 else name

            await message.create_thread(name=name, auto_archive_duration=ANNOUNCEMENT_THREAD_ARCHIVE_DURATION)
    else:
        await reputation.process_cmd(message)
        await hacks_mgmnt.process_cmd(message)


logger.info('Starting!')

app = Application(routes, template_path=get_template_dir(), static_path=get_static_dir(), cookie_secret=COOKIE_SECRET)
app.listen(int(PORT))
aloop = asyncio.get_event_loop()
asyncio.ensure_future(discord_client.start(DISCORD_BOT_USER_TOKEN), loop=aloop)
asyncio.ensure_future(schedule_decimeter(), loop=aloop)
aloop.run_forever()
