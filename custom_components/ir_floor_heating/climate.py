"""Support for IR floor heating with dual-sensor control and TPI algorithm."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    EVENT_HOMEASSISTANT_START,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
)
from homeassistant.core import (
    CoreState,
    Event,
    EventStateChangedData,
    State,
    callback,
)
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_BOOST_MODE,
    CONF_BOOST_TEMP_DIFF,
    CONF_CYCLE_PERIOD,
    CONF_FLOOR_PID_KD,
    CONF_FLOOR_PID_KI,
    CONF_FLOOR_PID_KP,
    CONF_FLOOR_SENSOR,
    CONF_HEATER,
    CONF_INITIAL_HVAC_MODE,
    CONF_KEEP_ALIVE,
    CONF_MAX_FLOOR_TEMP,
    CONF_MAX_FLOOR_TEMP_DIFF,
    CONF_MAX_TEMP,
    CONF_MIN_CYCLE_DURATION,
    CONF_MIN_TEMP,
    CONF_PID_KD,
    CONF_PID_KI,
    CONF_PID_KP,
    CONF_PRECISION,
    CONF_ROOM_SENSOR,
    CONF_SAFETY_HYSTERESIS,
    CONF_TARGET_TEMP,
    CONF_TEMP_STEP,
    DEFAULT_BOOST_TEMP_DIFF,
    DEFAULT_CYCLE_PERIOD,
    DEFAULT_FLOOR_PID_KD,
    DEFAULT_FLOOR_PID_KI,
    DEFAULT_FLOOR_PID_KP,
    DEFAULT_MAX_FLOOR_TEMP,
    DEFAULT_MAX_FLOOR_TEMP_DIFF,
    DEFAULT_MIN_CYCLE_DURATION,
    DEFAULT_NAME,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
    DEFAULT_SAFETY_HYSTERESIS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Serialize updates to prevent overwhelming the device
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the IR floor heating climate entity from a config entry."""
    # Read from options if available, otherwise fall back to data
    # This ensures compatibility with both initial setup and options updates
    config = config_entry.options if config_entry.options else config_entry.data

    name: str = config.get(CONF_NAME, DEFAULT_NAME)
    heater_entity_id: str = config[CONF_HEATER]
    room_sensor_entity_id: str = config[CONF_ROOM_SENSOR]
    floor_sensor_entity_id: str = config[CONF_FLOOR_SENSOR]
    min_temp: float | None = config.get(CONF_MIN_TEMP)
    max_temp: float | None = config.get(CONF_MAX_TEMP)
    target_temp: float | None = config.get(CONF_TARGET_TEMP)
    max_floor_temp: float = config.get(CONF_MAX_FLOOR_TEMP, DEFAULT_MAX_FLOOR_TEMP)
    max_floor_temp_diff: float = config.get(
        CONF_MAX_FLOOR_TEMP_DIFF, DEFAULT_MAX_FLOOR_TEMP_DIFF
    )
    min_cycle_duration: int = config.get(
        CONF_MIN_CYCLE_DURATION, DEFAULT_MIN_CYCLE_DURATION
    )
    cycle_period: int = config.get(CONF_CYCLE_PERIOD, DEFAULT_CYCLE_PERIOD)
    keep_alive: int | None = config.get(CONF_KEEP_ALIVE)
    initial_hvac_mode: HVACMode | None = config.get(CONF_INITIAL_HVAC_MODE)
    precision: float | None = config.get(CONF_PRECISION)
    target_temperature_step: float | None = config.get(CONF_TEMP_STEP)
    boost_mode: bool = config.get(CONF_BOOST_MODE, True)
    boost_temp_diff: float = config.get(CONF_BOOST_TEMP_DIFF, DEFAULT_BOOST_TEMP_DIFF)
    safety_hysteresis: float = config.get(
        CONF_SAFETY_HYSTERESIS, DEFAULT_SAFETY_HYSTERESIS
    )
    pid_kp: float = config.get(CONF_PID_KP, DEFAULT_PID_KP)
    pid_ki: float = config.get(CONF_PID_KI, DEFAULT_PID_KI)
    pid_kd: float = config.get(CONF_PID_KD, DEFAULT_PID_KD)
    floor_pid_kp: float = config.get(CONF_FLOOR_PID_KP, DEFAULT_FLOOR_PID_KP)
    floor_pid_ki: float = config.get(CONF_FLOOR_PID_KI, DEFAULT_FLOOR_PID_KI)
    floor_pid_kd: float = config.get(CONF_FLOOR_PID_KD, DEFAULT_FLOOR_PID_KD)
    unit = hass.config.units.temperature_unit
    unique_id = config_entry.entry_id

    climate_entity = IRFloorHeatingClimate(
        hass,
        name=name,
        heater_entity_id=heater_entity_id,
        room_sensor_entity_id=room_sensor_entity_id,
        floor_sensor_entity_id=floor_sensor_entity_id,
        min_temp=min_temp,
        max_temp=max_temp,
        target_temp=target_temp,
        max_floor_temp=max_floor_temp,
        max_floor_temp_diff=max_floor_temp_diff,
        min_cycle_duration=timedelta(seconds=min_cycle_duration),
        cycle_period=timedelta(seconds=cycle_period),
        keep_alive=timedelta(seconds=keep_alive) if keep_alive else None,
        initial_hvac_mode=initial_hvac_mode,
        precision=precision,
        target_temperature_step=target_temperature_step,
        unit=unit,
        unique_id=unique_id,
        boost_mode=boost_mode,
        boost_temp_diff=boost_temp_diff,
        safety_hysteresis=safety_hysteresis,
        pid_kp=pid_kp,
        pid_ki=pid_ki,
        pid_kd=pid_kd,
        floor_pid_kp=floor_pid_kp,
        floor_pid_ki=floor_pid_ki,
        floor_pid_kd=floor_pid_kd,
    )

    # Store climate entity for access by sensor platform
    hass.data[DOMAIN][config_entry.entry_id] = climate_entity

    async_add_entities([climate_entity])


