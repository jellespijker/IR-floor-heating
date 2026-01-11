"""PID control coordination logic."""

from __future__ import annotations
from dataclasses import dataclass
import logging

from .pid import PIDController

_LOGGER = logging.getLogger(__name__)

@dataclass
class PIDResult:
    """Result of dual-PID calculation."""
    room_demand: float
    floor_demand: float
    final_demand: float
    floor_target: float

class DualPIDController:
    """Coordinates room and floor PID controllers."""

    def __init__(self, room_pid: PIDController, floor_pid: PIDController):
        """Initialize with two PID controllers."""
        self.room_pid = room_pid
        self.floor_pid = floor_pid

    def get_floor_target(
        self,
        room_temp: float,
        target_room: float,
        max_floor_temp: float,
        comfort_offset: float,
        maintain_comfort: bool,
        boost_mode: bool = False,
        boost_temp_diff: float = 1.5,
    ) -> float:
        """Calculate the target floor temperature."""
        if maintain_comfort:
            if target_room > room_temp:
                # Heating up: Floor stays at comfort offset above target room temp
                floor_target = target_room + comfort_offset
            else:
                # Room at or above target: Maintain comfort based on current room temp
                floor_target = room_temp + comfort_offset
        else:
            # Normal operation: Floor target follows room temp + offset
            floor_target = room_temp + comfort_offset
            
            # Relax limit in boost mode
            if boost_mode:
                temp_error = target_room - room_temp
                if temp_error >= boost_temp_diff:
                    relaxed_diff = comfort_offset + temp_error
                    # Allow up to 2.5x the normal offset during boost
                    floor_target = room_temp + min(relaxed_diff, comfort_offset * 2.5)

        # Apply absolute maximum guard
        return min(max_floor_temp, floor_target)

    def calculate(
        self,
        room_temp: float,
        target_room: float,
        floor_temp: float,
        max_floor_temp: float,
        comfort_offset: float,
        maintain_comfort: bool,
        boost_mode: bool = False,
        boost_temp_diff: float = 1.5,
        dt: float = 1.0,
    ) -> PIDResult:
        """
        Calculate demand based on room and floor conditions.
        
        Args:
            room_temp: Current room temperature
            target_room: Target room temperature
            floor_temp: Current floor temperature
            max_floor_temp: Maximum allowed floor temperature
            comfort_offset: Comfort offset for floor (max floor - room diff)
            maintain_comfort: Whether to maintain floor comfort when room is at target
            boost_mode: Whether boost mode is enabled
            boost_temp_diff: Threshold for boost mode
            dt: Time delta
            
        Returns:
            PIDResult containing demands and target
        """
        # 1. Determine floor target
        floor_target = self.get_floor_target(
            room_temp=room_temp,
            target_room=target_room,
            max_floor_temp=max_floor_temp,
            comfort_offset=comfort_offset,
            maintain_comfort=maintain_comfort,
            boost_mode=boost_mode,
            boost_temp_diff=boost_temp_diff,
        )

        # 2. Calculate individual demands
        room_demand = self.room_pid.calculate(target_room, room_temp, dt)
        floor_demand = self.floor_pid.calculate(floor_target, floor_temp, dt)

        # 3. Combine demands
        # When maintain comfort is enabled and room is at/above target,
        # the floor PID becomes the primary demand generator.
        if maintain_comfort and room_temp >= target_room:
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
