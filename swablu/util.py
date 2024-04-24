from enum import Enum


class MiniCtx:
    def __init__(self, guild, bot, message):
        self.guild = guild
        self.bot = bot
        self.message = message
        self._state = message._state


class VotingAllowedStatus(Enum):
    """
    Used to represent whether a user is allowed to vote on a jam or not and why
    """
    ALLOWED = 0,
    NOT_ALLOWED_CLOSED = 1,
    NOT_ALLOWED_JURY = 2
