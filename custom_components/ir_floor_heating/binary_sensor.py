"""Binary sensor platform for IR floor heating status indicators."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .climate import IRFloorHeatingClimate

_LOGGER = logging.getLogger(__name__)

# Binary sensors don't control devices, so no need to serialize updates
PARALLEL_UPDATES = 0


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up IR floor heating binary sensors from a config entry."""
    climate_entity = config_entry.runtime_data

    async_add_entities(
        [
            IRFloorHeatingSafetyVetoBinarySensor(climate_entity, config_entry),
            IRFloorHeatingMaintainComfortLimitBinarySensor(
                climate_entity, config_entry
            ),
        ]
    )


class IRFloorHeatingBaseBinarySensor(BinarySensorEntity):
    """Base class for IR floor heating binary sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Binary sensors are diagnostic by default
    _attr_entity_registry_enabled_default = True

    def __init__(
        self,
        climate_entity: IRFloorHeatingClimate,
        _config_entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        self._climate_entity = climate_entity
        # Inherit device info from climate entity
        device_info = getattr(climate_entity, "_attr_device_info", None)
        if device_info is not None:
            self._attr_device_info = device_info
        # Use climate entity's unique_id as base for shorter, consistent IDs
        self._attr_unique_id = (
            f"{climate_entity.unique_id}_{self._attr_translation_key}"
        )
        self._last_reported_value: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()

        # Update when climate entity updates
        @callback
        def _handle_climate_update(_event: Event[EventStateChangedData]) -> None:
            """Handle updates from the climate entity only if value changed."""
            current_value = self.is_on
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


class IRFloorHeatingSafetyVetoBinarySensor(IRFloorHeatingBaseBinarySensor):
    """Binary sensor for safety veto status."""

    _attr_translation_key = "safety_veto_active"
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_entity_registry_enabled_default = True

    @property
    def is_on(self) -> bool:
        """Return True if safety veto is active."""
        return self._climate_entity.safety_veto_active


class IRFloorHeatingMaintainComfortLimitBinarySensor(IRFloorHeatingBaseBinarySensor):
    """Binary sensor for maintain comfort limit mode status."""

    _attr_translation_key = "maintain_comfort_limit"
    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_entity_registry_enabled_default = True

    @property
    def is_on(self) -> bool:
        """Return True if maintain comfort limit is enabled."""
        return self._climate_entity.maintain_comfort_limit
