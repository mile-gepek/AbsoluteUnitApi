import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Query, Request, Response, status
from fastapi.concurrency import asynccontextmanager
from pint.facets.plain import PlainQuantity, PlainUnit
from pint.util import UnitsContainer
from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer
from pytest_asyncio.plugin import AsyncGenerator
from result import Err
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT

from api import conversion
from api.config import get_secrets
from api.conversion import (
    get_unit_registry,
    has_different_currencies,
)
from api.currencies import CurrencyHandler
from api.errors import BaseError
from api.parsing import ParserMode

logger = logging.getLogger(__name__)


currency_handler = CurrencyHandler()


class ConversionExceptionGroup(ExceptionGroup):
    def __init__(self, message: str, errors: list[BaseError]) -> None:
        super().__init__(message, errors)
        self.errors = errors


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    secrets = get_secrets()
    ureg = get_unit_registry()

    if secrets.currency_api_token is not None:
        task = currency_handler.start_currency_task(secrets.currency_api_token, ureg)
        yield
    task.cancel()


app = FastAPI(title="Absolute Unit API", root_path="/api/v1", lifespan=lifespan)


@app.exception_handler(ConversionExceptionGroup)
async def handle_convert_exception_group(
    request: Request, exceptions: ConversionExceptionGroup
) -> dict[str, list[dict[str, str]]]:
    errors = [exception.json() for exception in exceptions.errors]
    return {"errors": errors}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime = Field(default_factory=utc_now)


@app.get("/health")
async def health() -> HealthResponse:
    return HealthResponse()


def validate_units(value: str | PlainUnit) -> PlainUnit:
    if isinstance(value, PlainUnit):
        return value
    ureg = get_unit_registry()
    return ureg(value).units


class QuantityWrapper(BaseModel, arbitrary_types_allowed=True):
    magnitude: float
    units: Annotated[PlainUnit, PlainSerializer(str), BeforeValidator(validate_units)]


class ConversionResponse(BaseModel):
    result: QuantityWrapper
    input_interpretation: str
    last_currency_update: datetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    input_unit_same_as_target: bool = Field(
        exclude_if=lambda value: value is None
    )  # Exclude field if False


@app.get("/convert")
async def convert(
    response: Response,
    ureg: conversion.UnitRegistryDep,
    user_input: str = Query(alias="input"),
    target_unit: str | None = None,
    mode: ParserMode = ParserMode.Strict,
) -> ConversionResponse:
    errors = []

    async with asyncio.timeout(2):
        try:
            expression_result = conversion.parse_input(
                user_input,
                ureg,
                mode,
            )
        except TimeoutError:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            raise

    if isinstance(expression_result, Err):
        errors.extend(expression_result.err())
        if target_unit is not None:
            target_unit_result = conversion.get_target_unit(
                target_unit,
                ureg,
            )
            if isinstance(target_unit_result, Err):
                error = target_unit_result.err()
                errors.append(error)
        response.status_code = HTTP_422_UNPROCESSABLE_CONTENT
        raise ConversionExceptionGroup("Errors", errors)

    expression = expression_result.ok()

    evaluation_result = conversion.evaluate_expression(expression, ureg)
    if isinstance(evaluation_result, Err):
        errors.extend(evaluation_result.err())
        if target_unit is not None:
            target_unit_result = conversion.get_target_unit(
                target_unit,
                ureg,
            )
            if isinstance(target_unit_result, Err):
                error = target_unit_result.err()
                errors.append(error)
        response.status_code = HTTP_422_UNPROCESSABLE_CONTENT
        raise ConversionExceptionGroup("Errors", errors)

    evaluated: PlainQuantity[float] = evaluation_result.ok().to_reduced_units()

    if target_unit is None:
        target_unit_result = conversion.infer_target_unit(evaluated, ureg)
    else:
        target_unit_result = conversion.get_target_unit(target_unit, ureg)

    if isinstance(target_unit_result, Err):
        response.status_code = HTTP_422_UNPROCESSABLE_CONTENT
        raise ConversionExceptionGroup("Errors", [target_unit_result.err()])

    target_unit: UnitsContainer = target_unit_result.ok()

    has_currencies = has_different_currencies(ureg, evaluated, target_unit)

    conversion_result = conversion.convert(evaluated, target_unit)
    if isinstance(conversion_result, Err):
        raise ConversionExceptionGroup("Errors", [conversion_result.err()])

    converted = conversion_result.ok()
    last_currency_update = (
        currency_handler.last_currency_update if has_currencies else None
    )

    # result = f"{converted:.3g~D}"
    same_unit = evaluated.unit_items() == target_unit.unit_items()

    magnitude = converted.magnitude
    units = converted.units

    result = QuantityWrapper(magnitude=magnitude, units=units)

    return ConversionResponse(
        result=result,
        input_interpretation=str(expression),
        last_currency_update=last_currency_update,
        input_unit_same_as_target=same_unit,
    )
