from asyncio import Task
from collections.abc import Sequence
from datetime import datetime
import logging
from typing import Annotated, Any

from aiohttp import ClientSession
import disnake
from disnake.ext import commands, tasks
from pint import UnitRegistry
from pint.util import UnitsContainer
from pydantic import (
    AliasPath,
    BaseModel,
    BeforeValidator,
    Field,
    ValidationError,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def clear_ureg_cache(ureg: UnitRegistry, units: Sequence[str]) -> None:
    """
    The current version of pint has a bug where redefining units does not clear their cached ratios.

    This is a problem for currencies as they have to be redefined because of variable exchange rates.
    """
    # ureg should have a cache, but whatever
    if not hasattr(ureg, "_cache"):
        return
    cache = ureg._cache  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportPrivateUsage]
    for unit in units:
        invalid_root_unit_keys: list[UnitsContainer] = []
        for key in cache.root_units:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(key, UnitsContainer) and unit in key:
                invalid_root_unit_keys.append(key)
        for unit_container in invalid_root_unit_keys:
            del cache.root_units[unit_container]  # pyright: ignore[reportUnknownMemberType]

        invalid_conversion_keys: list[tuple[UnitsContainer, UnitsContainer]] = []
        for key in cache.conversion_factor:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            left, right = key  # pyright: ignore[reportUnknownVariableType]
            if unit in left or unit in right:
                invalid_conversion_keys.append(key)  # pyright: ignore[reportUnknownArgumentType]
        for unit_container in invalid_conversion_keys:
            del cache.conversion_factor[unit_container]  # pyright: ignore[reportUnknownMemberType]


def clear_currencies(ureg: UnitRegistry):
    """
    If the api removes certain currencies they will be left in the registry.
    This is potentially invalid if a currency's old exchange rate is still stored, but the API doesn't update it.
    """
    units = ureg._units  # pyright: ignore[reportPrivateUsage]
    currency_list = [
        name
        for name, definition in units.items()
        if definition.reference == "[currency]"
    ]
    for currency in currency_list:
        del units[currency]


def get_exchange_rate_validator(value: dict[str, Any]) -> dict[str, float]:  # pyright: ignore[reportExplicitAny]
    for k in value:
        value[k] = value[k]["value"]
    return value


class CurrencyApiResponse(BaseModel):
    last_updated_at: datetime = Field(
        validation_alias=AliasPath("meta", "last_updated_at")
    )
    data: Annotated[dict[str, float], BeforeValidator(get_exchange_rate_validator)]


async def get_exchange_rates(
    currencyapi_session: ClientSession, base_currency: str
) -> CurrencyApiResponse | None:
    async with currencyapi_session as session:
        params = {"base_currency": base_currency}
        async with session.get("latest", params=params) as resp:
            if resp.status != 200:
                logger.warning(resp.reason)
                return
            resp_json = await resp.json()  # pyright: ignore[reportAny]

    try:
        response_model = CurrencyApiResponse.model_validate(resp_json)
        return response_model
    except ValidationError as e:
        logger.info(f'Call to currencyapi endpoint "latest" is missing key: "{e}"')


def define_exchange_rates(
    ureg: UnitRegistry, base_currency: str, exchange_rates: dict[str, float]
) -> None:
    clear_ureg_cache(ureg, tuple(exchange_rates.keys()))
    clear_currencies(ureg)
    ureg.define(f"{base_currency} = [currency] = {base_currency.lower()}")
    for currency, exchange_rate in exchange_rates.items():
        if currency == base_currency:
            continue
        if currency in ureg or currency.lower() in ureg:
            continue
        ureg.define(
            f"{currency} = {exchange_rate} * {base_currency} = {currency.lower()}"
        )


class CurrencyCog(commands.Cog):
    def __init__(
        self,
        disnake_client: disnake.Client,
        api_key: str,
        ureg: UnitRegistry,
        # euros because Europe is better
        base_currency: str = "EUR",
    ):
        self._disnake_client: disnake.Client = disnake_client
        self._api_key: str = api_key
        self._last_refresh_datetime: datetime | None = None
        self._ureg: UnitRegistry = ureg
        self.base_currency: str = base_currency
        headers = {"apikey": api_key}
        self.currencyapi_session: ClientSession = ClientSession(
            loop=disnake_client.loop,
            base_url="https://api.currencyapi.com/v3/",
            headers=headers,
        )
        logger.info("Starting currency exchange rate refresh task.")
        self.refresh_task: Task[None] = self.refresh_currency_exchange_rates.start()

    @property
    def last_refresh_datetime(self) -> datetime | None:
        return self._last_refresh_datetime

    @tasks.loop(hours=24)
    async def refresh_currency_exchange_rates(self) -> None:
        response = await get_exchange_rates(
            self.currencyapi_session,
            self.base_currency,
        )
        if response is None:
            return
        self._last_refresh_datetime = response.last_updated_at
        define_exchange_rates(self._ureg, self.base_currency, response.data)

    @refresh_currency_exchange_rates.before_loop
    async def before(self) -> None:
        await self._disnake_client.wait_until_ready()
