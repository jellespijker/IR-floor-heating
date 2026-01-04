"""Integration for IR floor heating with dual-sensor TPI control."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import ServiceCall, ServiceResponse, callback

from .climate import IRFloorHeatingClimate
from .const import DOMAIN as DOMAIN
from .const import PLATFORMS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_MAINTAIN_COMFORT_LIMIT = "set_maintain_comfort_limit"
ATTR_ENABLED = "enabled"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IR floor heating from a config entry."""
    _LOGGER.info("Setting up IR Floor Heating integration")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register service to toggle maintain comfort limit
    @callback
    def handle_set_maintain_comfort_limit(call: ServiceCall) -> ServiceResponse:
        """Handle service call to set maintain comfort limit."""
        enabled = call.data.get(ATTR_ENABLED, True)
        climate_entity = entry.runtime_data

        if isinstance(climate_entity, IRFloorHeatingClimate):
            climate_entity.set_maintain_comfort_limit(enabled)
            return {"success": True, "enabled": enabled}

        _LOGGER.error("Climate entity not found in runtime_data")
        return {"success": False, "error": "Climate entity not found"}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MAINTAIN_COMFORT_LIMIT,
        handle_set_maintain_comfort_limit,
        supports_response="only",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
