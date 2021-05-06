import logging
from discord import Message, TextChannel, Role
from discord.ext.commands import RoleConverter
from swablu.util import MiniCtx

from swablu.config import database, TABLE_NAME, discord_client

ALLOWED_ROLES = [
    712704493661192275,  # Admin
    712704743419543564,  # Mod
]

prefix = '!'
logger = logging.getLogger(__name__)


def create_hack(name: str, role: Role):
    cursor = database.cursor()
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


async def process_cmd(message: Message):
    if isinstance(message.channel, TextChannel):
        cmd_parts = message.content.split(' ')
        try:
            if cmd_parts[0] == prefix + 'add_hack':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_add_hack(message, message.channel)
        except Exception as ex:
            logger.error("Error running rep command", exc_info=ex)
            await message.channel.send(f"Error running this command: {str(ex)}")
