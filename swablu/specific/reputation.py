import json
import logging
import traceback
from typing import List, Tuple, NamedTuple

import tornado.web
from discord import Message, TextChannel, User
from discord.ext.commands import TextChannelConverter, UserConverter

from swablu.config import discord_client, DISCORD_GUILD_IDS, database, TABLE_NAME_REPUTATION, db_cursor
from swablu.util import MiniCtx

ALLOWED_ROLES = [
    712704493661192275,  # Admin
    712704743419543564,  # Mod
    764601232794058752,  # Sprite Approver
    960992828119457852,  # Guild Points
    # DX server:
    886168051060445204   # Mod
]

AUTHORIZED_DM_USERS = [
    101386221028134912,  # Parakoopa
    548718661129732106,  # SpriteBot
    117780585635643396.  # Audino
]

BOT_DM_CHANNEL = 822865440489472020
DEFAULT_REP = 3

DEFAULT_AUTHOR_DESCRIPTION = {
    'author': 'Parakoopa',
    'description': "ROM editor for Pokémon Mystery Dungeon Explorers of Sky. Let's you edit starters, graphics, scenes, dungeons and more!"
}

prefix = '!'
logger = logging.getLogger(__name__)


def get_guild_points_for(user: User) -> int:
    cursor = db_cursor(database, dictionary=True)
    sql = f"SELECT * FROM `{TABLE_NAME_REPUTATION}` WHERE discord_id = %s"
    cursor.execute(sql, (user.id,))
    r = cursor.fetchone()
    d = DEFAULT_REP
    if r:
        d = r['points']
    database.commit()
    cursor.close()
    return d


def give_guild_points_to(user: User, amount: int):
    cursor = db_cursor(database)
    sql = f"INSERT INTO {TABLE_NAME_REPUTATION} (discord_id, points) VALUES(%s, %s) ON DUPLICATE KEY UPDATE points=%s"
    pnts = get_guild_points_for(user) + amount
    cursor.execute(sql, (
        user.id,
        pnts, pnts
    ))
    database.commit()
    cursor.close()


def _get_username(id: int):
    try:
        u: User = discord_client.get_user(id)
        # if the discriminator is 0, they are using the name discord name system.
        if u.discriminator == 0:
            return u.name
        return u.name + '#' + u.discriminator
    except:
        return f'<@{id}>'


class GuidPointResults(NamedTuple):
    idx: int
    discord_id: int
    username: str
    guild_points: int


def get_all_guild_points() -> List[GuidPointResults]:
    cursor = db_cursor(database, dictionary=True)
    sql = f"SELECT * FROM `{TABLE_NAME_REPUTATION}` ORDER BY `points` DESC"
    cursor.execute(sql)
    d = []
    for i, k in enumerate(cursor.fetchall()):
        d.append((i + 1, k['discord_id'], _get_username(k['discord_id']), k['points']))
    database.commit()
    cursor.close()
    return d


async def process_cmd_dm(message: Message):
    cmd_parts = message.content.split(' ')
    channel_converter = TextChannelConverter()
    # Only first server (SkyTemple) supported.
    ctx = MiniCtx(discord_client.get_guild(DISCORD_GUILD_IDS[0]), discord_client, message)
    try:
        if not cmd_parts[0].startswith(prefix):
            return
        if cmd_parts[0] == prefix + 'gr' or cmd_parts[0] == prefix + 'tr':
            if len(cmd_parts) < 4:
                await message.channel.send(json.dumps({
                    'status': 'error',
                    'error': 'gr or tr commands need to have 3 arguments: <user> <amount> <channel>.'
                }))
                return
            channel = await channel_converter.convert(ctx, cmd_parts[3])
            await process_gr(message, channel, cmd_parts[0] == prefix + 'tr')
            await message.channel.send(json.dumps({
                'status': 'success',
                'result': 'See channel.'
            }))
        elif cmd_parts[0] == prefix + 'checkr':
            gps = get_guild_points_for(await UserConverter().convert(ctx, cmd_parts[1]))
            await message.channel.send(json.dumps({
                'status': 'success',
                'result': gps
            }))
        else:
            await message.channel.send(json.dumps({
                'status': 'error',
                'error': 'Unknown Command'
            }))
    except Exception as ex:
        await message.channel.send(json.dumps({
            'status': 'error',
            'error': str(ex)
        }))


