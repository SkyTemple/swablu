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
    OAUTH2_CLIENT_SECRET, TOKEN_URL, API_BASE_URL, DISCORD_GUILD_IDS, DISCORD_ADMIN_ROLES, get_rom_hacks, \
    regenerate_htaccess, DISCORD_CHANNEL_HACKS, update_hack, get_rom_hack, get_jam, vote_jam, discord_writes_enabled, \
    get_jams
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
        self._allow_auth_without_hacks = False

    async def get(self, *args, **kwargs):
        try:
            if await self.auth(self._allow_auth_without_hacks):
                await self.do_get(*args, **kwargs)
        except Exception as err:
            self.set_status(500)
            logger.exception(err)
            await self.render("error.html", title="SkyTemple - Internal Server Error",
                              trace=traceback.format_exc(), err=err, **DEFAULT_AUTHOR_DESCRIPTION)

    @abstractmethod
    async def do_get(self, *args, **kwargs):
        pass

    async def auth(self, ignore_no_hacks=False):
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
        self.user_id = None
        super().__init__(application, request, **kwargs)

    async def auth(self, ignore_no_hacks=False):
        if not self.get_secure_cookie('session_id'):
            discord_session = self.make_session(scope=OAUTH_SCOPE)
            authorization_url, state = discord_session.authorization_url(AUTHORIZATION_BASE_URL)
            self.set_cookie('oauth2_state', state)
            self.set_secure_cookie('callback_url', self.request.uri)
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
            self.set_secure_cookie('callback_url', self.request.uri)
            self.redirect(authorization_url, permanent=False)
            return False
        # Only first guild (SkyTemple) supported
        guild: Guild = discord_client.get_guild(DISCORD_GUILD_IDS[0])
        self.user_id = user_id
        member: Member = guild.get_member(int(user_id))
        if not member:
            if ignore_no_hacks:
                return True
            await self.not_authenticated()
            return False

        is_admin = any([r.id in DISCORD_ADMIN_ROLES for r in member.roles])
        role_names = [r.name for r in member.roles if r.name.startswith("Hack")]
        if is_admin:
            self.hack_access = get_rom_hacks(self.db)
        else:
            self.hack_access = get_rom_hacks(self.db, role_names)
        if len(self.hack_access) < 1:
            if ignore_no_hacks:
                return True
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
        return self.redirect(self.get_secure_cookie('callback_url') if self.get_secure_cookie('callback_url') else '/edit')


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
class ListHandler(BaseHandler):
    async def do_get(self, **kwargs):
        jams = get_jams(self.db)
        hacks_pre = get_rom_hacks(self.db, sorted=True)
        hacks = []
        for h in hacks_pre:
            if h['message_id'] is None:
                continue
            h['author'] = get_authors(self.discord_client, h['role_name'], True)
            h['description'] = str(h['description'], 'utf-8').splitlines()
            h['hack_type_printable'] = get_hack_type_str(h["hack_type"])
            h['featured_jams'] = []
            for jam in jams:
                if h['key'] in jam['hacks'].keys():
                    h['featured_jams'].append({
                        'key': jam['key'],
                        'name': jam['motto'],
                        'award': 'none' if 'awards' not in jam else self._get_award(h['key'], jam['awards'])
                    })
            hacks.append(h)
        await self.render('list.html',
                          title=f'SkyTemple Hack Directory',
                          hacks=hacks,
                          **DEFAULT_AUTHOR_DESCRIPTION)

    @staticmethod
    def _get_award(key, awards):
        for x in awards['golden'].values():
            if key in x:
                return 'golden'
        for x in awards['silver'].values():
            if key in x:
                return 'silver'
        for x in awards['bronze'].values():
            if key in x:
                return 'bronze'
        return 'none'

# noinspection PyAbstractClass
class HackEntryHandler(BaseHandler):
    async def do_get(self, **kwargs):
        hack = get_rom_hack(self.db, kwargs['hack_id'])
        if hack and hack['message_id']:
            authors = get_authors(self.discord_client, hack['role_name'], True)
            desc = str(hack['description'], 'utf-8')
            description_lines = desc.splitlines()
            await self.render('hack_entry.html',
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

        if jam is not None:
            if 'voting_enabled' not in jam:
                jam['voting_enabled'] = False
            left = list(jam['hacks'].keys())
            winners = []
            if 'awards' in jam:
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
                if 'awards' in jam:
                    for award, hacks in (jam['awards']['golden'] | jam['awards']['silver'] | jam['awards']['bronze']).items():
                        for ahack in hacks:
                            if ahack == hack:
                                hackdata[hack]['awards'].append(award)
            for dq in jam['dq']:
                member = discord_client.get_user(int(dq['author']))
                dq['author'] = f'{member.name}#{member.discriminator}'
            award_groups = {}
            if 'awards' in jam:
                for award in jam['awards']['golden'].keys():
                    award_groups[award] = 'golden'
                for award in jam['awards']['silver'].keys():
                    award_groups[award] = 'silver'
                for award in jam['awards']['bronze'].keys():
                    award_groups[award] = 'bronze'
            shuffle(left)
            await self.render('jam.html',
                              jam_key=kwargs['jam_key'],
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
class JamVoteHandler(AuthenticatedHandler):
    def __init__(self, application: tornado.web.Application, request: httputil.HTTPServerRequest, **kwargs: any):
        super().__init__(application, request, **kwargs)
        self._allow_auth_without_hacks = True

    async def do_get(self, **kwargs):
        jam = None
        hack = None
        try:
            hack = get_rom_hack(self.db, kwargs['hack_id'])
            jam = get_jam(self.db, kwargs['jam_key'])
        except Exception as ex:
            logger.warning("Jam vote error.", exc_info=ex)

        if jam is not None and 'voting_enabled' in jam and jam['voting_enabled'] and hack is not None:
            try:
                vote_jam(self.db, kwargs['jam_key'], self.user_id, kwargs['hack_id'])
            except:
                logger.error("Jam vote error.", exc_info=ex)
                raise
            await self.render('voted_jam.html',
                              jam_key=kwargs['jam_key'],
                              title=f'SkyTemple Hack Jam - {jam["motto"]} - You voted!',
                              jam=jam,
                              hack=hack,
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

        if discord_writes_enabled():
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
    (r"/", ListHandler, extra),
    (r"/callback/?", CallbackHandler, extra),
    (r"/h/(?P<hack_id>[^\/]+)/?", HackEntryHandler, extra),
    (r"/jam/(?P<jam_key>[^\/]+)/?", JamHandler, extra),
    (r"/jam/(?P<jam_key>[^\/]+)/vote/(?P<hack_id>[^\/]+)/?", JamVoteHandler, extra),
    (r"/edit/?", EditListHandler, extra),
    (r"/edit/(?P<hack_id>[^\/]+)/?", EditFormHandler, extra),
    (r"/translate_hook", TranslateHookHandler, extra),
] + reputation.collect_web_routes(extra)
