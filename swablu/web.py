import base64
import json
import logging
import mimetypes
import re
import traceback
import uuid
from abc import abstractmethod, ABC
from random import shuffle

import tornado.web
import os
from requests_oauthlib import OAuth2Session


from discord import Client, Guild, Member
from mysql.connector import MySQLConnection
from tornado import httputil

from swablu.config import discord_client, database, AUTHORIZATION_BASE_URL, OAUTH2_REDIRECT_URI, OAUTH2_CLIENT_ID, \
    OAUTH2_CLIENT_SECRET, TOKEN_URL, API_BASE_URL, DISCORD_GUILD_ID, DISCORD_ADMIN_ROLE, get_rom_hacks, \
    regenerate_htaccess, DISCORD_CHANNEL_HACKS, update_hack, get_rom_hack, get_jam
from swablu.discord_util import regenerate_message, get_authors
from swablu.roles import get_hack_type_str
from swablu.specific import reputation
from swablu.specific.translate_webhook import TranslateHookHandler

OAUTH_SCOPE = ['identify']
DEFAULT_AUTHOR_DESCRIPTION = {
    'author': 'Parakoopa',
    'description': "ROM editor for Pokémon Mystery Dungeon Explorers of Sky. Let's you edit starters, graphics, scenes, dungeons and more!"
}
ALLOWED_MIMES = ['image/jpeg', 'image/png']

if 'http://' in OAUTH2_REDIRECT_URI:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'
logger = logging.getLogger(__name__)


class SessionTokenProvider:
    tokens = {}

    @classmethod
    def get(cls, session_id):
        if session_id in cls.tokens:
            return cls.tokens[session_id]
        return None

    @classmethod
    def set(cls, session_id, token):
        cls.tokens[session_id] = token


# noinspection PyAttributeOutsideInit,PyAbstractClass,PyShadowingNames
class BaseHandler(tornado.web.RequestHandler, ABC):
    def initialize(self, discord_client: Client, db: MySQLConnection):
        self.discord_client: Client = discord_client
        self.db: MySQLConnection = db

    async def get(self, *args, **kwargs):
        try:
            if await self.auth():
                await self.do_get(*args, **kwargs)
        except Exception as err:
            self.set_status(500)
            logger.exception(err)
            await self.render("error.html", title="SkyTemple - Internal Server Error",
                              trace=traceback.format_exc(), err=err, **DEFAULT_AUTHOR_DESCRIPTION)

    @abstractmethod
    async def do_get(self, *args, **kwargs):
        pass

    async def auth(self):
        return True

    async def prepare(self):
        await self.discord_client.wait_until_ready()

    def token_updater(self, token):
        self.set_cookie('oauth2_token', token)

    def make_session(self, token=None, state=None, scope=None) -> OAuth2Session:
        return OAuth2Session(
            client_id=OAUTH2_CLIENT_ID,
            token=token,
            state=state,
            scope=scope,
            redirect_uri=OAUTH2_REDIRECT_URI,
            auto_refresh_kwargs={
                'client_id': OAUTH2_CLIENT_ID,
                'client_secret': OAUTH2_CLIENT_SECRET,
            },
            auto_refresh_url=TOKEN_URL,
            token_updater=self.token_updater
        )


# noinspection PyAbstractClass
class AuthenticatedHandler(BaseHandler, ABC):
    def __init__(self, application: tornado.web.Application, request: httputil.HTTPServerRequest, **kwargs: any):
        self.hack_access = []
        super().__init__(application, request, **kwargs)

    async def auth(self):
        if not self.get_secure_cookie('session_id'):
            discord_session = self.make_session(scope=OAUTH_SCOPE)
            authorization_url, state = discord_session.authorization_url(AUTHORIZATION_BASE_URL)
            self.set_cookie('oauth2_state', state)
            self.redirect(authorization_url, permanent=False)
            return False

        sc = str(self.get_secure_cookie('session_id'), 'utf-8')
        discord = self.make_session(token=SessionTokenProvider.get(sc))
        user = discord.get(API_BASE_URL + '/users/@me').json()
        if 'id' in user:
            user_id = user['id']
        else:
            logger.warning(f"OAuth login error: {sc} - {user}")
            discord_session = self.make_session(scope=OAUTH_SCOPE)
            authorization_url, state = discord_session.authorization_url(AUTHORIZATION_BASE_URL)
            self.set_cookie('oauth2_state', state)
            self.redirect(authorization_url, permanent=False)
            return False
        guild: Guild = discord_client.get_guild(DISCORD_GUILD_ID)
        member: Member = guild.get_member(int(user_id))
        if not member:
            await self.not_authenticated()
            return False

        is_admin = any([r.id == DISCORD_ADMIN_ROLE for r in member.roles])
        role_names = [r.name for r in member.roles if r.name.startswith("Hack")]
        if is_admin:
            self.hack_access = get_rom_hacks(self.db)
        else:
            self.hack_access = get_rom_hacks(self.db, role_names)
        if len(self.hack_access) < 1:
            await self.not_authenticated()
            return False
        return True

    async def not_authenticated(self):
        await self.render("not_authenticated.html", title="SkyTemple",
                          **DEFAULT_AUTHOR_DESCRIPTION)


