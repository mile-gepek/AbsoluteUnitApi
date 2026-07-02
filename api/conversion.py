from typing import Annotated

import pint
from fastapi import Depends
from pint import UnitRegistry
from pint.facets.plain import PlainQuantity
from pint.util import UnitsContainer
from result import Err, Ok, Result

from api import parsing
from api.errors import BaseError
from api.parsing import EvaluationError, ParsingError

metric_to_imperial = {
    "kilometer": "mile",
    "meter": "foot",
    "decimeter": "foot",
    "centimeter": "inch",
    "kilogram": "pound",
    "gram": "ounce",
    "kilometer_per_hour": "mile_per_hour",
    "celsius": "fahrenheit",
    "liter": "gallon",
    "milliliter": "fluid_ounce",
}


imperial_to_metric = {
    "mile": "kilometer",
    "foot": "meter",
    "inch": "centimeter",
    "pound": "kilogram",
    "mile_per_hour": "kilometer_per_hour",
    "fahrenheit": "celsius",
    "gallon": "liter",
    "pint": "liter",
    "fluid_ounce": "milliliter",
}


class Error(BaseError):
    pass


class UnitError(Error):
    pass


class ConversionError(Error):
    pass


class DimensionalityError(ConversionError):
    def __init__(
        self,
        expression_dimension: UnitsContainer,
        target_unit_dimension: UnitsContainer,
    ) -> None:
        self.expression_dimension = expression_dimension
        self.target_unit_dimension = target_unit_dimension
        super().__init__(
            f"Can not convert expression of dimension '{expression_dimension}' to target dimension '{target_unit_dimension}'",
            "TARGET_UNIT_DIMENSION_ERROR",
        )


class InvalidUnitError(UnitError):
    def __init__(self, unit: str) -> None:
        super().__init__(f"Undefined target units: {unit}", "INVALID_UNIT_ERROR")


class UnitInferError(UnitError):
    def __init__(self) -> None:
        super().__init__(
            "Can not infer target unit from expression.",
            "UNIT_INFER_ERROR",
        )


def infer_target_unit(
    quantity: PlainQuantity[float],
    ureg: UnitRegistry,
) -> Result[UnitsContainer, UnitInferError]:
    """
    Attempt to automatically recognize which units the given quantity to should be converted to.

    Errors
    ------
    - `UnitInferError`
        - The given quantity has units from both imperial and metric systems, so we can't infer which system to convert to.
    """

    # This works by stepping through each unit of the quantity (e.g. `5 N / m**2` has units `{N: 1, m: 2}`),
    # and if the unit is metric, adds its imperial "pair", and vice versa to the target unit.
    # Pairs are currently hardcoded in the dictionaries `imperial_to_metric` and `metric_to_imperial`.
    # Units which are used in both systems, such as `hour`, are added regardles.

    if quantity.units == ureg.cm:
        if quantity > ureg.Quantity("foot"):
            return Ok(UnitsContainer(foot=1))
        return Ok(UnitsContainer(inch=1))

    units = {}
    has_metric = False
    has_imperial = False
    for unit, power in quantity.unit_items():
        if unit in metric_to_imperial:
            if has_imperial:
                return Err(UnitInferError())
            has_metric = True
            new_unit = metric_to_imperial[unit]

        elif unit in imperial_to_metric:
            if has_metric:
                return Err(UnitInferError())
            has_imperial = True
            new_unit = imperial_to_metric[unit]

        else:
            new_unit = unit
        units[new_unit] = power

    return Ok(UnitsContainer(units))


def get_target_unit(
    target: str,
    ureg: UnitRegistry,
) -> Result[UnitsContainer, InvalidUnitError]:
    try:
        unit_quantity = ureg.Quantity(target)
    except pint.errors.UndefinedUnitError as e:
        units = ", ".join(e.unit_names)
        return Err(InvalidUnitError(units))
    unit_items = unit_quantity.unit_items()
    return Ok(UnitsContainer(unit_items))


def has_different_currencies(
    ureg: UnitRegistry,
    quantity: PlainQuantity[float],
    target: UnitsContainer,
) -> bool:
    q_units = UnitsContainer(quantity.unit_items())
    difference = set(q_units) ^ set(target)
    units = UnitsContainer({s: 0.1 for s in difference})
    dim = ureg.get_dimensionality(units)
    return "[currency]" in dim


def parse_input(
    input: str,
    ureg: UnitRegistry,
    mode: parsing.ParserMode = parsing.ParserMode.Adaptive,
) -> Result[parsing.Expression, list[ParsingError]]:
    parser = parsing.Parser(ureg, mode)
    parsing_result = parser.parse(input)
    if isinstance(parsing_result, Err):
        errors = parsing_result.err_value
        return Err(errors)
    return parsing_result


def evaluate_expression(
    expression: parsing.Expression,
    ureg: UnitRegistry,
) -> Result[PlainQuantity[float], list[EvaluationError]]:
    evaluation_result = expression.evaluate(ureg)
    if isinstance(evaluation_result, Err):
        errors = evaluation_result.err_value
        return Err(errors)
    return evaluation_result.map(ureg.Quantity)


def convert(
    quantity: PlainQuantity[float],
    target_unit: UnitsContainer,
) -> Result[PlainQuantity[float], ConversionError]:
    try:
        converted: PlainQuantity[float] = quantity.to(target_unit).to_reduced_units()
    except pint.DimensionalityError:
        return Err(DimensionalityError(quantity._units, target_unit))
    return Ok(converted)


unit_registry = UnitRegistry(filename="units.txt", autoconvert_offset_to_baseunit=False)


def get_unit_registry() -> UnitRegistry:
    return unit_registry


UnitRegistryDep = Annotated[UnitRegistry, Depends(get_unit_registry)]
