from unittest.mock import MagicMock
from custom_components.ir_floor_heating.sensor_manager import SensorManager


def test_calculate_total_power_with_sensors():
    """Test calculate_total_power using power sensors."""
    hass = MagicMock()

    manager = SensorManager(
        hass=hass,
        room_sensors=["sensor.room"],
        floor_sensors=["sensor.floor"],
        power_sensors=["sensor.power1", "sensor.power2"],
        heater_entity_id="switch.heater",
    )

    # Mock states for power sensors
    state1 = MagicMock()
    state1.state = "100.5"
    state2 = MagicMock()
    state2.state = "50.5"

    hass.states.get.side_effect = lambda entity_id: {
        "sensor.power1": state1,
        "sensor.power2": state2,
    }.get(entity_id)

    assert manager.calculate_total_power() == 151.0


def test_calculate_total_power_fallback_to_relays():
    """Test calculate_total_power falling back to relay attributes."""
    hass = MagicMock()

    manager = SensorManager(
        hass=hass,
        room_sensors=["sensor.room"],
        floor_sensors=["sensor.floor"],
        power_sensors=[],
        heater_entity_id="switch.heater",
    )

    # Mock relay state with power attribute
    relay_state = MagicMock()
    relay_state.attributes = {"power": "200.0"}

    hass.states.get.side_effect = lambda entity_id: {
        "switch.heater": relay_state,
    }.get(entity_id)

    assert manager.calculate_total_power() == 200.0


def test_calculate_total_power_unavailable_sensor():
    """Test calculate_total_power with an unavailable power sensor."""
    hass = MagicMock()

    manager = SensorManager(
        hass=hass,
        room_sensors=["sensor.room"],
        floor_sensors=["sensor.floor"],
        power_sensors=["sensor.power1", "sensor.power2"],
        heater_entity_id="switch.heater",
    )

    # Mock states: one valid, one unavailable
    state1 = MagicMock()
    state1.state = "100.0"
    state2 = MagicMock()
    state2.state = "unavailable"

    hass.states.get.side_effect = lambda entity_id: {
        "sensor.power1": state1,
        "sensor.power2": state2,
    }.get(entity_id)

    assert manager.calculate_total_power() == 100.0


def _room_manager(hass):
    return SensorManager(
        hass=hass,
        room_sensors=["sensor.fast", "sensor.reference"],
        floor_sensors=["sensor.floor"],
        power_sensors=[],
        heater_entity_id="switch.heater",
    )


def _state(value, reported):
    state = MagicMock()
    state.state = value
    state.last_reported = reported
    return state


def test_fresh_room_temperatures_hand_out_each_report_once():
    """A sensor that has not reported again yields None on the next read."""
    hass = MagicMock()
    states = {
        "sensor.fast": _state("23.5", 1),
        "sensor.reference": _state("20.0", 1),
    }
    hass.states.get.side_effect = states.get
    manager = _room_manager(hass)

    # First read: everything known counts as fresh.
    assert manager.get_fresh_room_temperatures() == [23.5, 20.0]
    # Nothing reported since.
    assert manager.get_fresh_room_temperatures() == [None, None]

    # Only the fast sensor reports again.
    states["sensor.fast"] = _state("23.6", 2)
    assert manager.get_fresh_room_temperatures() == [23.6, None]


def test_fresh_room_temperatures_count_unchanged_value_as_new_report():
    """A repeat of the same value with a newer report time is a measurement."""
    hass = MagicMock()
    states = {
        "sensor.fast": _state("23.5", 1),
        "sensor.reference": _state("20.0", 1),
    }
    hass.states.get.side_effect = states.get
    manager = _room_manager(hass)
    manager.get_fresh_room_temperatures()

    states["sensor.reference"] = _state("20.0", 2)
    assert manager.get_fresh_room_temperatures() == [None, 20.0]


def test_fresh_room_temperatures_skip_unavailable_and_recover():
    """An unavailable sensor is skipped and picked up when it returns."""
    hass = MagicMock()
    states = {
        "sensor.fast": _state("23.5", 1),
        "sensor.reference": _state("unavailable", 1),
    }
    hass.states.get.side_effect = states.get
    manager = _room_manager(hass)

    assert manager.get_fresh_room_temperatures() == [23.5, None]

    states["sensor.reference"] = _state("20.0", 2)
    assert manager.get_fresh_room_temperatures() == [None, 20.0]


def test_room_temperatures_are_not_affected_by_fresh_reads():
    """The plain getter keeps returning the current value of every sensor."""
    hass = MagicMock()
    states = {
        "sensor.fast": _state("23.5", 1),
        "sensor.reference": _state("20.0", 1),
    }
    hass.states.get.side_effect = states.get
    manager = _room_manager(hass)
    manager.get_fresh_room_temperatures()

    assert manager.get_room_temperatures() == [23.5, 20.0]
