import sys
from collections.abc import Generator

import pytest
from pint import UnitRegistry
from rich.pretty import pprint

from api.conversion import get_unit_registry
from api.currencies import (
    CurrencyApiResponse,
    clear_currencies,
    clear_ureg_cached_currencies,
    set_ureg_exchange_rates,
)


@pytest.fixture(name="ureg")
def ureg_fixture() -> UnitRegistry:
    return get_unit_registry()


@pytest.fixture(name="currency_ureg")
def currency_ureg_fixture(ureg: UnitRegistry) -> Generator[UnitRegistry]:
    with open("tests/test_currency_data.json", "r") as test_currencies_file:
        mock_currency_data = CurrencyApiResponse.model_validate_json(
            test_currencies_file.read()
        )
        set_ureg_exchange_rates(
            ureg,
            mock_currency_data.base_currency,
            mock_currency_data.exchange_rates_to_base,
        )
    yield ureg
    clear_currencies(ureg, mock_currency_data.base_currency)
    clear_ureg_cached_currencies(ureg)
