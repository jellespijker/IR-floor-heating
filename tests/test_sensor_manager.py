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
