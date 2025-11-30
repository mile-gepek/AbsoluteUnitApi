import logging
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


logging_formatter = logging.Formatter(
    "%(asctime)s %(name)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

io_handler = logging.StreamHandler()
io_handler.setFormatter(CustomFormatter())
logger.addHandler(io_handler)

handler = logging.FileHandler(filename="absolute_unit.log", encoding="utf-8", mode="w")
handler.setFormatter(logging_formatter)
logger.addHandler(handler)


disnake_logger = logging.getLogger("disnake")
disnake_logger.setLevel(logging.DEBUG)

handler = logging.FileHandler(filename="disnake.log", encoding="utf-8", mode="w")
handler.setFormatter(logging_formatter)
disnake_logger.addHandler(handler)
