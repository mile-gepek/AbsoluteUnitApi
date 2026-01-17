import asyncio
import enum
import logging
import disnake
from typing import override


class CustomFormatter(logging.Formatter):
    green: str = "\x1b[32;20m"
    blue: str = "\x1b[34;20m"
    yellow: str = "\x1b[33;20m"
    red: str = "\x1b[31;20m"
    bold_red: str = "\x1b[31;1m"
    reset: str = "\x1b[0m"

    format_str: str = (
        f"{red}%(asctime)s{reset} %(name)s [{{}}%(levelname)s{reset}] %(message)s"
    )

    FORMATS: dict[int, str] = {
        logging.DEBUG: format_str.format(green),
        logging.INFO: format_str.format(blue),
        logging.WARNING: format_str.format(yellow),
        logging.ERROR: format_str.format(red),
        logging.CRITICAL: format_str.format(bold_red),
    }

    @override
    def format(self, record: logging.LogRecord):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class LogLevel(enum.Enum):
    INFO = "info"
    DEBUG = "debug"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def to_value(self) -> int:
        return logging._nameToLevel[self.value.upper()]  # pyright: ignore[reportPrivateUsage]


def setup_logging(log_level: LogLevel) -> None:
    level = log_level.to_value()
    logging_formatter = logging.Formatter(
        "%(asctime)s %(name)s [%(levelname)s] %(message)s"
    )

    logger = logging.getLogger("absolute_unit")
    logger.setLevel(level)

    io_handler = logging.StreamHandler()
    io_handler.setFormatter(CustomFormatter())
    logger.addHandler(io_handler)

    handler = logging.FileHandler(
        filename="absolute_unit.log", encoding="utf-8", mode="w"
    )
    handler.setFormatter(logging_formatter)
    logger.addHandler(handler)

    disnake_logger = logging.getLogger("disnake")
    disnake_logger.setLevel(level)

    handler = logging.FileHandler(filename="disnake.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging_formatter)
    disnake_logger.addHandler(handler)


class DisnakeHandler(logging.Handler):
    def __init__(
        self,
        channel: disnake.channel.PartialMessageable,
        loop: asyncio.AbstractEventLoop,
        level: int = logging.WARNING,
    ) -> None:
        self._channel: disnake.channel.PartialMessageable = channel
        self._loop: asyncio.AbstractEventLoop = loop
        super().__init__(level)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        name = record.name
        level_name = record.levelname
        message = f"{name} [{level_name}] {record.getMessage()}"
        _ = self._loop.create_task(self._channel.send(message))
