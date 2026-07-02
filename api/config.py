import enum
import tomllib
from enum import StrEnum
from typing import Annotated, Self

from fastapi import Depends
from pydantic import BaseModel, BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    currency_api_token: str | None = None


class LogLevel(StrEnum):
    CRITICAL = enum.auto()
    FATAL = enum.auto()
    ERROR = enum.auto()
    WARNING = enum.auto()
    WARN = enum.auto()
    INFO = enum.auto()
    DEBUG = enum.auto()
    NOTSET = enum.auto()

    def has_debug(self) -> bool:
        return self in (self.DEBUG, self.NOTSET)


class LoggingConfig(BaseModel):
    level: Annotated[LogLevel, BeforeValidator(str.lower)] = LogLevel.INFO


class Config(BaseModel):
    debug: bool = False

    logging: LoggingConfig

    @classmethod
    def get_config(cls, path="config.toml") -> Self:
        with open(path, "rb") as config_file:
            values = tomllib.load(config_file)
            return cls.model_validate(values)


config = Config.get_config()
secrets = Secrets()  # ty:ignore[missing-argument]


def get_config() -> Config:
    return config


def get_secrets() -> Secrets:
    return secrets


ConfigDep = Annotated[Config, Depends(get_config)]
SecretsDep = Annotated[Secrets, Depends(get_secrets)]
