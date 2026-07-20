import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Annotated, Any

from httpx2 import AsyncClient
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

midnight = time(0, 0, 0)


def clear_ureg_cached_currencies(ureg: UnitRegistry) -> None:
    """
    The current version of pint has a bug where redefining units does not clear their cached ratios.

    This is a problem for currencies as they have to be redefined because of variable exchange rates.
    """
    # ureg should have a cache, but whatever
    if not hasattr(ureg, "_cache"):
        return
    cache = ureg._cache
    invalid_root_unit_keys: set[UnitsContainer] = set()
    for dimension, units in cache.dimensional_equivalents.items():
        if isinstance(dimension, UnitsContainer) and "currency" in dimension:
            invalid_root_unit_keys |= set(units)
    for unit_container in invalid_root_unit_keys:
        del cache.root_units[unit_container]

    invalid_conversion_keys: set[tuple[UnitsContainer, UnitsContainer]] = set()
    for dimension in cache.conversion_factor:
        left, right = dimension
        if left in invalid_root_unit_keys or right in invalid_root_unit_keys:
            invalid_conversion_keys.add(dimension)
    for unit_container in invalid_conversion_keys:
        del cache.conversion_factor[unit_container]


def clear_currencies(ureg: UnitRegistry, base_currency: str):
    """
    If the api removes certain currencies they will be left in the registry.
    This is potentially invalid if a currency's old exchange rate is still stored, but the API doesn't update it.
    """
    units = ureg._units
    currency_list = []
    for name, definition in units.items():
        if (
            definition.reference in ("[currency]", base_currency)
            and name not in currency_list
        ):
            currency_list.append(name)
    for currency in currency_list:
        del units[currency]


def extract_exchange_rates(currencies: dict[str, Any]) -> dict[str, float]:
    # The data that currencyapi.com gives is stupid.
    # Example: `{"USD": {"code": "USD", value: 0.789}}`
    # why is this a thing
    for currency in currencies:
        currencies[currency] = currencies[currency]["value"]
    return currencies


class CurrencyApiResponse(BaseModel):
    last_updated_at: datetime = Field(
        validation_alias=AliasPath("meta", "last_updated_at")
    )
    exchange_rates_to_base: Annotated[
        dict[str, float], BeforeValidator(extract_exchange_rates)
    ] = Field(alias="data")
    base_currency: str


async def get_exchange_rates(
    client: AsyncClient, base_currency: str
) -> CurrencyApiResponse | None:
    params = {"base_currency": base_currency}
    response = await client.get("latest", params=params)
    if response.status_code != 200:
        logger.warning(response.reason_phrase)
        return
    resp_json = response.json()

    try:
        response_model = CurrencyApiResponse.model_validate(resp_json)
        return response_model
    except ValidationError as e:
        logger.info(f'Call to currencyapi endpoint "latest" is missing key: "{e}"')


def set_ureg_exchange_rates(
    ureg: UnitRegistry,
    base_currency: str,
    exchange_rates: dict[str, float],
):
    ureg.define(
        f"{base_currency.upper()} = [currency] = {base_currency.capitalize()} = {base_currency.lower()}"
    )
    for currency, ratio_to_base in exchange_rates.items():
        if currency != base_currency:
            ureg.define(
                f"{currency.upper()} = {ratio_to_base} * {base_currency} = {currency.capitalize()} = {currency.lower()}"
            )


def seconds_until_midnight() -> float:
    now = datetime.now()
    target = datetime.combine(now.date(), midnight)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


class CurrencyHandler:
    last_currency_update: datetime

    def start_currency_task(
        self,
        currencyapi_token: str,
        ureg: UnitRegistry,
        base_currency: str = "EUR",
    ) -> asyncio.Task[None]:
        async def current_task_impl():
            async with AsyncClient(
                base_url="https://api.currencyapi.com/v3",
                headers={"apikey": currencyapi_token},
            ) as client:
                while True:
                    response = await client.get(
                        "/latest",
                        params={"base_currency": base_currency},
                    )
                    if response.status_code != 200:
                        clear_ureg_cached_currencies(ureg)

                    validated_response = CurrencyApiResponse(
                        **response.json(), base_currency=base_currency
                    )
                    clear_currencies(ureg, base_currency)
                    clear_ureg_cached_currencies(ureg)
                    set_ureg_exchange_rates(
                        ureg, base_currency, validated_response.exchange_rates_to_base
                    )
                    self.last_currency_update = validated_response.last_updated_at

                    await asyncio.sleep(seconds_until_midnight())

        task = asyncio.create_task(current_task_impl())
        return task
