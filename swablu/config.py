import json
import logging
import os
from time import sleep

import discord
import pkg_resources
import mysql.connector
from mysql.connector import MySQLConnection

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.guild_messages = True
discord_client = discord.Client(intents=intents)
TABLE_NAME = 'rom_hacks'
TABLE_NAME_REPUTATION = 'rep'
TABLE_NAME_JAM = 'jam'
TABLE_NAME_JAM_VOTES = 'jam_votes'
logger = logging.getLogger(__name__)


if 'DISCORD_BOT_USER_TOKEN' not in os.environ:
    raise ValueError("No bot token (env DISCORD_BOT_USER_TOKEN).")
DISCORD_BOT_USER_TOKEN = os.environ['DISCORD_BOT_USER_TOKEN']
if 'DISCORD_GUILD_ID' not in os.environ:
    raise ValueError("No env DISCORD_GUILD_ID.")
DISCORD_GUILD_IDS = [int(x) for x in os.environ['DISCORD_GUILD_ID'].split(',')]
if 'DISCORD_ADMIN_ROLE' not in os.environ:
    raise ValueError("No env DISCORD_ADMIN_ROLE.")
DISCORD_ADMIN_ROLES = [int(x) for x in os.environ['DISCORD_ADMIN_ROLE'].split(',')]
if 'DISCORD_CHANNEL_HACKS' not in os.environ:
    raise ValueError("No env DISCORD_CHANNEL_HACKS.")
DISCORD_CHANNEL_HACKS = int(os.environ['DISCORD_CHANNEL_HACKS'])
if 'PORT' not in os.environ:
    raise ValueError("No env PORT.")
PORT = os.environ['PORT']
if 'OAUTH2_CLIENT_ID' not in os.environ:
    raise ValueError("No env OAUTH2_CLIENT_ID.")
OAUTH2_CLIENT_ID = os.environ['OAUTH2_CLIENT_ID']
if 'OAUTH2_CLIENT_SECRET' not in os.environ:
    raise ValueError("No env OAUTH2_CLIENT_SECRET.")
OAUTH2_CLIENT_SECRET = os.environ['OAUTH2_CLIENT_SECRET']
if 'OAUTH2_REDIRECT_URI' not in os.environ:
    raise ValueError("No env OAUTH2_REDIRECT_URI.")
OAUTH2_REDIRECT_URI = os.environ['OAUTH2_REDIRECT_URI']
if 'COOKIE_SECRET' not in os.environ:
    raise ValueError("No env COOKIE_SECRET.")
COOKIE_SECRET = os.environ['COOKIE_SECRET']
if 'MANAGED_HTACCESS_FILE' not in os.environ:
    raise ValueError("No env MANAGED_HTACCESS_FILE.")
MANAGED_HTACCESS_FILE = os.environ['MANAGED_HTACCESS_FILE']
if 'BASE_URL' not in os.environ:
    raise ValueError("No env MANAGED_HTACCESS_FILE.")
BASE_URL = os.environ['BASE_URL']


