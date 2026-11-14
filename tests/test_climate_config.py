"""Tests for reading values from the config entry."""

import pytest

from custom_components.ir_floor_heating.climate import _optional_float


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("0.5", 0.5),  # as saved by the options form dropdown
        ("1.0", 1.0),
        (0.5, 0.5),  # as stored by older or hand-edited entries
        (1, 1.0),
        (None, None),
        ("", None),
    ],
)
def test_optional_float(stored, expected):
    """Precision and step are numbers whatever form they were stored in."""
    result = _optional_float(stored)

    assert result == expected
    assert result is None or type(result) is float
