"""Sensor manager for IR floor heating."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SensorManager:
    """Helper to manage sensor readings."""

    def __init__(
        self,
        hass: HomeAssistant,
        room_sensors: list[str],
        floor_sensors: list[str],
        power_sensors: list[str],
        heater_entity_id: str,
    ) -> None:
        """Initialize the sensor manager."""
        self.hass = hass
        self.room_sensors = room_sensors
        self.floor_sensors = floor_sensors
        self.power_sensors = power_sensors
        self.heater_entity_id = heater_entity_id
        # Report time of the last reading consumed per room sensor, used by
        # get_fresh_room_temperatures().
        self._last_consumed: dict[str, object] = {}

    def _get_sensor_values(self, entity_ids: list[str]) -> list[float | None]:
        """Gather float values from a list of entity IDs."""
        values: list[float | None] = []
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    values.append(float(state.state))
                except ValueError:
                    values.append(None)
            else:
                values.append(None)
        return values

    def get_room_temperatures(self) -> list[float | None]:
        """Get room temperature readings."""
        return self._get_sensor_values(self.room_sensors)

    def get_fresh_room_temperatures(self) -> list[float | None]:
        """
        Get room temperature readings that were not handed out before.

        A sensor that has not reported since the previous call yields None, so
        every reading is used as a measurement exactly once. This matters for
        bias estimation against a reference sensor: re-feeding the stale value
        of a slow (battery) reference on every update of a fast sensor would
        pin the room estimate to that stale value.
        """
        values: list[float | None] = []
        for entity_id in self.room_sensors:
            state = self.hass.states.get(entity_id)
            if not state or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                values.append(None)
                continue

            reported = getattr(state, "last_reported", None) or getattr(
                state, "last_updated", None
            )
            if reported is not None and self._last_consumed.get(entity_id) == reported:
                values.append(None)
                continue

            try:
                value = float(state.state)
            except ValueError:
                values.append(None)
                continue

            self._last_consumed[entity_id] = reported
            values.append(value)
        return values

    def get_floor_temperatures(self) -> list[float | None]:
        """Get floor temperature readings."""
        return self._get_sensor_values(self.floor_sensors)

    def calculate_total_power(self) -> float:
        """Sum power from all power sensors or the heater entity."""
        total_power = 0.0

        if self.power_sensors:
            power_values = self._get_sensor_values(self.power_sensors)
            for val in power_values:
                if val is not None:
                    total_power += val
            return total_power

        # Fallback to heater attributes if no power sensors defined
        state = self.hass.states.get(self.heater_entity_id)
        if state:
            # Extract attribute power or current_power_w
            p = state.attributes.get("power") or state.attributes.get("current_power_w")
            if p is not None:
                with contextlib.suppress(ValueError, TypeError):
                    total_power += float(p)
        return total_power
