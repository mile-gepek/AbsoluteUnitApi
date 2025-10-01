import pint
from pint.facets.plain import PlainQuantity
from pint.util import UnitsContainer

from result import Result, Ok, Err

from absolute_unit import ureg, parsing

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


class ConversionError(Exception):
    pass


class UnitInferError(ConversionError):
    def __init__(self, *args: object) -> None:
        super().__init__("Can not infer target unit from expression.")


def infer_target_unit(
    quantity: PlainQuantity[float],
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


def convert_expression(
    quantity: PlainQuantity[float],
    target: str | None = None,
) -> Result[PlainQuantity[float], ConversionError]:
    if target is None:
        target_result = infer_target_unit(quantity)
        if isinstance(target_result, Err):
            return target_result
        target_unit = target_result.ok_value
    else:
        unit_dict = {}
        try:
            quantity = ureg(target)
        except pint.errors.UndefinedUnitError as e:
            units = ", ".join(e.unit_names)
            return Err(ConversionError(f"Undefined target unit(s): {units}."))
        for unit, power in quantity.unit_items():
            unit_dict[unit] = power
        target_unit = UnitsContainer(unit_dict)
    try:
        converted: PlainQuantity[float] = quantity.to(target_unit).to_reduced_units()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return Ok(converted)
    except pint.errors.DimensionalityError as e:
        return Err(
            ConversionError(
                f"Mismatched dimensions of input '{e.dim1}' and target '{e.dim2}'."
            )
        )


def try_convert_expression(
    input: str, target: str | None = None
) -> Result[tuple[parsing.Expression, PlainQuantity[float]], str]:
    parsing_result = parsing.parse(input)
    if isinstance(parsing_result, Err):
        errors = parsing_result.err_value
        errors_formatted = parsing.format_errors(errors, len(input))
        output = f"```\n{input}\n{errors_formatted}\n```"
        return Err(output)
    expression = parsing_result.ok_value

    eval_result = expression.evaluate()
    if isinstance(eval_result, Err):
        errors = eval_result.err_value
        errors_formatted = parsing.format_errors(errors, len(input))
        output = f"```\n{input}\n{errors_formatted}\n```"
        return Err(output)
    evaluated = eval_result.ok_value

    converted_result = convert_expression(evaluated, target)
    if isinstance(converted_result, Err):
        error_str = str(converted_result.err_value)
        output = f"```\n{input}\n{error_str}\n```"
        return Err(output)

    return Ok((expression, converted_result.ok_value))
