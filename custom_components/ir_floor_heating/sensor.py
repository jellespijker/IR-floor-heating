"""Sensor platform for IR floor heating diagnostic sensors."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .climate import IRFloorHeatingClimate

_LOGGER = logging.getLogger(__name__)

# Sensors don't control devices, so no need to serialize updates
PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up IR floor heating sensors from a config entry."""
    climate_entity = config_entry.runtime_data

    async_add_entities(
        [
            IRFloorHeatingDemandSensor(climate_entity, config_entry),
            IRFloorHeatingEffectiveLimitSensor(climate_entity, config_entry),
            IRFloorHeatingSafetyVetoSensor(climate_entity, config_entry),
            IRFloorHeatingIntegralErrorSensor(climate_entity, config_entry),
            IRFloorHeatingRoomPIDDemandSensor(climate_entity, config_entry),
            IRFloorHeatingFloorPIDDemandSensor(climate_entity, config_entry),
            IRFloorHeatingRoomIntegralErrorSensor(climate_entity, config_entry),
            IRFloorHeatingFloorIntegralErrorSensor(climate_entity, config_entry),
            IRFloorHeatingRelayToggleCountSensor(climate_entity, config_entry),
        ]
    )


class IRFloorHeatingBaseSensor(SensorEntity):
    """Base class for IR floor heating sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Diagnostic sensors are disabled by default to avoid cluttering statistics
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        climate_entity: IRFloorHeatingClimate,
        _config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        self._climate_entity = climate_entity
        # Inherit device info from climate entity
        device_info = getattr(climate_entity, "_attr_device_info", None)
        if device_info is not None:
            self._attr_device_info = device_info
        # Use climate entity's unique_id as base for shorter, consistent IDs
        self._attr_unique_id = (
            f"{climate_entity.unique_id}_{self._attr_translation_key}"
        )
        self._last_reported_value: Any = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()

        # Update when climate entity updates
        @callback
        def _handle_climate_update(_event: Event[EventStateChangedData]) -> None:
            """Handle updates from the climate entity only if value changed."""
            current_value = self.native_value
            # Only write state if the value actually changed
            if current_value != self._last_reported_value:
                self._last_reported_value = current_value
                self.async_write_ha_state()

        # Track the climate entity state changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._climate_entity.entity_id],
                _handle_climate_update,
            )
        )

        # Trigger initial update
        self.async_write_ha_state()


class IRFloorHeatingDemandSensor(IRFloorHeatingBaseSensor):
    """Sensor for heating demand percentage."""

    _attr_translation_key = "demand_percent"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the current demand percentage."""
        return self._climate_entity.demand_percent


class IRFloorHeatingEffectiveLimitSensor(IRFloorHeatingBaseSensor):
    """Sensor for effective floor temperature limit."""

    _attr_translation_key = "effective_floor_limit"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the effective floor temperature limit."""
        return self._climate_entity.effective_floor_limit


class IRFloorHeatingSafetyVetoSensor(IRFloorHeatingBaseSensor):
    """Sensor for safety veto status (0 = off, 1 = active)."""

    _attr_translation_key = "safety_veto_active"
    _attr_native_unit_of_measurement = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> int:
        """Return 1 if safety veto is active, 0 otherwise."""
        return 1 if self._climate_entity.safety_veto_active else 0


class IRFloorHeatingIntegralErrorSensor(IRFloorHeatingBaseSensor):
    """Sensor for PID integral error term."""

    _attr_translation_key = "integral_error"
    _attr_native_unit_of_measurement = "°C·s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the integral error value."""
        return self._climate_entity.integral_error


class IRFloorHeatingRoomPIDDemandSensor(IRFloorHeatingBaseSensor):
    """Sensor for room temperature PID demand percentage."""

    _attr_translation_key = "room_pid_demand"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the room PID demand percentage."""
        return self._climate_entity.room_pid_demand_percent


class IRFloorHeatingFloorPIDDemandSensor(IRFloorHeatingBaseSensor):
    """Sensor for floor limit PID demand percentage."""

    _attr_translation_key = "floor_pid_demand"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the floor PID demand percentage."""
        return self._climate_entity.floor_pid_demand_percent


class IRFloorHeatingRoomIntegralErrorSensor(IRFloorHeatingBaseSensor):
    """Sensor for room PID integral error term."""

    _attr_translation_key = "room_integral_error"
    _attr_native_unit_of_measurement = "°C·s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the room PID integral error value."""
        return self._climate_entity.room_integral_error


class IRFloorHeatingFloorIntegralErrorSensor(IRFloorHeatingBaseSensor):
    """Sensor for floor PID integral error term."""

    _attr_translation_key = "floor_integral_error"
    _attr_native_unit_of_measurement = "°C·s"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return the floor PID integral error value."""
        return self._climate_entity.floor_integral_error


class IRFloorHeatingRelayToggleCountSensor(IRFloorHeatingBaseSensor):
    """Sensor for relay toggle count (cumulative since tracking started)."""

    _attr_translation_key = "relay_toggle_count"
    _attr_native_unit_of_measurement = None
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0
    # Enable by default since relay wear tracking is useful for maintenance
    _attr_entity_registry_enabled_default = True

    @property
    def native_value(self) -> int | None:
        """Return the total relay toggle count."""
        return self._climate_entity.relay_toggle_count
