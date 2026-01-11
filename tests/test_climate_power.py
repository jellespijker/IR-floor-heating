from unittest.mock import MagicMock, patch
from datetime import timedelta
from homeassistant.const import STATE_ON, STATE_OFF
from custom_components.ir_floor_heating.climate import (
    IRFloorHeatingClimate,
    ClimateConfig,
)


def test_calculate_total_power_with_sensors():
    """Test _calculate_total_power using power sensors."""
    hass = MagicMock()
    config = ClimateConfig(
        hass=hass,
        name="Test",
        heater_entity_id="switch.heater",
        room_sensor_entity_id="sensor.room",
        floor_sensor_entity_id="sensor.floor",
        room_sensors=["sensor.room"],
        floor_sensors=["sensor.floor"],
        power_sensors=["sensor.power1", "sensor.power2"],
        min_temp=10,
        max_temp=30,
        target_temp=21,
        max_floor_temp=28,
        max_floor_temp_diff=5,
        min_cycle_duration=timedelta(seconds=60),
        cycle_period=timedelta(seconds=900),
        keep_alive=None,
        initial_hvac_mode=None,
        precision=0.1,
        target_temperature_step=0.1,
        unit="°C",
        unique_id="test_id",
        boost_mode=True,
        boost_temp_diff=1.5,
        safety_hysteresis=0.5,
        pid_kp=80,
        pid_ki=2,
        pid_kd=15,
        floor_pid_kp=20,
        floor_pid_ki=0.5,
        floor_pid_kd=10,
        maintain_comfort_limit=False,
    )

    climate = IRFloorHeatingClimate(config)

    # Mock states for power sensors
    state1 = MagicMock()
    state1.state = "100.5"
    state2 = MagicMock()
    state2.state = "50.5"

    hass.states.get.side_effect = lambda entity_id: {
        "sensor.power1": state1,
        "sensor.power2": state2,
    }.get(entity_id)

    assert climate._calculate_total_power() == 151.0


def test_calculate_total_power_fallback_to_relays():
    """Test _calculate_total_power falling back to relay attributes."""
    hass = MagicMock()
    config = ClimateConfig(
        hass=hass,
        name="Test",
        heater_entity_id="switch.heater",
        room_sensor_entity_id="sensor.room",
        floor_sensor_entity_id="sensor.floor",
        room_sensors=["sensor.room"],
        floor_sensors=["sensor.floor"],
        power_sensors=[],
        min_temp=10,
        max_temp=30,
        target_temp=21,
        max_floor_temp=28,
        max_floor_temp_diff=5,
        min_cycle_duration=timedelta(seconds=60),
        cycle_period=timedelta(seconds=900),
        keep_alive=None,
        initial_hvac_mode=None,
        precision=0.1,
        target_temperature_step=0.1,
        unit="°C",
        unique_id="test_id",
        boost_mode=True,
        boost_temp_diff=1.5,
        safety_hysteresis=0.5,
        pid_kp=80,
        pid_ki=2,
        pid_kd=15,
        floor_pid_kp=20,
        floor_pid_ki=0.5,
        floor_pid_kd=10,
        maintain_comfort_limit=False,
    )

    climate = IRFloorHeatingClimate(config)

    # Mock relay state with power attribute
    relay_state = MagicMock()
    relay_state.attributes = {"power": "200.0"}

    hass.states.get.side_effect = lambda entity_id: {
        "switch.heater": relay_state,
    }.get(entity_id)

    assert climate._calculate_total_power() == 200.0


def test_calculate_total_power_unavailable_sensor():
    """Test _calculate_total_power with an unavailable power sensor."""
    hass = MagicMock()
    config = ClimateConfig(
        hass=hass,
        name="Test",
        heater_entity_id="switch.heater",
        room_sensor_entity_id="sensor.room",
        floor_sensor_entity_id="sensor.floor",
        room_sensors=["sensor.room"],
        floor_sensors=["sensor.floor"],
        power_sensors=["sensor.power1", "sensor.power2"],
        min_temp=10,
        max_temp=30,
        target_temp=21,
        max_floor_temp=28,
        max_floor_temp_diff=5,
        min_cycle_duration=timedelta(seconds=60),
        cycle_period=timedelta(seconds=900),
        keep_alive=None,
        initial_hvac_mode=None,
        precision=0.1,
        target_temperature_step=0.1,
        unit="°C",
        unique_id="test_id",
        boost_mode=True,
        boost_temp_diff=1.5,
        safety_hysteresis=0.5,
        pid_kp=80,
        pid_ki=2,
        pid_kd=15,
        floor_pid_kp=20,
        floor_pid_ki=0.5,
        floor_pid_kd=10,
        maintain_comfort_limit=False,
    )

    climate = IRFloorHeatingClimate(config)

    # Mock states: one valid, one unavailable
    state1 = MagicMock()
    state1.state = "100.0"
    state2 = MagicMock()
    state2.state = "unavailable"

    hass.states.get.side_effect = lambda entity_id: {
        "sensor.power1": state1,
        "sensor.power2": state2,
    }.get(entity_id)

    assert climate._calculate_total_power() == 100.0
