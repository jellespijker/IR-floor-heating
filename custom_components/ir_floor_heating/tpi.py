"""TPI (Time Proportional & Integral) controller for relay actuation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

_LOGGER = logging.getLogger(__name__)


class TPIController:
    """Time Proportional & Integral controller for slow PWM relay actuation."""

    def __init__(
        self,
        cycle_period: timedelta,
        min_cycle_duration: timedelta,
    ) -> None:
        """
        Initialize the TPI controller.

        Args:
            cycle_period: Duration of one control cycle (e.g., 900 seconds = 15 min)
            min_cycle_duration: Minimum on/off time for relay protection

        """
        self._cycle_period = cycle_period
        self._min_cycle_duration = min_cycle_duration
        self._cycle_start_time: datetime | None = None

    def get_relay_state(self, demand_percent: float) -> bool:
        """
        Determine if relay should be ON based on current cycle position.

        Args:
            demand_percent: Heating demand (0-100%)

        Returns:
            True if relay should be ON, False if OFF

        """
        current_time = datetime.now(UTC)

        # Initialize cycle start time
        if self._cycle_start_time is None:
            self._cycle_start_time = current_time

        # Calculate time within current cycle
        time_in_cycle = (current_time - self._cycle_start_time).total_seconds()

        # Start new cycle if period elapsed
        if time_in_cycle >= self._cycle_period.total_seconds():
            self._cycle_start_time = current_time
            time_in_cycle = 0.0

        # Calculate ON duration for this cycle based on demand
        on_duration_seconds = (
            demand_percent / 100.0
        ) * self._cycle_period.total_seconds()

        # Apply minimum cycle duration constraints (relay protection)
        min_duration = self._min_cycle_duration.total_seconds()
        if on_duration_seconds < min_duration:
            on_duration_seconds = 0.0  # Too short, stay OFF
        elif on_duration_seconds > (self._cycle_period.total_seconds() - min_duration):
            on_duration_seconds = (
                self._cycle_period.total_seconds()
            )  # Stay ON full cycle

        # Determine relay state for current position in cycle
        return time_in_cycle < on_duration_seconds

    def reset_cycle(self) -> None:
        """Reset the control cycle (e.g., on force update)."""
        self._cycle_start_time = None

    def get_cycle_info(self) -> dict[str, float]:
        """
        Get diagnostic information about current cycle position.

        Returns:
            Dictionary with cycle position and period information

        """
        if self._cycle_start_time is None:
            return {"time_in_cycle": 0.0, "cycle_period": 0.0}

        current_time = datetime.now(UTC)
        time_in_cycle = (current_time - self._cycle_start_time).total_seconds()
        cycle_period = self._cycle_period.total_seconds()

        # Handle cycle rollover
        if time_in_cycle >= cycle_period:
            time_in_cycle = time_in_cycle % cycle_period

        return {"time_in_cycle": time_in_cycle, "cycle_period": cycle_period}
