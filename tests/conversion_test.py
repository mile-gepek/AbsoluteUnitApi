from pint.util import UnitsContainer
import pytest
from result import Err, Ok

from absolute_unit import ureg

from absolute_unit.conversion import (
    ConversionError,
    DimensionalityError,
    metric_to_imperial,
    imperial_to_metric,
    infer_target_unit,
    convert,
    UnitError,
    UnitInferError,
)


def str_to_units_container(units: str) -> UnitsContainer:
    quantity = ureg.Quantity(units)
    unit_container = UnitsContainer(quantity.unit_items())
    return unit_container


@pytest.mark.parametrize("metric, imperial", list(metric_to_imperial.items()))
def test_infer_target_unit_metric_to_imperial(metric: str, imperial: str):
    qty = ureg(metric)
    result = infer_target_unit(qty)

    assert isinstance(result, Ok)
    units = result.ok()
    assert imperial in units


@pytest.mark.parametrize("imperial, metric", list(imperial_to_metric.items()))
def test_infer_target_unit_imperial_to_metric(imperial: str, metric: str):
    qty = ureg(imperial)
    result = infer_target_unit(qty)

    assert isinstance(result, Ok)
    units = result.ok()
    assert metric in units


def test_infer_target_unit_mixed_metric_and_imperial_length():
    qty = ureg("5 mile") / ureg("2 meter")
    result = infer_target_unit(qty)

    assert isinstance(result, Err)
    assert isinstance(result.err(), UnitInferError)


def test_infer_target_unit_mixed_metric_and_imperial_weight():
    qty = ureg("kg") * ureg("lbs")
    result = infer_target_unit(qty)

    assert isinstance(result, Err)
    assert isinstance(result.err(), UnitInferError)


def test_infer_target_unit_mixed_metric_and_imperial_speed():
    qty = ureg("mph") * ureg("meter")
    result = infer_target_unit(qty)

    assert isinstance(result, Err)
    assert isinstance(result.err(), UnitInferError)


@pytest.mark.parametrize(
    "src_unit, expected_unit",
    [
        ("kilometer", "mile"),
        ("meter", "foot"),
        ("decimeter", "foot"),
        ("centimeter", "inch"),
        ("kilogram", "pound"),
        ("gram", "ounce"),
        ("kilometer / hour", "mile / hour"),
        ("mile", "kilometer"),
        ("foot", "meter"),
        ("inch", "centimeter"),
        ("pound", "kilogram"),
        ("mile / hour", "kilometer / hour"),
    ],
)
def test_convert(src_unit: str, expected_unit: str):
    qty = ureg(src_unit)
    target = str_to_units_container(expected_unit)
    result = convert(qty, target)

    assert isinstance(result, Ok)
    converted = result.ok()
    assert expected_unit in str(converted.units)


@pytest.mark.parametrize(
    "src_unit, target_unit",
    [
        ("meter", "second"),  # length -> time
        ("kilogram", "meter"),  # mass -> length
        ("second", "pound"),  # time -> mass
    ],
)
def test_convert_expression_dimensionality_mismatch(src_unit: str, target_unit: str):
    qty = ureg(src_unit)
    target = str_to_units_container(target_unit)
    result = convert(qty, target)

    assert isinstance(result, Err)
    error = result.err()
    assert isinstance(error, DimensionalityError)
