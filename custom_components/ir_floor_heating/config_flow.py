"""Config flow for IR floor heating integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol

from homeassistant.components.climate import HVACMode
from homeassistant.const import (
    CONF_NAME,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
)
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
)

from .const import (
    CONF_BOOST_MODE,
    CONF_BOOST_TEMP_DIFF,
    CONF_COLD_TOLERANCE,
    CONF_CYCLE_PERIOD,
    CONF_FLOOR_SENSOR,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
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
    DEFAULT_MAX_FLOOR_TEMP,
    DEFAULT_MAX_FLOOR_TEMP_DIFF,
    DEFAULT_MIN_CYCLE_DURATION,
    DEFAULT_NAME,
    DEFAULT_PID_KD,
    DEFAULT_PID_KI,
    DEFAULT_PID_KP,
    DEFAULT_SAFETY_HYSTERESIS,
    DEFAULT_TOLERANCE,
    DOMAIN,
)

# Configuration schema for the initial setup
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
        vol.Required(CONF_HEATER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Required(CONF_ROOM_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Required(CONF_FLOOR_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
    }
)

# Options schema for advanced configuration
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HEATER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Required(CONF_ROOM_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Required(CONF_FLOOR_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Optional(
            CONF_MAX_FLOOR_TEMP, default=DEFAULT_MAX_FLOOR_TEMP
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=20.0,
                max=35.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_MAX_FLOOR_TEMP_DIFF, default=DEFAULT_MAX_FLOOR_TEMP_DIFF
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.0,
                max=15.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_MIN_TEMP): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5.0,
                max=25.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_MAX_TEMP): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=15.0,
                max=35.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_TARGET_TEMP): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5.0,
                max=35.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                max=5.0,
                step=0.1,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                max=5.0,
                step=0.1,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_MIN_CYCLE_DURATION, default=DEFAULT_MIN_CYCLE_DURATION
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=30,
                max=600,
                step=30,
                unit_of_measurement="seconds",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_CYCLE_PERIOD, default=DEFAULT_CYCLE_PERIOD
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=300,
                max=1800,
                step=60,
                unit_of_measurement="seconds",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_KEEP_ALIVE): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=60,
                max=3600,
                step=60,
                unit_of_measurement="seconds",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_INITIAL_HVAC_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    HVACMode.HEAT,
                    HVACMode.OFF,
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_PRECISION): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    str(PRECISION_TENTHS),
                    str(PRECISION_HALVES),
                    str(PRECISION_WHOLE),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_TEMP_STEP): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    str(PRECISION_TENTHS),
                    str(PRECISION_HALVES),
                    str(PRECISION_WHOLE),
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_BOOST_MODE, default=True): selector.BooleanSelector(),
        vol.Optional(
            CONF_BOOST_TEMP_DIFF, default=DEFAULT_BOOST_TEMP_DIFF
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1.0,
                max=10.0,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_SAFETY_HYSTERESIS, default=DEFAULT_SAFETY_HYSTERESIS
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                max=2.0,
                step=0.1,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_PID_KP, default=DEFAULT_PID_KP): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                max=50.0,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_PID_KI, default=DEFAULT_PID_KI): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.0,
                max=10.0,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_PID_KD, default=DEFAULT_PID_KD): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.0,
                max=20.0,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
)


CONFIG_FLOW = {
    "user": SchemaFlowFormStep(CONFIG_SCHEMA),
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(OPTIONS_SCHEMA),
}


class IRFloorHeatingConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config flow for IR floor heating."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast(str, options[CONF_NAME])
