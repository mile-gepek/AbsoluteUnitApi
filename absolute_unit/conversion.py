import pint
from pint import UnitRegistry
from pint.facets.plain import PlainQuantity
from pint.util import UnitsContainer

from result import Result, Ok, Err

from absolute_unit import parsing

metric_to_imperial = {
    "kilometer": "mile",
    "meter": "foot",
    "decimeter": "foot",
    "centimeter": "inch",
    "kilogram": "pound",
    "gram": "ounce",
    "kilometer_per_hour": "mile_per_hour",
}


imperial_to_metric = {
    "mile": "kilometer",
    "foot": "meter",
    "inch": "centimeter",
    "pound": "kilogram",
    "mile_per_hour": "kilometer_per_hour",
}


class UnitError(Exception):
    pass


class ConversionError(Exception):
    pass


class DimensionalityError(ConversionError):
    def __init__(self, dim_1: str, dim_2: str) -> None:
        super().__init__(
            f"Mismatched dimensionalities between input `{dim_1}` and target `{dim_2}`"
        )


class InvalidUnitError(UnitError):
    def __init__(self, unit: str) -> None:
        super().__init__(f"Undefined target units: {unit}")


class UnitInferError(UnitError):
    def __init__(self) -> None:
        super().__init__("Can not infer target unit from expression.")


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


def parse_input(input: str, ureg: UnitRegistry) -> Result[parsing.Expression, str]:
    parser = parsing.Parser(ureg)
    parsing_result = parser.parse(input)
    if isinstance(parsing_result, Err):
        errors = parsing_result.err_value
        errors_formatted = parsing.format_errors(errors, len(input))
        return Err(errors_formatted)
    return parsing_result


def evaluate_expression(
    expression: parsing.Expression,
    ureg: UnitRegistry,
) -> Result[PlainQuantity[float], str]:
    evaluation_result = expression.evaluate(ureg)
    if isinstance(evaluation_result, Err):
        errors = evaluation_result.err_value
        errors_formatted = parsing.format_errors(errors, expression.end())
        return Err(errors_formatted)
    return evaluation_result


def convert(
    quantity: PlainQuantity[float],
    target_unit: UnitsContainer,
) -> Result[PlainQuantity[float], ConversionError]:
    try:
        converted: PlainQuantity[float] = quantity.to(target_unit).to_reduced_units()  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]
    except pint.DimensionalityError as e:
        return Err(DimensionalityError(e.dim1, e.dim2))
    return Ok(converted)
