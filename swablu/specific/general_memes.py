from discord import Message

from swablu.config import DISCORD_GUILD_IDS


async def process_cmd(message: Message):
    if message.content.lower() == 'no u' and message.author.id != 789984504839929876 and message.guild.id not in DISCORD_GUILD_IDS:
        await message.channel.send('no u')
