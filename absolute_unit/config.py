"""
Configuration module, check the `Config` class for configuration options.
"""

import logging
from pathlib import Path
from typing import Any, ClassVar, Self

import tomlkit
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from result import Err, Ok, Result


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_file=".env")

    bot_token: str
    currency_api_token: str | None = None

    @classmethod
    def from_env(cls) -> Result[Self, ValidationError]:
        try:
            return Ok(cls.model_validate({}))
        except ValidationError as validation_error:
            return Err(validation_error)


class Config(BaseModel):
    test_guild_ids: list[int] | None = None

    mod_role_ids: list[int] = Field([])
    admin_role_ids: list[int] = []

    # cooldown length in seconds
    cooldown_duration: float = 5

    path: Path = Field(Path("config.toml"), exclude=True)

    @property
    def testing_mode(self) -> bool:
        return self.test_guild_ids is not None

    @classmethod
    def default_config(cls) -> Result[Self, ValidationError]:
        """
        Returns the default config.
        """
        return Ok(cls.model_validate({}))

    @classmethod
    def _create_config(
        cls,
        path: Path,
        data: dict[str, Any],  # pyright: ignore[reportExplicitAny]
    ) -> Result[Self, ValidationError]:
        data["path"] = path
        try:
            return Ok(cls.model_validate(data))
        except ValidationError as validation_error:
            return Err(validation_error)

    @classmethod
    def get_config(cls, path: Path | None = None) -> Result[Self, ValidationError]:
        """Load the config from the given, or "config.toml" by default."""
        if path is None:
            path = Path("config.toml")
        try:
            with path.open("r") as config_file:
                data: dict[str, Any] = dict(tomlkit.load(config_file))  # pyright: ignore[reportExplicitAny]
        except FileNotFoundError:
            logger.info("config.toml file does not exist, using default config.")
            return cls.default_config()
        return cls._create_config(path, data)

    def write(self) -> None:
        data = self.model_dump(
            exclude_none=True,
            exclude_unset=True,
        )
        with self.path.open("w") as config_file:
            tomlkit.dump(data, config_file)  # pyright: ignore[reportUnknownMemberType]
