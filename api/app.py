import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import rich
from fastapi import FastAPI, Query, Response, status
from pint.facets.plain import PlainQuantity
from pint.util import UnitsContainer
from pydantic import BaseModel
from result import Err
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT

from api import conversion
from api.conversion import ConversionError, UnitError
from api.parsing import EvaluationError, ParserMode, ParsingError

logger = logging.getLogger(__name__)

app = FastAPI(title="Absolute Unit API", root_path="/api/v1")


@app.get("/test")
async def test(event_id: int = Query(default=42, alias="id")) -> dict[str, Any]:
    logger.info("AAAAAA")
    return {"id": event_id}


class QuantityWrapper(BaseModel):
    magnitude: float
    units: str


class ConversionResponse(BaseModel):
    result: QuantityWrapper
    expression: str
    last_currency_update: datetime.datetime
    input_unit_same_as_target: bool


@app.get("/convert", response_model=None)
async def convert(
    response: Response,
    ureg: conversion.UnitRegistryDep,
    user_input: str = Query(alias="input"),
    target_unit: str | None = None,
    mode: ParserMode = ParserMode.Strict,
) -> (
    ConversionResponse
    | list[ParsingError | ConversionError | UnitError | EvaluationError]
):
    errors = []

    with ThreadPoolExecutor(1) as executor:
        future = executor.submit(
            lambda: conversion.parse_input(
                user_input,
                ureg,
                mode,
            )
        )
        try:
            expression_result = future.result(timeout=2)
        except TimeoutError:
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            # TODO: should probably return instead of reraising
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
        return errors

    expression = expression_result.ok()

    rich.print(expression)

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
        return errors
    evaluated: PlainQuantity[float] = evaluation_result.ok().to_reduced_units()

    if target_unit is None:
        target_unit_result = conversion.infer_target_unit(evaluated, ureg)
    else:
        target_unit_result = conversion.get_target_unit(target_unit, ureg)

    if isinstance(target_unit_result, Err):
        response.status_code = HTTP_422_UNPROCESSABLE_CONTENT
        return [target_unit_result.err()]

    target_unit: UnitsContainer = target_unit_result.ok()

    conversion_result = conversion.convert(evaluated, target_unit)
    if isinstance(conversion_result, Err):
        return [conversion_result.err()]
    converted = conversion_result.ok()

    # result = f"{converted:.3g~D}"
    same_unit = evaluated.unit_items() == target_unit.unit_items()

    magnitude = converted.magnitude
    units = str(converted.units)

    result = QuantityWrapper(magnitude=magnitude, units=units)

    return ConversionResponse(
        result=result,
        expression=str(expression),
        last_currency_update=datetime.datetime.now(),
        input_unit_same_as_target=same_unit,
    )
