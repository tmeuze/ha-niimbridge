"""Config and options flow for NiimBridge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COPIES,
    CONF_DENSITY,
    CONF_DEVICE_ID,
    CONF_FONT,
    CONF_FONT_SIZE,
    CONF_HEIGHT,
    CONF_LABEL_SIZE,
    CONF_LABEL_TYPE,
    CONF_MQTT_JSON_TOPIC,
    CONF_MQTT_PNG_TOPIC,
    CONF_QR_PERCENT,
    CONF_ROTATE,
    CONF_WEBHOOK_ID,
    CONF_WIDTH,
    CUSTOM_SIZE,
    DEFAULT_COPIES,
    DEFAULT_DENSITY,
    DEFAULT_FONT_SIZE,
    DEFAULT_LABEL_SIZE,
    DEFAULT_LABEL_TYPE,
    DEFAULT_QR_PERCENT,
    DEFAULT_ROTATE,
    DOMAIN,
    LABEL_SIZE_PRESETS,
)


def _label_schema(defaults: dict[str, Any], *, with_device: bool) -> vol.Schema:
    def d(key: str, fallback: Any) -> Any:
        return defaults.get(key, fallback)

    def opt(key: str, fallback: Any) -> vol.Optional:
        value = defaults.get(key, fallback)
        return vol.Optional(key, default=value) if value not in (None, "") else vol.Optional(key)

    fields: dict[Any, Any] = {}
    if with_device:
        fields[vol.Required(CONF_DEVICE_ID)] = selector.DeviceSelector(
            selector.DeviceSelectorConfig(integration="niimbot")
        )
    fields.update(
        {
            vol.Required(CONF_LABEL_SIZE, default=d(CONF_LABEL_SIZE, DEFAULT_LABEL_SIZE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        *[
                            selector.SelectOptionDict(value=k, label=f"{k} mm")
                            for k in LABEL_SIZE_PRESETS
                        ],
                        selector.SelectOptionDict(value=CUSTOM_SIZE, label="Custom (pixels)"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_WIDTH, default=d(CONF_WIDTH, 320)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=10, max=1600, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_HEIGHT, default=d(CONF_HEIGHT, 96)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=10, max=1600, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_ROTATE, default=str(d(CONF_ROTATE, DEFAULT_ROTATE))): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["0", "90", "180", "270"])
            ),
            vol.Required(CONF_DENSITY, default=d(CONF_DENSITY, DEFAULT_DENSITY)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=5, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_LABEL_TYPE, default=str(d(CONF_LABEL_TYPE, DEFAULT_LABEL_TYPE))): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="1", label="With gaps"),
                        selector.SelectOptionDict(value="2", label="Black"),
                        selector.SelectOptionDict(value="3", label="Continuous"),
                    ]
                )
            ),
            vol.Required(CONF_COPIES, default=d(CONF_COPIES, DEFAULT_COPIES)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=50, mode=selector.NumberSelectorMode.BOX)
            ),
            opt(CONF_FONT, ""): selector.TextSelector(),
            vol.Required(CONF_FONT_SIZE, default=d(CONF_FONT_SIZE, DEFAULT_FONT_SIZE)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=200, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_QR_PERCENT, default=d(CONF_QR_PERCENT, DEFAULT_QR_PERCENT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=30, max=100, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX)
            ),
            opt(CONF_MQTT_PNG_TOPIC, ""): selector.TextSelector(),
            opt(CONF_MQTT_JSON_TOPIC, ""): selector.TextSelector(),
        }
    )
    return vol.Schema(fields)


def _webhook_placeholders(hass: Any, webhook_id: str) -> dict[str, str]:
    url = webhook.async_generate_url(hass, webhook_id)
    return {
        "webhook_url": url,
        "command": "HBOX_LABEL_MAKER_PRINT_COMMAND=wget -q -O /dev/null --tries=1 --timeout=10 "
        "--header=Content-Type:text/plain --header=X-Title:{{.TitleText}} "
        "--header=X-URL:{{.URL}} --post-data={{.DescriptionText}} " + url,
    }


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    out = dict(user_input)
    for key in (CONF_ROTATE, CONF_LABEL_TYPE, CONF_DENSITY, CONF_COPIES, CONF_FONT_SIZE, CONF_QR_PERCENT, CONF_WIDTH, CONF_HEIGHT):
        if key in out:
            out[key] = int(out[key])
    return out


class NiimBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {**_normalize(user_input), CONF_WEBHOOK_ID: webhook.async_generate_id()}
            return await self.async_step_webhook()
        return self.async_show_form(
            step_id="user", data_schema=_label_schema({}, with_device=True)
        )

    async def async_step_webhook(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="NiimBridge", data=self._data)
        return self.async_show_form(
            step_id="webhook",
            description_placeholders=_webhook_placeholders(
                self.hass, self._data[CONF_WEBHOOK_ID]
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return NiimBridgeOptionsFlow()


class NiimBridgeOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_normalize(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_label_schema(current, with_device=False),
            description_placeholders=_webhook_placeholders(
                self.hass, self.config_entry.data[CONF_WEBHOOK_ID]
            ),
        )
