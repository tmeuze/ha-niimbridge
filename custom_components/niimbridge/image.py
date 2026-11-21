"""Preview image entity showing the most recent rendered label."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .bridge import NiimBridge
from .const import DOMAIN, SIGNAL_LABEL_UPDATED


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([NiimBridgePreview(hass, entry, hass.data[DOMAIN][entry.entry_id])])


class NiimBridgePreview(ImageEntity):
    _attr_has_entity_name = True
    _attr_name = "Label preview"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, bridge: NiimBridge) -> None:
        super().__init__(hass)
        self._bridge = bridge
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_preview"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_LABEL_UPDATED}_{self._entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._bridge.last_png