async def process_gr(message: Message, channel: TextChannel, negative: bool):
    cmd_parts = message.content.split(' ')
    ctx = MiniCtx(message.guild, discord_client, message)
    if len(cmd_parts) < 2:
        raise ValueError("Missing parameters. Usage: -gr/-tr <user> [points]")
    if len(cmd_parts) < 3:
        points = 1
    else:
        try:
            points = int(cmd_parts[2])
        except ValueError:
            raise ValueError("The number of points to give must be a number.")
    if negative:
        points *= -1
    if points == 0:
        return
    user = await UserConverter().convert(ctx, cmd_parts[1])
    give_guild_points_to(user, points)
    gps = get_guild_points_for(user)
    if points > 0:
        await channel.send(
            f"Gave `{points}` Guild Point(s) to **{user.name}** (current: `{gps}`). -- Leaderboard: <https://hacks.skytemple.org/guildpoints>"
        )
    else:
        await channel.send(
            f"Took away `{-1 * points}` Guild Point(s) from **{user.name}** (current: `{gps}`). -- Leaderboard: <https://hacks.skytemple.org/guildpoints>"
        )


async def process_toprep(message: Message):
    await message.channel.send(
        "Visit <https://hacks.skytemple.org/guildpoints> for the leaderboard."
    )


async def process_checkr(message: Message):
    cmd_parts = message.content.split(' ')
    ctx = MiniCtx(message.guild, discord_client, message)
    user: User
    if len(cmd_parts) < 2:
        user = message.author
    else:
        user = await UserConverter().convert(ctx, cmd_parts[1])
    gps = get_guild_points_for(user)
    await message.channel.send(
        f"**{user.name}** has `{gps}` Guild Point(s). -- Leaderboard: <https://hacks.skytemple.org/guildpoints>"
    )


async def process_cmd(message: Message):
    if isinstance(message.channel, TextChannel):
        if message.channel.id == BOT_DM_CHANNEL:
            if message.author.id in AUTHORIZED_DM_USERS:
                await process_cmd_dm(message)
        else:
            cmd_parts = message.content.split(' ')
            try:
                if cmd_parts[0] == prefix + 'gr' or cmd_parts[0] == prefix + 'tr':
                    if not any(r.id in ALLOWED_ROLES for r in message.author.roles):
                        raise RuntimeError("You are not allowed to give or take Guild Points.")
                    await process_gr(message, message.channel, cmd_parts[0] == prefix + 'tr')
                elif cmd_parts[0] == prefix + 'checkr':
                    await process_checkr(message)
                elif cmd_parts[0] == prefix + 'toprep':
                    await process_toprep(message)
            except Exception as ex:
                logger.error("Error running rep command", exc_info=ex)
                await message.channel.send(f"Error running this command: {str(ex)}")


# noinspection PyAttributeOutsideInit,PyAbstractClass,PyShadowingNames
class GuildPointsHandler(tornado.web.RequestHandler):
    async def get(self, *args, **kwargs):
        try:
            if self.get_query_argument("json", None) is not None:
                self.set_header('Content-Type', 'application/json')
                all_credits = {}
                for _, discord_id, __, points in get_all_guild_points():
                    all_credits[discord_id] = points
                self.write(json.dumps(all_credits))
                await self.flush()
            else:
                await self.render("points.html", title="SkyTemple - Guild Points",
                                  all_points=get_all_guild_points(), **DEFAULT_AUTHOR_DESCRIPTION)
        except Exception as err:
            self.set_status(500)
            logger.exception(err)
            await self.render("error.html", title="SkyTemple - Internal Server Error",
                              trace=traceback.format_exc(), err=err, **DEFAULT_AUTHOR_DESCRIPTION)


def collect_web_routes(extra):
    return [
        (r"/guildpoints", GuildPointsHandler)
    ]
