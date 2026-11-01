"""NiimBridge: bridge HomeBox label requests to the Niimbot integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .bridge import NiimBridge
from .const import DOMAIN

PLATFORMS = ["image"]

SERVICE_PRINT_LABEL = "print_label"
PRINT_LABEL_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional("name", default=""): cv.string,
        vol.Optional("asset_id", default=""): cv.string,
        vol.Optional("floor", default=""): cv.string,
        vol.Optional("area", default=""): cv.string,
        vol.Optional("location", default=""): cv.string,
        vol.Optional("url", default=""): cv.string,
        vol.Optional("copies"): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
        vol.Optional("preview_only", default=False): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def _print_label(call: ServiceCall) -> None:
        bridges: dict[str, NiimBridge] = hass.data.get(DOMAIN, {})
        entry_id = call.data.get("config_entry_id")
        if entry_id:
            bridge = bridges.get(entry_id)
        elif len(bridges) == 1:
            bridge = next(iter(bridges.values()))
        else:
            bridge = None
        if bridge is None:
            raise ServiceValidationError(
                "Specify config_entry_id (no bridge, or more than one configured)"
            )
        data = {k: v for k, v in call.data.items() if k not in ("config_entry_id", "preview_only")}
        await bridge.async_print_item(data, preview_only=call.data["preview_only"])

    hass.services.async_register(
        DOMAIN, SERVICE_PRINT_LABEL, _print_label, schema=PRINT_LABEL_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    bridge = NiimBridge(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = bridge
    await bridge.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN].pop(entry.entry_id).async_stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
