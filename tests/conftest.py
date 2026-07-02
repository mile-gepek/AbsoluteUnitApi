from collections.abc import AsyncGenerator

import pytest
from pint import UnitRegistry

from api.conversion import get_unit_registry


@pytest.fixture(name="ureg")
async def ureg_fixture() -> AsyncGenerator[UnitRegistry]:
    yield get_unit_registry()
