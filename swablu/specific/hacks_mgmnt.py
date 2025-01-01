import json
import logging
from io import StringIO

from discord import Message, TextChannel, Role, File, Embed
from discord.ext.commands import RoleConverter
from swablu.util import MiniCtx

from swablu.config import database, TABLE_NAME_HACKS, discord_client, discord_writes_enabled, get_jam, get_rom_hacks, \
    jam_exists, update_jam, create_jam, db_cursor, DISCORD_CHANNEL_HACKS, update_hack_authors, get_hack_authors
from swablu.discord_util import regenerate_message, get_authors_as_ids
from swablu.web import invalidate_jam_cache

ALLOWED_ROLES = [
    712704493661192275,  # Admin
    712704743419543564,  # Mod
    367451227551694852,  # Test server - Admin
    367451406468382722,  # Test server - Mod
]

ALLOWED_ROLES_ADMIN = [
    712704493661192275,  # Admin
    367451227551694852,  # Test server - Admin
]

prefix = '!'
logger = logging.getLogger(__name__)


def create_hack(name: str, role: Role):
    cursor = db_cursor(database)
    sql = f"INSERT INTO {TABLE_NAME_HACKS} (`key`, `role_name`) VALUES(%s, %s)"
    cursor.execute(sql, (
        name, role.name
    ))
    database.commit()
    cursor.close()


def delete_hack(name: str):
    cursor = db_cursor(database)
    sql = f"DELETE FROM {TABLE_NAME_HACKS} WHERE `key` = %s"
    cursor.execute(sql, (
        name,
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


async def process_delete_hack(message: Message, channel: TextChannel):
    cmd_parts = message.content.split(' ')
    if len(cmd_parts) < 2:
        raise ValueError("Missing parameters. Usage: !delete_hack <key>")
    delete_hack(cmd_parts[1])
    await channel.send(
        f"Hack `{cmd_parts[1]}` deleted"
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
    invalidate_jam_cache(jam_key, jam_data)
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
    invalidate_jam_cache(jam_key, jam_data)
    await channel.send("OK")


async def process_update_hack_list(channel: TextChannel):
    if not discord_writes_enabled():
        raise ValueError("Cannot update hack list: Discord writes are disabled in the config.")

    hacks = get_rom_hacks(database)
    for hack in hacks:
        if hack['message_id']:
            await regenerate_message(discord_client, DISCORD_CHANNEL_HACKS, int(hack['message_id']), hack)

    await channel.send("Hack list successfully updated")


async def process_migrate_hack_roles(channel: TextChannel):
    if not discord_writes_enabled():
        raise ValueError("Cannot migrate hack author list: Discord writes are disabled in the config.")

    hacks = get_rom_hacks(database)
    for hack in hacks:
        authors = get_authors_as_ids(discord_client, hack['role_name'])
        update_hack_authors(database, hack['key'], authors)

    await channel.send("Hack roles successfully migrated.")


async def process_get_hack_authors(message: Message, channel: TextChannel):
    if not discord_writes_enabled():
        raise ValueError("Cannot retrieve hack author list: Discord writes are disabled in the config.")

    cmd_parts = message.content.split(' ')
    if len(cmd_parts) < 2:
        raise ValueError("Missing parameters. Usage: !get_hack_authors <hack key or name>")

    requested_hack = " ".join(cmd_parts[1:])

    hacks = get_rom_hacks(database)
    matched_hacks = []
    for hack in hacks:
        if (
            hack['key'] == requested_hack or
            hack['name'] is not None and requested_hack.lower() in hack['name'].lower()
        ):
            matched_hacks.append(hack)

    if len(matched_hacks) == 0:
        raise ValueError(f"Cannot find a hack with the key or name `{requested_hack}`.")
    elif len(matched_hacks) > 1:
        matched_hacks_str = "\n".join([f"- {hack['name']}" for hack in matched_hacks])
        embed = Embed(description=matched_hacks_str)

        await channel.send(f"Multiple hacks match '{requested_hack}':", embed=embed)
    else:
        hack = matched_hacks[0]
        authors = get_hack_authors(database, hack['key'])

        if len(authors) == 0:
            await channel.send(f"List of authors for hack '{hack['name']}':\nNone")
        else:
            authors_str = ", ".join([f"<@{author}>" for author in authors])
            embed = Embed(description=authors_str)

            await channel.send(f"List of authors for hack '{hack['name']}':", embed=embed)


async def process_cmd(message: Message):
    if isinstance(message.channel, TextChannel):
        cmd_parts = message.content.split(' ')
        try:
            if cmd_parts[0] == prefix + 'add_hack':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_add_hack(message, message.channel)
            if cmd_parts[0] == prefix + 'delete_hack':
                if not any(r.id in ALLOWED_ROLES_ADMIN for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_delete_hack(message, message.channel)
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
            if cmd_parts[0] == prefix + 'update_hack_list':
                if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_update_hack_list(message.channel)
            if cmd_parts[0] == prefix + 'migrate_hack_roles':
                if not any(r.id in ALLOWED_ROLES_ADMIN for r in message.author.roles):
                    raise RuntimeError("You are not allowed to use this command.")
                await process_migrate_hack_roles(message.channel)
            if cmd_parts[0] == prefix + 'get_hack_authors' or cmd_parts[0] == prefix + 'authors':
                await process_get_hack_authors(message, message.channel)
        except Exception as ex:
            logger.error("Error running hack management command", exc_info=ex)
            await message.channel.send(f"Error running this command: {str(ex)}")
