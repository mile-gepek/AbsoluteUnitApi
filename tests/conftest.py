import pytest
from pint import UnitRegistry

from api.conversion import get_unit_registry


@pytest.fixture(name="ureg")
def ureg_fixture() -> UnitRegistry:
    return get_unit_registry()
