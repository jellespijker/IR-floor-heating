"""Tests for the MIMO Kalman fusion filter, focused on sensor gating."""

import pytest

from custom_components.ir_floor_heating.filters import FusionKalmanFilter


@pytest.fixture
def kf():
    """Build a filter configured for 1 floor sensor and 2 room sensors."""
    return FusionKalmanFilter(num_floor_sensors=1, num_room_sensors=2)


def test_update_with_all_sensors_reporting(kf):
    """All configured sensors present is the happy path."""
    kf.update([21.0], [20.0, 20.5], power=1000.0, dt=60.0)

    assert isinstance(kf.floor_temp, float)
    assert isinstance(kf.room_temp, float)


def test_update_with_unavailable_room_sensor(kf):
    """
    Check that a single unavailable sensor does not raise.

    Regression: dim_z was fixed at construction to the total sensor count, so
    a gated (shorter) z was rejected by filterpy with
    "z must be convertible to shape (3, 1)".
    """
    kf.update([21.0], [20.0, None], power=1000.0, dt=60.0)

    assert isinstance(kf.room_temp, float)


def test_update_with_only_one_sensor_left(kf):
    """Gating down to a single measurement still updates."""
    kf.update([None], [20.0, None], power=1000.0, dt=60.0)

    assert isinstance(kf.floor_temp, float)
    assert isinstance(kf.room_temp, float)


def test_update_with_no_valid_sensors_is_prediction_only(kf):
    """With every sensor unavailable the filter predicts but does not update."""
    kf.update([21.0], [20.0, 20.5], power=1000.0, dt=60.0)
    before = kf.room_temp

    kf.update([None], [None, None], power=1000.0, dt=60.0)

    # Prediction still advances the state, but no measurement was folded in.
    assert isinstance(kf.room_temp, float)
    assert kf.room_temp == pytest.approx(before, abs=1.0)


def test_sensor_recovery_after_dropout(kf):
    """A sensor coming back must not leave the filter in a broken shape."""
    kf.update([21.0], [20.0, 20.5], power=1000.0, dt=60.0)
    kf.update([21.0], [20.0, None], power=1000.0, dt=60.0)
    kf.update([21.0], [20.0, 20.5], power=1000.0, dt=60.0)

    assert isinstance(kf.floor_temp, float)
    assert isinstance(kf.room_temp, float)


def test_temperature_properties_return_scalars(kf):
    """Regression: float() on a size-1 numpy array is an error on numpy 2.x."""
    kf.update([21.0], [20.0, 20.5], power=1000.0, dt=60.0)

    assert type(kf.floor_temp) is float
    assert type(kf.room_temp) is float
    assert kf.x.shape == (4,)
