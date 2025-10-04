"""
Configuration module, check the `Config` class for configuration options.
"""

import os
from typing import Self

from dotenv import load_dotenv
from result import Err, Ok, Result

_ = load_dotenv()


class ConfigError(Exception): ...


class MissingConfigKeyError(ConfigError):
    def __init__(self, key_name: str) -> None:
        super().__init__(f"Missing {key_name} key in config")


class Config:
    """
    Singleton class for all config, use the `get_config` method to get a config.

    Options
    -------
    - DISCORD_APPLICATION_TOKEN `str`
        - The token for the discord bot.

    - TEST_GUILD_ID: `Optional[int]`
        - ID of the guild used for testing.
        - If  the ID is present, only cooldown messages will be ephemeral, all other errors will not.
    """

    __config: Self | None = None

    def __init__(self, bot_token: str, test_guilds: list[int] | None) -> None:
        self.bot_token: str = bot_token
        self.test_guilds: list[int] | None = test_guilds

    @property
    def ephemeral_errors(self) -> bool:
        return self.test_guilds is None

    @classmethod
    def get_config(cls) -> Result[Self, ConfigError]:
        """Gets the existing config or loads it."""
        if cls.__config is not None:
            return Ok(cls.__config)

        config = cls.load_config()
        if isinstance(config, Err):
            return config
        new = cls(*config.ok())
        cls.__config = new
        return Ok(new)

    @staticmethod
    def load_config() -> Result[tuple[str, list[int] | None], ConfigError]:
        """Load all the options from the file."""
        bot_token = os.getenv("DISCORD_APPLICATION_TOKEN")
        if bot_token is None:
            return Err(MissingConfigKeyError("DISCORD_APPLICATION_TOKEN"))

        test_guilds = os.getenv("TEST_GUILD_ID")
        if test_guilds is not None:
            test_guilds = [int(test_guilds)]

        return Ok((bot_token, test_guilds))
