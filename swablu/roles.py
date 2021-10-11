import logging

from discord import Member, Role, BaseActivity, Guild

from swablu.config import discord_client, DISCORD_GUILD_IDS

skytemple_app_id = 736538698719690814
dreamnexus_app_id = 897109434893991976
logger = logging.getLogger(__name__)


async def check_for(member: Member, role: Role, app_id):
    if role is None:
        return
    should = False
    for activity in member.activities:
        activity: BaseActivity
        if hasattr(activity, 'application_id') and activity.application_id == app_id:
            should = True
    logger.info(f'[{member.guild.name}] {member.display_name}? {should}')
    if should and role not in member.roles:
        await member.add_roles(role)
    elif not should and role in member.roles:
        await member.remove_roles(role)


def get_role(guild: Guild, role_name: str):
    for candidate in guild.roles:
        candidate: Role
        if candidate.name == role_name:
            return candidate
    return None


async def scan_roles():
    logger.info("Periodic scan.")
    # Only first guild (SkyTemple) and second guild (DreamNexus) supported
    guild: Guild = discord_client.get_guild(DISCORD_GUILD_IDS[0])
    r = get_role(guild, "Using SkyTemple")
    for m in guild.members:
        await check_for(m, r, skytemple_app_id)
    guild: Guild = discord_client.get_guild(DISCORD_GUILD_IDS[1])
    r = get_role(guild, "Using DreamNexus")
    for m in guild.members:
        await check_for(m, r, dreamnexus_app_id)
    logger.info("Periodic scan complete.")


def get_hack_type_str(hack_type):
    if hack_type == "balance_hack_wip":
        return "Balance Hack (work in progress)"
    if hack_type == "balance_hack_demo":
        return "Balance Hack (with demo)"
    if hack_type == "balance_hack_mostly":
        return "Balance Hack (mostly finished)"
    if hack_type == "balance_hack":
        return "Balance Hack (finished)"
    if hack_type == "story_hack_wip":
        return "Story Hack (work in progress)"
    if hack_type == "story_hack_demo":
        return "Story Hack (with demo)"
    if hack_type == "story_hack_mostly":
        return "Story Hack (mostly finished)"
    if hack_type == "story_hack":
        return "Story Hack (finished)"
    if hack_type == "translation_wip":
        return "Translation (work in progress)"
    if hack_type == "translation_demo":
        return "Translation (with demo)"
    if hack_type == "translation_mostly":
        return "Translation (mostly finished)"
    if hack_type == "translation":
        return "Translation (finished)"
    if hack_type == "misc_hack_wip":
        return "Misc. Hack (work in progress)"
    if hack_type == "misc_hack_demo":
        return "Misc. Hack (with demo)"
    if hack_type == "misc_hack_mostly":
        return "Misc. Hack (mostly finished)"
    if hack_type == "misc_hack":
        return "Misc. Hack (finished)"
    if hack_type == "machinima_ongoing":
        return "Machinima (ongoing)"
    if hack_type == "machinima":
        return "Machinima (finished)"
    return "Misc. Hack"