class IRFloorHeatingClimate(ClimateEntity, RestoreEntity):
    """
    Representation of an IR floor heating climate device.

    Includes dual-sensor TPI control.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        *,
        name: str,
        heater_entity_id: str,
        room_sensor_entity_id: str,
        floor_sensor_entity_id: str,
        min_temp: float | None,
        max_temp: float | None,
        target_temp: float | None,
        max_floor_temp: float,
        max_floor_temp_diff: float,
        min_cycle_duration: timedelta,
        cycle_period: timedelta,
        keep_alive: timedelta | None,
        initial_hvac_mode: HVACMode | None,
        precision: float | None,
        target_temperature_step: float | None,
        unit: UnitOfTemperature,
        unique_id: str,
        boost_mode: bool,
        boost_temp_diff: float,
        safety_hysteresis: float,
        pid_kp: float,
        pid_ki: float,
        pid_kd: float,
        floor_pid_kp: float,
        floor_pid_ki: float,
        floor_pid_kd: float,
    ) -> None:
        """Initialize the IR floor heating climate device."""
        self._attr_name = name
        self.heater_entity_id = heater_entity_id
        self.room_sensor_entity_id = room_sensor_entity_id
        self.floor_sensor_entity_id = floor_sensor_entity_id
        self.device_entry = async_entity_id_to_device(hass, heater_entity_id)

        # Temperature limits
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._max_floor_temp = max_floor_temp
        self._max_floor_temp_diff = max_floor_temp_diff

        # Control parameters
        self.min_cycle_duration = min_cycle_duration
        self.cycle_period = cycle_period
        self._keep_alive = keep_alive
        self._boost_mode = boost_mode
        self._boost_temp_diff = boost_temp_diff
        self._safety_hysteresis = safety_hysteresis

        # State variables
        self._hvac_mode = initial_hvac_mode
        self._target_temp = target_temp
        self._temp_precision = precision
        self._temp_target_temperature_step = target_temperature_step
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._active = False
        self._room_temp: float | None = None
        self._floor_temp: float | None = None
        self._temp_lock = asyncio.Lock()
        self._attr_temperature_unit = unit
        self._attr_unique_id = unique_id
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

        # TPI control state
        self._cycle_start_time: datetime | None = None
        self._demand_percent: float = 0.0
        self._safety_veto_active: bool = False

        # PID state
        self._integral_error: float = 0.0
        self._last_error: float = 0.0
        self._last_room_temp: float | None = None
        self._last_logged_demand: float = 0.0

        # PID tuning constants (configurable)
        self._kp: float = pid_kp
        self._ki: float = pid_ki
        self._kd: float = pid_kd

        _LOGGER.info(
            "IR Floor Heating initialized: '%s' - Room sensor: %s, Floor sensor: %s, "
            "Max floor temp: %.1f°C, Max diff: %.1f°C, Cycle period: %ds, "
            "Room PID (Kp=%.1f, Ki=%.1f, Kd=%.1f), "
            "Floor PID (Kp=%.1f, Ki=%.1f, Kd=%.1f)",
            name,
            room_sensor_entity_id,
            floor_sensor_entity_id,
            max_floor_temp,
            max_floor_temp_diff,
            cycle_period.total_seconds(),
            pid_kp,
            pid_ki,
            pid_kd,
            floor_pid_kp,
            floor_pid_ki,
            floor_pid_kd,
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add sensor listeners
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.room_sensor_entity_id], self._async_room_sensor_changed
            )
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self.floor_sensor_entity_id],
                self._async_floor_sensor_changed,
            )
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.heater_entity_id], self._async_switch_changed
            )
        )

        # Set up keep-alive timer
        if self._keep_alive:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_control_heating, self._keep_alive
                )
            )

        # Set up TPI cycle timer
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_tpi_cycle, timedelta(seconds=1)
            )
        )

        @callback
        def _async_startup(_: Event | None = None) -> None:
            """Init on startup."""
            room_state = self.hass.states.get(self.room_sensor_entity_id)
            if room_state and room_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                self._async_update_room_temp(room_state)

            floor_state = self.hass.states.get(self.floor_sensor_entity_id)
            if floor_state and floor_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                self._async_update_floor_temp(floor_state)

            switch_state = self.hass.states.get(self.heater_entity_id)
            if switch_state and switch_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                self.hass.async_create_task(
                    self._check_switch_initial_state(), eager_start=True
                )

            self.async_write_ha_state()

        if self.hass.state is CoreState.running:
            _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

        # Restore previous state
        if (old_state := await self.async_get_last_state()) is not None:
            if self._target_temp is None:
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    self._target_temp = self.min_temp
                    _LOGGER.warning(
                        "Undefined target temperature, falling back to %s",
                        self._target_temp,
                    )
                else:
                    self._target_temp = float(old_state.attributes[ATTR_TEMPERATURE])
            if not self._hvac_mode and old_state.state:
                self._hvac_mode = HVACMode(old_state.state)
        else:
            if self._target_temp is None:
                self._target_temp = self.min_temp
            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._target_temp
            )

        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVACMode.OFF

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision
        return super().precision

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        if self._temp_target_temperature_step is not None:
            return self._temp_target_temperature_step
        return self.precision

    @property
    def current_temperature(self) -> float | None:
        """Return the room sensor temperature."""
        return self._room_temp

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation."""
        if self._hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if not self._is_device_active:
            return HVACAction.IDLE
        return HVACAction.HEATING

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._min_temp is not None:
            return self._min_temp
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._max_temp is not None:
            return self._max_temp
        return super().max_temp

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "floor_temperature": self._floor_temp,
            "room_temperature": self._room_temp,
            "max_floor_temp": self._max_floor_temp,
            "max_floor_temp_diff": self._max_floor_temp_diff,
            "demand_percent": round(self._demand_percent, 1),
            "safety_veto_active": self._safety_veto_active,
        }

        if self._room_temp is not None:
            effective_limit = self._calculate_effective_floor_limit()
            attrs["effective_floor_limit"] = round(effective_limit, 1)

        return attrs

    @property
    def demand_percent(self) -> float:
        """Return the current heating demand percentage."""
        return round(self._demand_percent, 1)

    @property
    def effective_floor_limit(self) -> float | None:
        """Return the effective floor temperature limit."""
        if self._room_temp is None:
            return None
        return round(self._calculate_effective_floor_limit(), 1)

    @property
    def safety_veto_active(self) -> bool:
        """Return whether safety veto is currently active."""
        return self._safety_veto_active

    @property
    def integral_error(self) -> float:
        """Return the PID integral error term."""
        return round(self._integral_error, 1)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        if hvac_mode == HVACMode.HEAT:
            self._hvac_mode = HVACMode.HEAT
            await self._async_control_heating(force=True)
        elif hvac_mode == HVACMode.OFF:
            self._hvac_mode = HVACMode.OFF
            if self._is_device_active:
                await self._async_heater_turn_off()
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._target_temp = temperature
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    async def _async_room_sensor_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle room temperature changes."""
        new_state = event.data["new_state"]
        if new_state is None:
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # Sensor unavailable - clear temperature and re-evaluate for safety
            self._last_room_temp = self._room_temp
            self._room_temp = None
            _LOGGER.warning(
                "Room sensor unavailable - clearing temperature for safety evaluation"
            )
        else:
            self._async_update_room_temp(new_state)

        try:
            await self._async_control_heating()
        finally:
            self.async_write_ha_state()

    async def _async_floor_sensor_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle floor temperature changes."""
        new_state = event.data["new_state"]
        if new_state is None:
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # Sensor unavailable - clear temperature and re-evaluate for safety
            self._floor_temp = None
            _LOGGER.warning(
                "Floor sensor unavailable - clearing temperature and "
                "activating safety veto"
            )
        else:
            self._async_update_floor_temp(new_state)

        try:
            await self._async_control_heating()
        finally:
            self.async_write_ha_state()

    async def _check_switch_initial_state(self) -> None:
        """Prevent the device from keep running if HVACMode.OFF."""
        if self._hvac_mode == HVACMode.OFF and self._is_device_active:
            _LOGGER.warning(
                "The climate mode is OFF, but the switch device is ON. "
                "Turning off device %s",
                self.heater_entity_id,
            )
            await self._async_heater_turn_off()

    @callback
    def _async_switch_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle heater switch state changes."""
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None:
            return
        if old_state is None:
            self.hass.async_create_task(
                self._check_switch_initial_state(), eager_start=True
            )
        self.async_write_ha_state()

    @callback
    def _async_update_room_temp(self, state: State) -> None:
        """Update thermostat with latest room temperature from sensor."""
        try:
            room_temp = float(state.state)
            if not math.isfinite(room_temp):
                _LOGGER.exception(
                    "Unable to update room temperature from sensor: "
                    "Sensor has illegal state %s",
                    state.state,
                )
                return
            self._last_room_temp = self._room_temp
            self._room_temp = room_temp
        except ValueError:
            _LOGGER.exception("Unable to update room temperature from sensor")

    @callback
    def _async_update_floor_temp(self, state: State) -> None:
        """Update thermostat with latest floor temperature from sensor."""
        try:
            floor_temp = float(state.state)
            if not math.isfinite(floor_temp):
                _LOGGER.exception(
                    "Unable to update floor temperature from sensor: "
                    "Sensor has illegal state %s",
                    state.state,
                )
                return
            self._floor_temp = floor_temp
        except ValueError:
            _LOGGER.exception("Unable to update floor temperature from sensor")

    def _calculate_effective_floor_limit(self) -> float:
        """Calculate effective floor temperature limit based on conditions."""
        if self._room_temp is None:
            return self._max_floor_temp

        # Calculate differential limit
        diff_limit = self._room_temp + self._max_floor_temp_diff

        # Apply boost mode logic if enabled
        if self._boost_mode and self._target_temp is not None:
            temp_error = self._target_temp - self._room_temp
            # Activate boost when error is at or above threshold
            if temp_error >= self._boost_temp_diff:
                # Relax the differential limit during boost
                # Add the full error to the base room temp to allow faster heating
                relaxed_diff = self._max_floor_temp_diff + temp_error
                diff_limit = self._room_temp + min(
                    relaxed_diff, self._max_floor_temp_diff * 2.5
                )
                _LOGGER.info(
                    "Boost mode active: temp error %.1f°C, relaxed floor limit "
                    "from %.1f°C to %.1f°C",
                    temp_error,
                    self._room_temp + self._max_floor_temp_diff,
                    diff_limit,
                )

        # Return the stricter of absolute and differential limits
        return min(self._max_floor_temp, diff_limit)

    def _check_safety_veto(self, *, bypass_hysteresis: bool = False) -> bool:
        """
        Check if safety veto should be active.

        Based on floor temperature limits.

        Args:
            bypass_hysteresis: If True, ignores hysteresis band.
                When True, makes immediate decision.
                Used when setpoint changes to allow immediate veto release.

        """
        if self._floor_temp is None or self._room_temp is None:
            # If we can't read sensors, veto heating for safety
            _LOGGER.warning(
                "SAFETY VETO ACTIVE: Missing sensor data (Floor: %s, Room: %s) - "
                "Heating disabled for safety",
                ("None" if self._floor_temp is None else f"{self._floor_temp:.1f}°C"),
                ("None" if self._room_temp is None else f"{self._room_temp:.1f}°C"),
            )
            return True

        effective_limit = self._calculate_effective_floor_limit()

        # Use hysteresis to prevent chattering
        if self._floor_temp >= effective_limit:
            if not self._safety_veto_active:
                _LOGGER.warning(
                    "SAFETY VETO ENGAGED: Floor temp %.1f°C >= "
                    "Effective limit %.1f°C - Heating OFF",
                    self._floor_temp,
                    effective_limit,
                )
            return True

        if not bypass_hysteresis and self._floor_temp > (
            effective_limit - self._safety_hysteresis
        ):
            # In hysteresis band: maintain previous veto state
            if self._safety_veto_active:
                _LOGGER.debug(
                    "SAFETY VETO MAINTAINED: Floor temp %.1f°C "
                    "in hysteresis band (%.1f°C to %.1f°C)",
                    self._floor_temp,
                    effective_limit - self._safety_hysteresis,
                    effective_limit,
                )
            return self._safety_veto_active

        # Below hysteresis band - release veto
        if self._safety_veto_active:
            _LOGGER.info(
                "SAFETY VETO RELEASED: Floor temp %.1f°C < "
                "(Limit %.1f°C - Hysteresis %.1f°C) - Heating allowed",
                self._floor_temp,
                effective_limit,
                self._safety_hysteresis,
            )

        return False

    def _calculate_pid_demand(self) -> float:
        """Calculate heating demand using PID control."""
        if self._room_temp is None or self._target_temp is None:
            _LOGGER.debug("PID calculation skipped: Missing temperature data")
            return 0.0

        # Calculate error
        error = self._target_temp - self._room_temp

        # Proportional term
        p_term = self._kp * error

        # Integral term (only accumulate if not vetoed to prevent windup)
        if not self._safety_veto_active:
            self._integral_error += error
            # Clamp integral to prevent excessive windup
            max_integral = 100.0 / self._ki if self._ki > 0 else 0
            # Clamp lower bound to 0.0 to prevent negative "cooling" debt
            self._integral_error = max(0.0, min(max_integral, self._integral_error))
        i_term = self._ki * self._integral_error

        # Derivative term
        d_term = 0.0
        if self._last_room_temp is not None:
            temp_change = self._room_temp - self._last_room_temp
            d_term = (
                -self._kd * temp_change
            )  # Negative because we want to dampen rate of change

        # Calculate total demand
        demand = p_term + i_term + d_term

        # Constrain to 0-100%
        demand = max(0.0, min(100.0, demand))

        self._last_error = error

        # Only log if demand changed significantly or periodically
        demand_change_threshold = 5.0
        if abs(demand - self._last_logged_demand) > demand_change_threshold:
            _LOGGER.debug(
                "PID demand: %.1f%% (error=%.2f°C, P=%.1f, I=%.1f, D=%.1f)",
                demand,
                error,
                p_term,
                i_term,
                d_term,
            )
            self._last_logged_demand = demand

        return demand

    async def _async_control_heating(
        self, _time: datetime | None = None, *, force: bool = False
    ) -> None:
        """Control heating using TPI algorithm with safety veto architecture."""
        async with self._temp_lock:
            # Activate control once we have both temperatures
            if not self._active and None not in (
                self._room_temp,
                self._floor_temp,
                self._target_temp,
            ):
                self._active = True
                # Reset cycle to start fresh when heating becomes active
                self._cycle_start_time = None
                _LOGGER.info(
                    "IR floor heating active. Room: %.1f°C, Floor: %.1f°C, "
                    "Target: %.1f°C",
                    self._room_temp,
                    self._floor_temp,
                    self._target_temp,
                )

            if not self._active or self._hvac_mode == HVACMode.OFF:
                return

            # Check safety veto (bypass hysteresis on forced updates like setpoint
            # changes)
            self._safety_veto_active = self._check_safety_veto(bypass_hysteresis=force)

            if self._safety_veto_active:
                self._demand_percent = 0.0
            else:
                # Calculate PID demand
                self._demand_percent = self._calculate_pid_demand()

            # Force immediate update if requested
            if force:
                self._cycle_start_time = None

    async def _async_tpi_cycle(self, _time: datetime | None = None) -> None:
        """Execute Time Proportional & Integral (TPI) control cycle."""
        if not self._active or self._hvac_mode == HVACMode.OFF:
            return

        current_time = datetime.now(UTC)

        # Initialize cycle start time
        if self._cycle_start_time is None:
            self._cycle_start_time = current_time

        # Calculate time within current cycle
        time_in_cycle = (current_time - self._cycle_start_time).total_seconds()

        # Start new cycle if period elapsed
        if time_in_cycle >= self.cycle_period.total_seconds():
            self._cycle_start_time = current_time
            time_in_cycle = 0.0

        # Calculate ON duration for this cycle based on demand
        on_duration_seconds = (
            self._demand_percent / 100.0
        ) * self.cycle_period.total_seconds()

        # Apply minimum cycle duration constraints (relay protection)
        min_duration = self.min_cycle_duration.total_seconds()
        if on_duration_seconds < min_duration:
            on_duration_seconds = 0.0  # Too short, stay OFF
        elif on_duration_seconds > (self.cycle_period.total_seconds() - min_duration):
            on_duration_seconds = (
                self.cycle_period.total_seconds()
            )  # Stay ON full cycle

        # Determine relay state for current position in cycle
        should_be_on = time_in_cycle < on_duration_seconds

        # Actuate relay if state should change
        if should_be_on and not self._is_device_active:
            _LOGGER.info(
                "Heater ON (demand %.0f%%, cycle %.0f/%.0fs)",
                self._demand_percent,
                time_in_cycle,
                self.cycle_period.total_seconds(),
            )
            await self._async_heater_turn_on()
        elif not should_be_on and self._is_device_active:
            _LOGGER.info(
                "Heater OFF (demand %.0f%%, cycle %.0f/%.0fs)",
                self._demand_percent,
                time_in_cycle,
                self.cycle_period.total_seconds(),
            )
            await self._async_heater_turn_off()

    @property
    def _is_device_active(self) -> bool | None:
        """Check if the toggleable device is currently active."""
        if not self.hass.states.get(self.heater_entity_id):
            return None
        return self.hass.states.is_state(self.heater_entity_id, STATE_ON)

    async def _async_heater_turn_on(self) -> None:
        """Turn heater toggleable device on."""
        _LOGGER.debug("Turning on heater %s", self.heater_entity_id)
        await self.hass.services.async_call(
            HOMEASSISTANT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: self.heater_entity_id},
            context=self._context,
        )

    async def _async_heater_turn_off(self) -> None:
        """Turn heater toggleable device off."""
        _LOGGER.debug("Turning off heater %s", self.heater_entity_id)
        await self.hass.services.async_call(
            HOMEASSISTANT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self.heater_entity_id},
            context=self._context,
        )
