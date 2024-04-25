import time
from typing import Optional

import discord
from discord import Client, TextChannel, Guild

from swablu.config import DISCORD_GUILD_IDS
from swablu.roles import get_hack_type_str

async def regenerate_message(discord_client: Client, channel_id: int, message_id: Optional['int'], hack: dict):
    authors = get_authors(discord_client, hack['role_name'], False)
    text = f'**{hack["name"]}** by {authors} ({get_hack_type_str(hack["hack_type"])}):\n<https://hacks.skytemple.org/h/{hack["key"]}>'
    channel: TextChannel = discord_client.get_channel(channel_id)
    try_count = 0
    while try_count < 10:
        try:
            if not message_id:
                message = await channel.send(text)
                message_id = message.id
            else:
                message = await channel.fetch_message(message_id)
                if message.content != text:
                    await message.edit(content=text)
            break
        except Exception:
            try_count += 1
            if try_count >= 10:
                raise
            time.sleep(try_count * 5)

    return message_id

def get_authors(discord_client, rrole: str, as_names=False):
    # Only first guild (SkyTemple) supported
    guild = discord_client.get_guild(DISCORD_GUILD_IDS[0])
    authors = '???'
    for role in guild.roles:
        if role.name == rrole:
            authors = []
            for member in role.members:
                if as_names:
                    authors.append(member.name)
                else:
                    authors.append(f'<@{member.id}>')
            authors = ', '.join(authors)
    return authors


async def has_role(discord_client: discord.Client, user_id: int, role_id: int) -> bool:
    """
    Checks if the given user has the given role on the server set in the config (DISCORD_GUILD_ID environment variable).
    :param discord_client: Discord client
    :param user_id: User to check
    :param role_id: Role to check
    :return: True if the user has the specified role, false otherwise
    """
    guild = discord_client.get_guild(DISCORD_GUILD_IDS[0])
    role = guild.get_role(role_id)
    try:
        user = await guild.fetch_member(user_id)
    except discord.NotFound:
        return False

    return role in user.roles