def check_table_exists(dbcon, tablename):
    dbcur = dbcon.cursor()
    dbcur.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = '{0}'
        """.format(tablename.replace('\'', '\'\'')))
    if dbcur.fetchone()[0] == 1:
        dbcur.close()
        return True


def get_rom_hacks(dbcon, filter=None, sorted=False):
    cursor = dbcon.cursor(dictionary=True, buffered=True)
    if filter is None:
        sql = f"SELECT * FROM `{TABLE_NAME}`"
        if sorted:
            sql += f" ORDER BY date_updated DESC, name ASC"
        cursor.execute(sql)
    else:
        if len(filter) < 1:
            cursor.close()
            return []
        format_strings = ','.join(['%s'] * len(filter))
        sql = f"SELECT * FROM `{TABLE_NAME}` WHERE role_name IN (%s)"
        if sorted:
            sql += f" ORDER BY date_updated DESC, name DESC"
        cursor.execute(sql % format_strings, tuple(filter))
    d = []
    for k in cursor.fetchall():
        d.append(k)
    dbcon.commit()
    cursor.close()
    return d


def get_rom_hack(dbcon, key):
    cursor = dbcon.cursor(dictionary=True, buffered=True)
    sql = f"SELECT * FROM `{TABLE_NAME}` WHERE `key` = %s"
    cursor.execute(sql, (key,))
    d = cursor.fetchone()
    dbcon.commit()
    cursor.close()
    return d


def get_rom_hack_img(dbcon, key, id):
    field = None
    if int(id) == 1:
        field = 'screenshot1'
    elif int(id) == 2:
        field = 'screenshot2'
    if field:
        cursor = dbcon.cursor(dictionary=True, buffered=True)
        sql = f"SELECT `{field}` FROM `{TABLE_NAME}` WHERE `key` = %s"
        cursor.execute(sql, (key,))
        d = cursor.fetchone()
        dbcon.commit()
        cursor.close()
        v = d[field]
        if v != 'None':
            return v
    return None


def get_jams(dbcon):
    cursor = dbcon.cursor(dictionary=True, buffered=True)
    sql = f"SELECT * FROM `{TABLE_NAME_JAM}`"
    cursor.execute(sql)
    rows = []
    for k in cursor.fetchall():
        d = json.loads(k['config'])
        d['key'] = k['key']
        rows.append(d)
    dbcon.commit()
    cursor.close()
    return rows


def get_jam(dbcon, key):
    cursor = dbcon.cursor(dictionary=True, buffered=True)
    sql = f"SELECT * FROM `{TABLE_NAME_JAM}` WHERE `key` = %s"
    cursor.execute(sql, (key,))
    d = cursor.fetchone()
    dbcon.commit()
    cursor.close()
    return json.loads(d['config'])


def create_jam(dbcon, jam_key, config):
    cursor = dbcon.cursor()
    sql = f"INSERT INTO {TABLE_NAME_JAM} (`key`, `config`) VALUES(%s, %s)"
    cursor.execute(sql, (
        jam_key, config,
    ))
    dbcon.commit()
    cursor.close()


def update_jam(dbcon, jam_key, config):
    cursor = dbcon.cursor()
    sql = f"UPDATE {TABLE_NAME_JAM} SET `config` = %s WHERE `key` = %s"
    cursor.execute(sql, (
        config, jam_key,
    ))
    dbcon.commit()
    cursor.close()


def vote_jam(dbcon, jam_key, user_id, hack):
    cursor = dbcon.cursor()
    sql = f"INSERT INTO {TABLE_NAME_JAM_VOTES} (user_id, jam, hack) VALUES(%s, %s, %s) ON DUPLICATE KEY UPDATE hack=%s"
    cursor.execute(sql, (
        user_id, jam_key, hack, hack
    ))
    dbcon.commit()
    cursor.close()


def update_hack(dbcon, hack):
    cursor = dbcon.cursor()
    sql = f"UPDATE `{TABLE_NAME}` SET " \
          f"`name` = %s," \
          f"`description` = %s," \
          f"`screenshot1` = %s," \
          f"`screenshot2` = %s," \
          f"`url_main` = %s," \
          f"`url_discord` = %s," \
          f"`url_download` = %s," \
          f"`video` = %s," \
          f"`hack_type` = %s," \
          f"`message_id` = %s," \
          f"`date_updated` = NOW()" \
          f" WHERE id = %s"
    cursor.execute(sql, (
        hack['name'],
        hack['description'],
        hack['screenshot1'],
        hack['screenshot2'],
        hack['url_main'],
        hack['url_discord'],
        hack['url_download'],
        hack['video'],
        hack['hack_type'],
        hack['message_id'],
        hack['id']
    ))
    dbcon.commit()
    cursor.close()


def regenerate_htaccess():
    logger.info("Regenerating htaccess...")
    with open(MANAGED_HTACCESS_FILE, 'w') as f:
        for hack in get_rom_hacks(database):
            f.write(f"RedirectMatch 301 (?i)/{hack['key']}$/? {BASE_URL}/h/{hack['key']}\n")


logger.info("Connect to DB...")
database = None
while database is None:
    try:
        database: MySQLConnection = mysql.connector.connect(user=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'],
                                                            host=os.environ['MYSQL_HOST'], port=os.environ['MYSQL_PORT'],
                                                            database=os.environ['MYSQL_DATABASE'])
    except Exception as ex:
        logger.warning("Connecting failed. Retrying...", exc_info=ex)
        sleep(5)

if not check_table_exists(database, TABLE_NAME):
    dbcur = database.cursor()
    logger.info("Creating hacks table...")
    # Could surely be optimized, but fine for now.
    dbcur.execute(f"""
    CREATE TABLE `{TABLE_NAME}` (
        `id` INT(10) unsigned NOT NULL AUTO_INCREMENT,
        `key` VARCHAR(80) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
        `name` VARCHAR(100) CHARACTER SET utf8 COLLATE utf8_bin,
        `description` TEXT CHARACTER SET utf8 COLLATE utf8_bin,
        `screenshot1` LONGTEXT CHARACTER SET ascii,
        `screenshot2` LONGTEXT CHARACTER SET ascii,
        `url_main` VARCHAR(200) CHARACTER SET utf8 COLLATE utf8_bin,
        `url_discord` VARCHAR(200) CHARACTER SET utf8 COLLATE utf8_bin,
        `url_download` VARCHAR(200) CHARACTER SET utf8 COLLATE utf8_bin,
        `video` VARCHAR(100) CHARACTER SET utf8 COLLATE utf8_bin,
        `hack_type` VARCHAR(32) CHARACTER SET utf8 COLLATE utf8_bin,
        `role_name` VARCHAR(60) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
        `message_id` BIGINT(30) unsigned,
        PRIMARY KEY (`id`),
        INDEX (`role_name`),
        INDEX (`key`)
    );
    """)
    dbcur.close()
else:
    logger.info("Hacks table existed!")

if not check_table_exists(database, TABLE_NAME_REPUTATION):
    dbcur = database.cursor()
    logger.info("Creating reputation table...")
    # Could surely be optimized, but fine for now.
    dbcur.execute(f"""
    CREATE TABLE `{TABLE_NAME_REPUTATION}` (
        `discord_id` BIGINT(30) unsigned NOT NULL,
        `points` INT(20) signed NOT NULL,
        PRIMARY KEY (`discord_id`)
    );
    """)
    dbcur.close()
else:
    logger.info("Reputation table existed!")

if not check_table_exists(database, TABLE_NAME_JAM):
    dbcur = database.cursor()
    logger.info("Creating jam table...")
    dbcur.execute(f"""
    CREATE TABLE `{TABLE_NAME_JAM}` (
        `id` INT(10) unsigned NOT NULL AUTO_INCREMENT,
        `key` VARCHAR(80) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
        `config` TEXT CHARACTER SET utf8 COLLATE utf8_bin,
        PRIMARY KEY (`id`)
    );
    """)
    dbcur.close()
else:
    logger.info("Jam table existed!")

if not check_table_exists(database, TABLE_NAME_JAM_VOTES):
    dbcur = database.cursor()
    logger.info("Creating jam votes table...")
    dbcur.execute(f"""
    CREATE TABLE `{TABLE_NAME_JAM_VOTES}` (
        `user_id` BIGINT(30) unsigned,
        `jam` VARCHAR(80) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
        `hack` VARCHAR(80) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
        PRIMARY KEY (`user_id`, `jam`)
    );
    """)
    dbcur.close()
else:
    logger.info("Jam votes table existed!")

API_BASE_URL ='https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'


regenerate_htaccess()


def discord_writes_enabled():
    return bool(int(os.getenv('ENABLE_DISCORD_WRITES', "0")))


def get_template_dir():
    return pkg_resources.resource_filename(__name__, 'tpl')


def get_static_dir():
    return pkg_resources.resource_filename(__name__, 'static')
