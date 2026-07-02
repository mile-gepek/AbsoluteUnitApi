import pytest
from httpx import AsyncClient
from httpx import Response as HttpxResponse
from pint import UnitRegistry

from api.app import ConversionResponse
from api.parsing import ParserMode


async def call_convert_endpoint(
    client: AsyncClient,
    input_string: str,
    target_unit: str | None = None,
    mode: ParserMode | None = None,
) -> HttpxResponse:
    params = {
        "input": input_string,
        "target_unit": target_unit,
        "mode": mode,
    }
    params = {key: value for key, value in params.items() if value is not None}
    return await client.get("/convert", params=params)


@pytest.mark.anyio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_conversion_simple(client: AsyncClient, ureg: UnitRegistry):
    response = await call_convert_endpoint(client, "5ft", "cm")
    conversion_response = ConversionResponse(**response.json())
    assert response.status_code == 200
    assert conversion_response.result.units == ureg("cm")


@pytest.mark.anyio
async def test_conversion_simple_infer(client: AsyncClient):
    response = await call_convert_endpoint(client, "5ft")
    conversion_response = ConversionResponse(**response.json())
    assert response.status_code == 200
    assert conversion_response.result.units.dimensionality == "[length]"


@pytest.mark.anyio
async def test_conversion_strict_mode(client: AsyncClient):
    response = await call_convert_endpoint(client, "5ft 6in", mode=ParserMode.Strict)
    conversion_response = ConversionResponse(**response.json())
    assert response.status_code == 200
    assert conversion_response.result.units.dimensionality == "[length] ** 2"


@pytest.mark.anyio
async def test_conversion_adaptive_mode(client: AsyncClient):
    response = await call_convert_endpoint(client, "5ft 6in", mode=ParserMode.Adaptive)
    conversion_response = ConversionResponse(**response.json())
    assert response.status_code == 200
    assert conversion_response.result.units.dimensionality == "[length]"


@pytest.mark.anyio
async def test_conversion_bad_expression(client: AsyncClient):
    response = await call_convert_endpoint(client, "5 / / 3")
    assert response.status_code == 422