# noinspection PyAbstractClass
class CallbackHandler(BaseHandler):
    async def do_get(self):
        logger.info("Trying OAuth...")
        if self.get_argument('error', default='') != '':
            self.set_status(400)
            return self.write(self.get_argument('error'))
        self.set_status(200)
        discord_session = self.make_session(state=self.get_cookie('oauth2_state'))
        token = discord_session.fetch_token(
            TOKEN_URL, self.get_argument('code'),
            client_secret=OAUTH2_CLIENT_SECRET,
            include_client_id=True
        )
        session_id = uuid.uuid4().hex
        self.set_secure_cookie('session_id', session_id)
        SessionTokenProvider.set(session_id, token)
        return self.redirect('/edit')


# noinspection PyAbstractClass
class EditListHandler(AuthenticatedHandler):
    async def do_get(self, **kwargs):
        if len(self.hack_access) == 1:
            return self.redirect(f'/edit/{self.hack_access[0]["key"]}')
        await self.render('edit-list.html',
                          title='SkyTemple - Edit ROM Hack',
                          hack_list=sorted(self.hack_access, key=lambda h: h['key']),
                          **DEFAULT_AUTHOR_DESCRIPTION)


# noinspection PyAbstractClass
class ListingHandler(BaseHandler):
    async def do_get(self, **kwargs):
        hack = get_rom_hack(self.db, kwargs['hack_id'])
        if hack and hack['message_id']:
            authors = get_authors(self.discord_client, hack['role_name'], True)
            desc = str(hack['description'], 'utf-8')
            description_lines = desc.splitlines()
            await self.render('listing.html',
                              title=f'{hack["name"]} - SkyTemple Hack Directory',
                              hack=hack,
                              description=hack["description"],
                              hack_type=get_hack_type_str(hack["hack_type"]),
                              author=authors,
                              description_lines=description_lines)
            return
        return self.redirect('https://skytemple.org')


# noinspection PyAbstractClass
class JamHandler(BaseHandler):
    async def do_get(self, **kwargs):
        jam = None
        try:
            jam = get_jam(self.db, kwargs['jam_key'])
        except Exception as ex:
            logger.warning("Jam error.", exc_info=ex)

        # TODO TMP
        jam = {
            'description': 'This has been the first ROM Hack Game Jam by the SkyTemple community, '
                           'and we\'ve been blown away with 12 submissions with amazing quality! '
                           'Thanks to everyone who submitted!',
            'motto': 'An Unlikely Team',
            'gimmick': 'Have a Pokémon not present in the base game take an important role',
            'other_text': 'With so many amazing ROM Hacks and only 9 awards, sadly not everyone can win. '
                          'Here are the other submitted ROM Hacks, which are also all really good but didn\'t quite get '
                          'one of the awards. For some of them it was REALLY close, so don\'t be discouraged by not '
                          'getting an award. The competition was really tough!',
            'hacks': {
                'chip2': '',
                'unknown': '',
                'victorious': '',
                'ccprologue': '',
                'distant': '',
                'fountvictory': '',
                'crashingdimensions': '',
                'amaura': '',
                'blizzardisland': '',
                'fragments': '',
                'stardom': '',
            },
            'awards': {
                'golden': {'Best Hack': ['blizzardisland']},
                'silver': {
                    'Best Use of Topic': ['blizzardisland'],
                    'Best Use of Gimmick': ['amaura', 'chip2'],
                },
                'bronze': {
                    'Best Gameplay': ['amaura'],
                    'Best Narrative': ['distant'],
                    'Best Cutscenes': ['distant', 'unknown'],
                    'Best Dungeon Design': ['blizzardisland', 'chip2'],
                    'Best Custom Graphics': ['blizzardisland'],
                    'Most Unique or Creative': ['amaura'],
                }
            },
            'dq': [
                {
                    'name': 'John Cena and the Quest for the Undertale Orgy',
                    'description': ['Follow John Cena, Copypasta Vaporeon, and Bidoof from Grass Continent as they embark on the adventure of a lifetime. Filled with dead memes and sexual innuendo, this hack is for mature audiences only. About 15-20 minutes long. Created by Ass Cucumber.'],
                    'author': '268142625280884736',
                    'screenshot1': 'data:image/png;base64,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',
                    'screenshot2': 'data:image/png;base64,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',
                    'video': None,
                    'url_main': None,
                    'url_download': None,
                    'url_discord': None,
                    'jury': ''
                }
            ]
        }
        if jam is not None:
            left = list(jam['hacks'].keys())
            winners = []
            for award, hacks in (jam['awards']['golden'] | jam['awards']['silver'] | jam['awards']['bronze']).items():
                for hack in hacks:
                    if hack in left:
                        winners.append(hack)
                        left.remove(hack)
            hackdata = {}
            for hack in jam['hacks'].keys():
                hackdata[hack] = get_rom_hack(self.db, hack)
                hackdata[hack]['author'] = get_authors(self.discord_client, hackdata[hack]['role_name'], True)
                hackdata[hack]['description'] = str(hackdata[hack]['description'], 'utf-8').splitlines()
                hackdata[hack]['awards'] = []
                for award, hacks in (jam['awards']['golden'] | jam['awards']['silver'] | jam['awards']['bronze']).items():
                    for ahack in hacks:
                        if ahack == hack:
                            hackdata[hack]['awards'].append(award)
            for dq in jam['dq']:
                member = discord_client.get_user(int(dq['author']))
                dq['author'] = f'{member.name}#{member.discriminator}'
            award_groups = {}
            for award in jam['awards']['golden'].keys():
                award_groups[award] = 'golden'
            for award in jam['awards']['silver'].keys():
                award_groups[award] = 'silver'
            for award in jam['awards']['bronze'].keys():
                award_groups[award] = 'bronze'
            shuffle(left)
            await self.render('jam.html',
                              title=f'SkyTemple Hack Jam - {jam["motto"]}',
                              jam=jam,
                              winners=winners,
                              others=left,
                              hackdata=hackdata, award_groups=award_groups,
                              description=jam['description'],
                              author="SkyTemple Community")
            return
        return self.redirect('https://skytemple.org')


