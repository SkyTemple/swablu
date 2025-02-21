import time
from typing import Optional

import discord
from discord import Client, TextChannel, User

from swablu.config import DISCORD_GUILD_IDS, discord_client, get_hack_authors
from swablu.roles import get_hack_type_str


async def regenerate_message(dbcon, discord_client: Client, channel_id: int, message_id: Optional['int'], hack: dict):
    authors = get_hack_author_mentions_str(dbcon, hack['key'])
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


def get_hack_author_names_str(dbcon, hack_key: str) -> str:
    author_ids = get_hack_authors(dbcon, hack_key)
    author_usernames = get_usernames(author_ids)
    return ", ".join(author_usernames)


def get_hack_author_mentions_str(dbcon, hack_key: str) -> str:
    author_ids = get_hack_authors(dbcon, hack_key)
    author_mentions = [f"<@{_id}>" for _id in author_ids]
    return ", ".join(author_mentions)


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


def get_username(discord_id: int) -> str:
    try:
        u: User = discord_client.get_user(discord_id)
        # if the discriminator is 0, they are using the name discord name system.
        if u.discriminator == "0":
            return u.name
        return u.name + '#' + u.discriminator
    except:
        return f'<@{discord_id}>'


def get_usernames(discord_ids: list[int]) -> list[str]:
    return [get_username(discord_id) for discord_id in discord_ids]
