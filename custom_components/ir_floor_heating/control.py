"""PID control coordination logic."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pid import PIDController

_LOGGER = logging.getLogger(__name__)


@dataclass
class PIDResult:
    """Result of dual-PID calculation."""

    room_demand: float
    floor_demand: float
    final_demand: float
    floor_target: float


@dataclass(kw_only=True)
class ControlConfig:
    """Configuration for dual-PID calculation."""

    max_floor_temp: float
    comfort_offset: float
    maintain_comfort: bool
    safety_hysteresis: float = 0.25
    boost_mode: bool = False
    boost_temp_diff: float = 1.5


class DualPIDController:
    """Coordinates room and floor PID controllers."""

    def __init__(self, room_pid: PIDController, floor_pid: PIDController) -> None:
        """Initialize with two PID controllers."""
        self.room_pid = room_pid
        self.floor_pid = floor_pid

    def get_floor_target(
        self,
        *,
        room_temp: float,
        target_room: float,
        config: ControlConfig,
    ) -> float:
        """Calculate the target floor temperature."""
        if config.maintain_comfort:
            if target_room > room_temp:
                # Heating up: Floor stays at comfort offset above target room temp
                floor_target = target_room + config.comfort_offset
            else:
                # Room at or above target: Maintain comfort based on current room temp
                floor_target = room_temp + config.comfort_offset
        else:
            # Normal operation: Floor target follows room temp + offset
            floor_target = room_temp + config.comfort_offset

            # Relax limit in boost mode
            if config.boost_mode:
                temp_error = target_room - room_temp
                if temp_error >= config.boost_temp_diff:
                    relaxed_diff = config.comfort_offset + temp_error
                    # Allow up to 2.5x the normal offset during boost
                    max_boost_offset = config.comfort_offset * 2.5
                    floor_target = room_temp + min(relaxed_diff, max_boost_offset)

        # Apply absolute maximum guard
        if floor_target >= config.max_floor_temp:
            return config.max_floor_temp - config.safety_hysteresis

        return floor_target

    def calculate(
        self,
        *,
        room_temp: float,
        target_room: float,
        floor_temp: float,
        config: ControlConfig,
        dt: float = 1.0,
    ) -> PIDResult:
        """
        Calculate demand based on room and floor conditions.

        Args:
            room_temp: Current room temperature
            target_room: Target room temperature
            floor_temp: Current floor temperature
            config: Configuration for the calculation
            dt: Time delta

        Returns:
            PIDResult containing demands and target

        """
        # 1. Determine floor target
        floor_target = self.get_floor_target(
            room_temp=room_temp,
            target_room=target_room,
            config=config,
        )

        # 2. Calculate individual demands
        room_demand = self.room_pid.calculate(target_room, room_temp, dt)
        floor_demand = self.floor_pid.calculate(floor_target, floor_temp, dt)

        # 3. Combine demands
        # When maintain comfort is enabled and room is at/above target,
        # the floor PID becomes the primary demand generator.
        if config.maintain_comfort and room_temp >= target_room:
            final_demand = floor_demand
            # Pause room PID to prevent windup since its output is being ignored
            self.room_pid.pause_integration()
        else:
            # Normal operation: Min-Selector chooses the most restrictive demand
            final_demand = min(room_demand, floor_demand)

            # Anti-windup coordination: if floor limits us, pause room integral
            if final_demand < room_demand:
                self.room_pid.pause_integration()

        return PIDResult(
            room_demand=room_demand,
            floor_demand=floor_demand,
            final_demand=final_demand,
            floor_target=floor_target,
        )
