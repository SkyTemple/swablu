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
logger = logging.getLogger(__name__)


if 'DISCORD_BOT_USER_TOKEN' not in os.environ:
    raise ValueError("No bot token (env DISCORD_BOT_USER_TOKEN).")
DISCORD_BOT_USER_TOKEN = os.environ['DISCORD_BOT_USER_TOKEN']
if 'DISCORD_GUILD_ID' not in os.environ:
    raise ValueError("No env DISCORD_GUILD_ID.")
DISCORD_GUILD_ID = int(os.environ['DISCORD_GUILD_ID'])
if 'DISCORD_ADMIN_ROLE' not in os.environ:
    raise ValueError("No env DISCORD_ADMIN_ROLE.")
DISCORD_ADMIN_ROLE = int(os.environ['DISCORD_ADMIN_ROLE'])
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


def get_rom_hacks(dbcon, filter=None):
    cursor = dbcon.cursor(dictionary=True)
    if filter is None:
        sql = f"SELECT * FROM `{TABLE_NAME}`"
        cursor.execute(sql)
    else:
        format_strings = ','.join(['%s'] * len(filter))
        sql = f"SELECT * FROM `{TABLE_NAME}` WHERE role_name IN (%s)"
        cursor.execute(sql % format_strings, tuple(filter))
    d = []
    for k in cursor.fetchall():
        d.append(k)
    dbcon.commit()
    cursor.close()
    return d


def get_rom_hack(dbcon, key):
    cursor = dbcon.cursor(dictionary=True)
    sql = f"SELECT * FROM `{TABLE_NAME}` WHERE `key` = %s"
    cursor.execute(sql, (key,))
    d = cursor.fetchone()
    dbcon.commit()
    cursor.close()
    return d


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
          f"`message_id` = %s" \
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
            f.write(f"RedirectMatch 301 (?i)/{hack['key']}/? {BASE_URL}/h/{hack['key']}\n")


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



API_BASE_URL ='https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'


regenerate_htaccess()


def get_template_dir():
    return pkg_resources.resource_filename(__name__, 'tpl')


def get_static_dir():
    return pkg_resources.resource_filename(__name__, 'static')
