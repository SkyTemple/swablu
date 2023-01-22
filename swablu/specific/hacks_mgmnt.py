import json
import logging
from io import StringIO

from discord import Message, TextChannel, Role, File
from discord.ext.commands import RoleConverter
from swablu.util import MiniCtx

from swablu.config import database, TABLE_NAME, discord_client, get_jam, jam_exists, update_jam, create_jam, db_cursor
from swablu.web import invalidate_cache

ALLOWED_ROLES = [
    712704493661192275,  # Admin
    712704743419543564,  # Mod
]

prefix = '!'
logger = logging.getLogger(__name__)


def create_hack(name: str, role: Role):
    cursor = db_cursor(database)
    sql = f"INSERT INTO {TABLE_NAME} (`key`, `role_name`) VALUES(%s, %s)"
    cursor.execute(sql, (
        name, role.name
    ))
    database.commit()
    cursor.close()


async def process_add_hack(message: Message, channel: TextChannel):
    cmd_parts = message.content.split(' ')
    ctx = MiniCtx(message.guild, discord_client, message)
    if len(cmd_parts) < 3:
        raise ValueError("Missing parameters. Usage: !add_hack <key> <role>")
    role = await RoleConverter().convert(ctx, cmd_parts[2])
    create_hack(cmd_parts[1], role)
    await channel.send(
        f"New Hack `{cmd_parts[1]}` created for role {role.name}"
    )


async def process_dump_jam(message: Message, channel: TextChannel):
    cmd_parts = message.content.split(' ')
    if len(cmd_parts) < 2:
        raise ValueError("Missing parameters. Usage: !dump_jam <key>")
    jam_key = cmd_parts[1]

    jam = get_jam(database, jam_key)

    data = StringIO()
    json.dump(jam, data, indent=2)
    data.seek(0)

    await channel.send("", files=[
        File(data, f"{jam_key}.json")
    ])


async def process_create_jam(message: Message, channel: TextChannel):
    cmd_parts = message.content.split(' ')
    if len(cmd_parts) < 2:
        raise ValueError("Missing parameters. Usage: !create_jam <key>")
    if len(message.attachments) != 1:
        raise ValueError("Missing file to update to.")
    jam_key = cmd_parts[1]
    jam_data = await message.attachments[0].read()

    if jam_exists(database, jam_key):
        raise ValueError("This jam already exists. Use !update_jam.")

    create_jam(database, jam_key, jam_data)
    invalidate_cache(f'jam-{jam_key}')
    await channel.send("OK")


async def process_update_jam(message: Message, channel: TextChannel):
    cmd_parts = message.content.split(' ')
    if len(cmd_parts) < 2:
        raise ValueError("Missing parameters. Usage: !update_jam <key>")
    if len(message.attachments) != 1:
        raise ValueError("Missing file to update to.")
    jam_key = cmd_parts[1]
    jam_data = await message.attachments[0].read()

    if not jam_exists(database, jam_key):
        raise ValueError("This jam does not exist. Use !create_jam.")

    update_jam(database, jam_key, jam_data)
    invalidate_cache(f'jam-{jam_key}')
    await channel.send("OK")


async def process_cmd(message: Message):
    if isinstance(message.channel, TextChannel):
        cmd_parts = message.content.split(' ')
        try:
            if cmd_parts[0] == prefix + 'add_hack':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_add_hack(message, message.channel)
            if cmd_parts[0] == prefix + 'dump_jam':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_dump_jam(message, message.channel)
            if cmd_parts[0] == prefix + 'create_jam':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_create_jam(message, message.channel)
            if cmd_parts[0] == prefix + 'update_jam':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_update_jam(message, message.channel)
        except Exception as ex:
            logger.error("Error running rep command", exc_info=ex)
            await message.channel.send(f"Error running this command: {str(ex)}")
