"""PID Controller implementation with anti-windup support."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


class PIDController:
    """Pure mathematical PID controller with anti-windup and saturation handling."""

    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        name: str = "PID",
    ) -> None:
        """
        Initialize the PID controller.

        Args:
            kp: Proportional gain
            ki: Integral gain
            kd: Derivative gain
            name: Name for logging purposes

        """
        self._kp = kp
        self._ki = ki
        self._kd = kd
        self._name = name

        # State variables
        self._integral_error: float = 0.0
        self._last_process_variable: float | None = None

    def calculate(
        self,
        setpoint: float,
        process_variable: float,
        dt: float = 1.0,
    ) -> float:
        """
        Calculate PID output (demand 0-100%).

        Args:
            setpoint: Desired value (target temperature)
            process_variable: Current value (actual temperature)
            dt: Time delta since last calculation (seconds)

        Returns:
            Demand percentage 0-100%

        """
        # Calculate error
        error = setpoint - process_variable

        # Proportional term
        p_term = self._kp * error

        # Integral term with anti-windup clamping
        self._integral_error += error * dt
        max_integral = 100.0 / self._ki if self._ki > 0 else 0.0
        self._integral_error = max(0.0, min(max_integral, self._integral_error))
        i_term = self._ki * self._integral_error

        # Derivative term
        d_term = 0.0
        if self._last_process_variable is not None:
            pv_change = process_variable - self._last_process_variable
            d_term = -self._kd * pv_change / dt if dt > 0 else 0.0

        self._last_process_variable = process_variable

        # Calculate total demand
        demand = p_term + i_term + d_term

        # Clamp to 0-100%
        return max(0.0, min(100.0, demand))

    def pause_integration(self) -> None:
        """
        Pause integral accumulation (call when output is externally saturated).

        This prevents windup when an external constraint limits our output.
        For example, in Dual-PID when the floor limit restricts heating,
        call this on the room PID to prevent integral windup.
        """
        # Reset integral error to prevent windup
        self._integral_error = 0.0

    def get_integral_error(self) -> float:
        """Return the current integral error for diagnostics."""
        return self._integral_error

    def reset(self) -> None:
        """Reset controller state."""
        self._integral_error = 0.0
        self._last_process_variable = None
