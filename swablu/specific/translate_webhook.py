import json
import logging

import tornado.web
import tornado.escape
from discord import Client, TextChannel, Embed, Colour

CHANNEL_ID = 813057591608999957
logger = logging.getLogger(__name__)


# noinspection PyAttributeOutsideInit,PyAbstractClass
class TranslateHookHandler(tornado.web.RequestHandler):
    def initialize(self, discord_client: Client, *args, **kwargs):
        self.discord_client: Client = discord_client
        self.channel: TextChannel = self.discord_client.get_channel(CHANNEL_ID)

    async def post(self, *args, **kwargs):
        hook_data = tornado.escape.json_decode(self.request.body)
        logger.info(hook_data)
        count_added = 0
        count_updated = 0
        count_removed = 0
        description = ""
        if not isinstance(hook_data, list):
            hook_data = [hook_data]
        for hook in hook_data:
            if hook["event"] == "string.added":
                count_added += 1
            elif hook["event"] == "string.updated":
                count_updated += 1
            elif hook["event"] == "string.deleted":
                count_removed += 1

        if count_added > 0:
            description += f"{count_added} strings added.\n"
        if count_updated > 0:
            description += f"{count_updated} strings updated.\n"
        if count_removed > 0:
            description += f"{count_removed} strings removed.\n"

        if count_added + count_updated > 0:
            embed = Embed(
                title="Crowdin",
                description=description,
                url="https://translate.skytemple.org",
                colour=Colour.dark_green()
            )
            embed.set_author(name="Crowdin", url="https://translate.skytemple.org", icon_url="https://skytemple.org/crowdin.png")
            await self.channel.send("New Crowdin string updates.", embed=embed)
        return self.write(f"ok.\n{description}\n{json.dumps(hook_data)}")