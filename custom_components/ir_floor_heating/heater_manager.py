"""Heater manager with cascading power bucket algorithm for multi-relay actuation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class Heater:
    """Represents a single heater/relay with its power rating."""

    entity_id: str
    power: float  # Watts or relative unit (all heaters should use same unit)
    name: str = ""

    def __post_init__(self) -> None:
        """Post-init hook to set default name."""
        if not self.name:
            self.name = self.entity_id.split(".")[-1]


@dataclass
class HeaterState:
    """Current state of a heater."""

    entity_id: str
    should_be_on: bool = False
    duty_cycle: float = 0.0  # 0-100% for TPI heater


class HeaterShuffler:
    """
    Manages multiple heater relays with cascading power bucket algorithm.

    Features:
    - Distributes demand across multiple heaters
    - Maintains baseload for continuously-on heaters (no switching)
    - Uses single TPI heater for fractional remainder
    - Rotates priority order each cycle to prevent wear imbalance
    """

    def __init__(
        self,
        hass: HomeAssistant,
        heaters: list[Heater],
        cycle_period: timedelta,
        min_cycle_duration: timedelta,
    ) -> None:
        """
        Initialize the heater shuffler.

        Args:
            hass: Home Assistant instance
            heaters: List of Heater configurations
            cycle_period: Duration of one control cycle (e.g., 900 seconds = 15 min)
            min_cycle_duration: Minimum on/off time for relay protection

        Raises:
            ValueError: If heaters list is empty or has invalid configuration
        """
        if not heaters:
            raise ValueError("At least one heater must be configured")

        self.hass = hass
        self.heaters = heaters
        self.cycle_period = cycle_period
        self.min_cycle_duration = min_cycle_duration

        # Calculate total capacity
        self._total_capacity = sum(h.power for h in heaters)

        # Rotation state: index incremented each cycle to rotate priority
        self._rotation_index: int = 0

        # Cycle timing
        self._cycle_start_time: datetime | None = None

        # Track last known states to avoid redundant service calls
        self._last_states: dict[str, bool] = {h.entity_id: False for h in heaters}

        # Statistics
        self._toggle_counts: dict[str, int] = {h.entity_id: 0 for h in heaters}

        _LOGGER.info(
            "HeaterShuffler initialized with %d heaters, total capacity: %.1f, "
            "cycle period: %ds, min cycle: %ds",
            len(heaters),
            self._total_capacity,
            cycle_period.total_seconds(),
            min_cycle_duration.total_seconds(),
        )

    async def async_apply_demand(
        self,
        demand_percent: float,
        context: object | None = None,
    ) -> list[HeaterState]:
        """
        Apply heating demand using cascading power bucket algorithm.

        Args:
            demand_percent: Heating demand percentage (0-100%)
            context: Home Assistant context for service calls

        Returns:
            List of HeaterState objects describing the new state for each heater
        """
        if demand_percent < 0 or demand_percent > 100:
            _LOGGER.warning("Invalid demand percentage: %.1f%%", demand_percent)
            demand_percent = max(0, min(100, demand_percent))

        # Get the prioritized list of heaters (rotated)
        prioritized_heaters = self._get_prioritized_heaters()

        # Calculate required power based on demand
        required_power = self._total_capacity * (demand_percent / 100.0)

        # Calculate heater states using cascading power bucket
        heater_states = self._calculate_heater_states(
            prioritized_heaters, required_power
        )

        # Apply the calculated states via Home Assistant service calls
        await self._async_actuate_heaters(heater_states, context)

        return heater_states

    def _get_prioritized_heaters(self) -> list[Heater]:
        """Get heaters in priority order (rotated each cycle)."""
        if len(self.heaters) <= 1:
            return self.heaters

        # Rotate the priority list
        index = self._rotation_index % len(self.heaters)
        return self.heaters[index:] + self.heaters[:index]

    def _calculate_heater_states(
        self,
        prioritized_heaters: list[Heater],
        required_power: float,
    ) -> dict[str, HeaterState]:
        """
        Calculate the state for each heater using cascading power bucket.

        Algorithm:
        1. Iterate through heaters in priority order
        2. If required_power >= heater_power: Turn heater ON (100% duty)
        3. If 0 < required_power < heater_power: This is the TPI heater
           (calculate duty cycle, actuate based on cycle timing)
        4. If required_power <= 0: Turn heater OFF

        Args:
            prioritized_heaters: Heaters in priority order
            required_power: Total power required (sum of all heater power scales)

        Returns:
            Dictionary mapping entity_id to HeaterState
        """
        heater_states: dict[str, HeaterState] = {}
        tpi_heater_entity_id: str | None = None
        tpi_duty_cycle: float = 0.0

        # Process heaters in priority order
        for heater in prioritized_heaters:
            if required_power >= heater.power:
                # This heater goes full ON
                heater_states[heater.entity_id] = HeaterState(
                    entity_id=heater.entity_id, should_be_on=True, duty_cycle=100.0
                )
                required_power -= heater.power
            elif required_power > 0:
                # This is the TPI heater (fractional remainder)
                tpi_duty_cycle = (required_power / heater.power) * 100.0
                tpi_heater_entity_id = heater.entity_id
                heater_states[heater.entity_id] = HeaterState(
                    entity_id=heater.entity_id,
                    should_be_on=False,  # Will be set by TPI timing
                    duty_cycle=tpi_duty_cycle,
                )
                required_power = 0.0
            else:
                # This heater and all remaining go OFF
                heater_states[heater.entity_id] = HeaterState(
                    entity_id=heater.entity_id, should_be_on=False, duty_cycle=0.0
                )

        # Ensure all heaters are in the dictionary
        for heater in self.heaters:
            if heater.entity_id not in heater_states:
                heater_states[heater.entity_id] = HeaterState(
                    entity_id=heater.entity_id, should_be_on=False, duty_cycle=0.0
                )

        # Apply TPI logic to the designated TPI heater (if any)
        if tpi_heater_entity_id is not None:
            tpi_state = self._calculate_tpi_state(tpi_duty_cycle)
            heater_states[tpi_heater_entity_id].should_be_on = tpi_state

        return heater_states

    def _calculate_tpi_state(self, duty_cycle: float) -> bool:
        """
        Calculate TPI relay state based on cycle position.

        Args:
            duty_cycle: Desired duty cycle (0-100%)

        Returns:
            True if relay should be ON, False if OFF
        """
        current_time = datetime.now(UTC)

        # Initialize cycle start time
        if self._cycle_start_time is None:
            self._cycle_start_time = current_time

        # Calculate time within current cycle
        time_in_cycle = (current_time - self._cycle_start_time).total_seconds()
        cycle_duration = self.cycle_period.total_seconds()

        # Start new cycle if period elapsed
        if time_in_cycle >= cycle_duration:
            self._cycle_start_time = current_time
            time_in_cycle = 0.0
            self._rotation_index += 1  # Rotate priority at cycle start

        # Calculate ON duration for this cycle based on duty cycle
        on_duration_seconds = (duty_cycle / 100.0) * cycle_duration

        # Apply minimum cycle duration constraints (relay protection)
        min_duration = self.min_cycle_duration.total_seconds()
        if on_duration_seconds < min_duration:
            on_duration_seconds = 0.0  # Too short, stay OFF
        elif on_duration_seconds > (cycle_duration - min_duration):
            on_duration_seconds = cycle_duration  # Stay ON full cycle

        # Determine relay state for current position in cycle
        return time_in_cycle < on_duration_seconds

    async def _async_actuate_heaters(
        self,
        heater_states: dict[str, HeaterState],
        context: object | None = None,
    ) -> None:
        """
        Apply heater states via Home Assistant service calls.

        Only calls services if state actually changed.

        Args:
            heater_states: Dictionary of HeaterState objects
            context: Home Assistant context for service calls
        """
        for entity_id, state in heater_states.items():
            # Get current state from Home Assistant
            current_state_entity = self.hass.states.get(entity_id)
            current_is_on = (
                current_state_entity.state == STATE_ON
                if current_state_entity
                else False
            )

            # Only call service if state should change
            if state.should_be_on and not current_is_on:
                _LOGGER.debug("Turning ON heater: %s", entity_id)
                await self.hass.services.async_call(
                    HOMEASSISTANT_DOMAIN,
                    SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: entity_id},
                    context=context,
                )
                self._last_states[entity_id] = True
                self._toggle_counts[entity_id] += 1
            elif not state.should_be_on and current_is_on:
                _LOGGER.debug("Turning OFF heater: %s", entity_id)
                await self.hass.services.async_call(
                    HOMEASSISTANT_DOMAIN,
                    SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    context=context,
                )
                self._last_states[entity_id] = False
                self._toggle_counts[entity_id] += 1

    def reset_cycle(self) -> None:
        """Reset the TPI control cycle (call on demand changes or force updates)."""
        self._cycle_start_time = None

    def get_toggle_count(self, entity_id: str) -> int:
        """Get total toggle count for a specific heater."""
        return self._toggle_counts.get(entity_id, 0)

    def get_total_toggle_count(self) -> int:
        """Get total toggle count across all heaters."""
        return sum(self._toggle_counts.values())

    def get_cycle_info(self) -> dict[str, float]:
        """
        Get diagnostic information about current cycle position.

        Returns:
            Dictionary with time_in_cycle and cycle_period (both in seconds)
        """
        if self._cycle_start_time is None:
            return {"time_in_cycle": 0.0, "cycle_period": 0.0}

        current_time = datetime.now(UTC)
        time_in_cycle = (current_time - self._cycle_start_time).total_seconds()
        cycle_period = self.cycle_period.total_seconds()

        # Handle cycle rollover
        if time_in_cycle >= cycle_period:
            time_in_cycle = time_in_cycle % cycle_period

        return {"time_in_cycle": time_in_cycle, "cycle_period": cycle_period}

    def get_rotation_info(self) -> dict[str, int | list[str]]:
        """
        Get information about current heater rotation state.

        Returns:
            Dictionary with rotation_index and current_priority_order
        """
        return {
            "rotation_index": self._rotation_index,
            "current_priority_order": [h.entity_id for h in self._get_prioritized_heaters()],
        }

    def get_heater_info(self) -> dict[str, dict[str, float | str]]:
        """
        Get information about all configured heaters.

        Returns:
            Dictionary mapping entity_id to heater info
        """
        return {
            h.entity_id: {
                "name": h.name,
                "power": h.power,
                "toggle_count": self._toggle_counts[h.entity_id],
            }
            for h in self.heaters
        }
