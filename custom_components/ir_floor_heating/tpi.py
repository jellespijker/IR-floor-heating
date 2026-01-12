"""TPI (Time Proportional & Integral) controller for relay actuation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class TPIController:
    """
    Time Proportional & Integral Controller.

    Manages the duty cycle of a relay based on demand percentage.
    Latches the demand at the start of each cycle to enforce stricter timing.
    """

    def __init__(self, cycle_period: timedelta, min_cycle_duration: timedelta) -> None:
        """Initialize the TPI controller."""
        self._cycle_period = cycle_period
        self._min_cycle_duration = min_cycle_duration
        self._cycle_start_time: datetime | None = None

        # Store the calculated ON duration for the current cycle
        self._current_on_duration: float = 0.0

    def reset_cycle(self) -> None:
        """Force a reset of the current cycle (e.g. on setpoint change)."""
        self._cycle_start_time = None
        self._current_on_duration = 0.0

    def get_cycle_info(self) -> dict[str, float]:
        """Return diagnostic info about the current cycle."""
        now = dt_util.utcnow()
        time_in_cycle = 0.0
        if self._cycle_start_time:
            time_in_cycle = (now - self._cycle_start_time).total_seconds()

        return {
            "time_in_cycle": time_in_cycle,
            "cycle_period": self._cycle_period.total_seconds(),
            "current_on_duration": self._current_on_duration,
        }

    def get_relay_state(self, demand_percent: float) -> bool:
        """
        Calculate if relay should be ON based on latched demand for the current cycle.

        Args:
            demand_percent: The current demand from PID (0-100).

        Returns:
            bool: True if heater should be ON, False otherwise.

        """
        now = dt_util.utcnow()
        cycle_period_seconds = self._cycle_period.total_seconds()

        # Check if we need to start a NEW cycle or initialize
        if (
            self._cycle_start_time is None
            or (now - self._cycle_start_time).total_seconds() >= cycle_period_seconds
        ):
            self._cycle_start_time = now

            # LATCH the demand only at the START of the cycle
            demand_clamped = max(0.0, min(100.0, demand_percent))
            on_sec = (demand_clamped / 100.0) * cycle_period_seconds

            # Apply relay protection constraints
            min_duration = self._min_cycle_duration.total_seconds()

            if on_sec < min_duration:
                # If calculated time is too short, stick to 0% (OFF)
                self._current_on_duration = 0.0
            elif on_sec > (cycle_period_seconds - min_duration):
                # If calculated off time is too short, stick to 100% (ON)
                self._current_on_duration = cycle_period_seconds
            else:
                self._current_on_duration = on_sec

            _LOGGER.debug(
                "Starting new TPI cycle: Demand %.1f%% -> Latched ON for %.1fs",
                demand_percent,
                self._current_on_duration,
            )

        # Calculate time within the current block
        time_in_cycle = (now - self._cycle_start_time).total_seconds()

        # IDEAL STATE is based on the LATCHED duration, not the live demand_percent
        return time_in_cycle < self._current_on_duration


class BudgetBucket:
    """Budget bucket for rate limiting relay toggles."""

    def __init__(self, capacity: float, refill_rate: float) -> None:
        """
        Initialize budget bucket.

        Args:
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Number of tokens added per second.

        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_update = datetime.now(UTC)

    def consume(self, amount: float = 1.0, *, force: bool = False) -> bool:
        """
        Consume tokens from the bucket.

        Args:
            amount: Number of tokens to consume.
            force: If True, consume tokens even if it makes the balance negative.

        Returns:
            True if tokens were consumed, False otherwise.

        """
        self._refill()
        if force or self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.now(UTC)
        delta = (now - self.last_update).total_seconds()
        self.tokens = min(self.capacity, self.tokens + delta * self.refill_rate)
        self.last_update = now
