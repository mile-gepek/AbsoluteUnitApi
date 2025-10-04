import os
from typing import Self

from dotenv import load_dotenv
from result import Err, Ok, Result

_ = load_dotenv()


class ConfigError(Exception): ...


class MissingBotTokenError(ConfigError):
    def __init__(self, *args: object) -> None:
        super().__init__("Missing DISCORD_APPLICATION_TOKEN key in config")


class Config:
    __config: Self | None = None

    def __init__(self, bot_token: str, test_guilds: list[int] | None) -> None:
        self.bot_token: str = bot_token
        self.test_guilds: list[int] | None = test_guilds

    @property
    def ephemeral_errors(self) -> bool:
        return self.test_guilds is None

    @classmethod
    def get_config(cls) -> Result[Self, ConfigError]:
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
        bot_token = os.getenv("DISCORD_APPLICATION_TOKEN")
        if bot_token is None:
            return Err(MissingBotTokenError())

        test_guilds = os.getenv("TEST_GUILD_ID")
        if test_guilds is not None:
            test_guilds = [int(test_guilds)]

        return Ok((bot_token, test_guilds))