# noinspection PyAbstractClass
class EditFormHandler(AuthenticatedHandler):
    async def post(self, hack_id):
        key = self.get_body_argument('key', '')
        if not await self.auth():
            return
        hack = None
        for hackc in self.hack_access:
            if hackc['key'] == hack_id:
                hack = hackc
                break
        if key != hack_id or not hack:
            return self.redirect('/edit')
        hack['name'] = self.get_body_argument('name', '')
        hack['description'] = self.get_body_argument('description', '')
        hack['hack_type'] = self.get_body_argument('hack_type', '')
        hack['url_main'] = self.get_body_argument('url_main', '')
        hack['url_discord'] = self.get_body_argument('url_discord', '')
        hack['url_download'] = self.get_body_argument('url_download', '')
        screenshot1 = self.request.files.get('screenshot1', None)
        screenshot2 = self.request.files.get('screenshot2', None)
        if screenshot1:
            mime = mimetypes.guess_type(screenshot1[0]['filename'])[0] or "application/octet-stream"
            if mime in ALLOWED_MIMES and len(screenshot1[0]["body"]) <= 1000000:
                hack['screenshot1'] = f'data:{mime};base64,{str(base64.b64encode(screenshot1[0]["body"]), "ascii")}'
        if screenshot2:
            mime = mimetypes.guess_type(screenshot2[0]['filename'])[0] or "application/octet-stream"
            if mime in ALLOWED_MIMES and len(screenshot2[0]["body"]) <= 1000000:
                hack['screenshot2'] = f'data:{mime};base64,{str(base64.b64encode(screenshot2[0]["body"]), "ascii")}'
        hack['video'] = self.get_body_argument('video', '')
        regex = re.compile(r'^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*).*')
        m = regex.match(hack['video'])
        if m:
            hack['video'] = m.group(7)

        hack['message_id'] = await regenerate_message(self.discord_client, DISCORD_CHANNEL_HACKS,
                                                      int(hack['message_id']) if hack['message_id'] else None, hack)
        update_hack(self.db, hack)
        regenerate_htaccess()
        return self.redirect(f'/edit/{hack_id}?saved=1')

    async def do_get(self, **kwargs):
        for hack in self.hack_access:
            if hack['key'] == kwargs['hack_id']:
                await self.render('edit-form.html',
                                  title='SkyTemple - Edit ROM Hack',
                                  hack=hack,
                                  saved=bool(self.get_argument('saved', '')),
                                  **DEFAULT_AUTHOR_DESCRIPTION)
                return
        return self.redirect('/edit')


extra = {
    "discord_client": discord_client,
    "db": database,
}

routes = [
    (r"/", EditListHandler, extra),
    (r"/callback/?", CallbackHandler, extra),
    (r"/h/(?P<hack_id>[^\/]+)/?", ListingHandler, extra),
    (r"/jam/(?P<jam_key>[^\/]+)/?", JamHandler, extra),
    (r"/edit/?", EditListHandler, extra),
    (r"/edit/(?P<hack_id>[^\/]+)/?", EditFormHandler, extra),
    (r"/translate_hook", TranslateHookHandler, extra),
] + reputation.collect_web_routes(extra)
