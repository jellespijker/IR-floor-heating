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


# --- Room sensor bias estimation against a reference sensor -----------------


@pytest.fixture
def biased_kf():
    """One floor sensor, a warm-reading fast room sensor and a reference."""
    return FusionKalmanFilter(
        num_floor_sensors=1, num_room_sensors=2, reference_room_index=1
    )


def test_without_reference_there_are_no_bias_states(kf):
    """The default filter is unchanged: four states, no offsets."""
    kf.update([21.0], [20.0, 20.5], power=0.0, dt=60.0)

    assert kf.x.shape == (4,)
    assert kf.room_biases == [None, None]


def test_without_reference_room_sensors_are_averaged(kf):
    """Documents the behaviour that bias estimation is meant to fix."""
    for _ in range(200):
        kf.update([20.0], [23.5, 20.0], power=0.0, dt=60.0)

    assert kf.room_temp == pytest.approx(21.75, abs=0.05)


def test_reference_sets_level_and_offset_is_learned(biased_kf):
    """The fused value follows the reference; the offset lands on the other."""
    for _ in range(50):
        biased_kf.update([20.0], [23.5, 20.0], power=0.0, dt=60.0)

    assert biased_kf.room_temp == pytest.approx(20.0, abs=0.1)
    assert biased_kf.room_biases[0] == pytest.approx(3.5, abs=0.1)
    assert biased_kf.room_biases[1] is None


def test_fast_sensor_carries_dynamics_while_reference_is_silent(biased_kf):
    """
    Between reference reports the biased sensor still moves the estimate.

    The room warms 1 degC over 20 minutes and only the warm-reading sensor
    reports. The estimate has to follow the warming at the reference level
    instead of jumping to the biased reading or standing still.
    """
    for _ in range(50):
        biased_kf.update([20.0], [23.5, 20.0], power=0.0, dt=60.0)

    for step in range(1, 21):
        biased_kf.update([20.0], [23.5 + step * 0.05, None], power=0.0, dt=60.0)

    assert biased_kf.room_temp == pytest.approx(21.0, abs=0.3)
    assert biased_kf.room_biases[0] == pytest.approx(3.5, abs=0.3)


def test_offset_change_is_relearned_from_reference(biased_kf):
    """A drifting offset is corrected once the reference reports again."""
    for _ in range(50):
        biased_kf.update([20.0], [23.5, 20.0], power=0.0, dt=60.0)

    # The fast sensor's offset grows to 4.5 degC; the reference reports every
    # 6 minutes and keeps saying 20.0.
    for step in range(120):
        reference = 20.0 if step % 6 == 0 else None
        biased_kf.update([20.0], [24.5, reference], power=0.0, dt=60.0)

    assert biased_kf.room_temp == pytest.approx(20.0, abs=0.15)
    assert biased_kf.room_biases[0] == pytest.approx(4.5, abs=0.15)


def test_reference_dropout_keeps_last_offset(biased_kf):
    """With the reference unavailable the learned offset stays applied."""
    for _ in range(50):
        biased_kf.update([20.0], [23.5, 20.0], power=0.0, dt=60.0)

    for _ in range(120):
        biased_kf.update([20.0], [23.5, None], power=0.0, dt=60.0)

    assert biased_kf.room_temp == pytest.approx(20.0, abs=0.2)


def test_three_room_sensors_get_independent_offsets():
    """Each non-reference sensor learns its own offset."""
    kf = FusionKalmanFilter(
        num_floor_sensors=1, num_room_sensors=3, reference_room_index=0
    )
    for _ in range(50):
        kf.update([20.0], [19.0, 22.5, 18.2], power=0.0, dt=60.0)

    assert kf.x.shape == (6,)
    assert kf.room_temp == pytest.approx(19.0, abs=0.1)
    assert kf.room_biases[0] is None
    assert kf.room_biases[1] == pytest.approx(3.5, abs=0.1)
    assert kf.room_biases[2] == pytest.approx(-0.8, abs=0.1)


def test_reference_only_room_sensor_has_no_offsets():
    """A lone reference sensor degenerates to the plain filter."""
    kf = FusionKalmanFilter(
        num_floor_sensors=1, num_room_sensors=1, reference_room_index=0
    )
    kf.update([20.0], [19.0], power=0.0, dt=60.0)

    assert kf.x.shape == (4,)
    assert kf.room_biases == [None]


@pytest.mark.parametrize("index", [-1, 2])
def test_reference_index_out_of_range_is_rejected(index):
    """A reference that is not one of the room sensors is a config error."""
    with pytest.raises(ValueError, match="reference_room_index"):
        FusionKalmanFilter(
            num_floor_sensors=1, num_room_sensors=2, reference_room_index=index
        )
