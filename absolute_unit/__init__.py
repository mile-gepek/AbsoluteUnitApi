import logging

from pint import UnitRegistry


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename="absolute_unit.log", encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

disnake_logger = logging.getLogger("disnake")
disnake_logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename="disnake.log", encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
disnake_logger.addHandler(handler)
_ = logging.getLogger(__name__)


ureg = UnitRegistry()
