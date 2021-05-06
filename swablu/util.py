class MiniCtx:
    def __init__(self, guild, bot, message):
        self.guild = guild
        self.bot = bot
        self.message = message
        self._state = message._state