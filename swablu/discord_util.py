from typing import Optional

from discord import Client, TextChannel, Guild

from swablu.config import DISCORD_GUILD_ID
from swablu.roles import get_hack_type_str


async def regenerate_message(discord_client: Client, channel_id: int, message_id: Optional['int'], hack: dict):
    authors = get_authors(discord_client, hack['role_name'], False)
    text = f'**{hack["name"]}** by {authors} ({get_hack_type_str(hack["hack_type"])}):\n<https://skytemple.org/{hack["key"]}>'
    channel: TextChannel = discord_client.get_channel(channel_id)
    if not message_id:
        message = await channel.send(text)
        message_id = message.id
    else:
        message = await channel.fetch_message(message_id)
        await message.edit(content=text)

    return message_id


def get_authors(discord_client, rrole: str, as_names=False):
    guild = discord_client.get_guild(DISCORD_GUILD_ID)
    authors = '???'
    for role in guild.roles:
        if role.name == rrole:
            authors = []
            for member in role.members:
                if as_names:
                    authors.append(f'{member.name}#{member.discriminator}')
                else:
                    authors.append(f'<@{member.id}>')
            authors = ', '.join(authors)
    return authors
