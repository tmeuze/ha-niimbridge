"""Core bridge: turns incoming label requests into niimbot.print calls."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

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
    MAX_UPLOAD_BYTES,
    SIGNAL_LABEL_UPDATED,
)
from .renderer import LabelSpec, fit_image_to_label, parse_homebox_text, render_item_label

_LOGGER = logging.getLogger(__name__)


class NiimBridge:
    """One bridge per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.last_png: bytes | None = None
        self._unsubs: list[Any] = []
        self._print_lock = asyncio.Lock()

    @property
    def settings(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def spec(self) -> LabelSpec:
        s = self.settings
        size = s.get(CONF_LABEL_SIZE, DEFAULT_LABEL_SIZE)
        if size in LABEL_SIZE_PRESETS and size != CUSTOM_SIZE:
            width, height = LABEL_SIZE_PRESETS[size]
        else:
            width, height = int(s.get(CONF_WIDTH, 320)), int(s.get(CONF_HEIGHT, 96))
        font = s.get(CONF_FONT) or None
        font_path = self._resolve_font(font) if font else None
        return LabelSpec(
            width,
            height,
            font_path,
            int(s.get(CONF_FONT_SIZE, DEFAULT_FONT_SIZE)),
            int(s.get(CONF_QR_PERCENT, DEFAULT_QR_PERCENT)),
        )

    def _resolve_font(self, name: str) -> str | None:
        for candidate in (
            name,
            self.hass.config.path("www/fonts", name),
            self.hass.config.path("custom_components/niimbot/fonts", name),
        ):
            if os.path.isfile(candidate):
                return candidate
        _LOGGER.warning("Font %s not found; using the default font", name)
        return None

    # -- lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        webhook.async_register(
            self.hass,
            DOMAIN,
            f"NiimBridge ({self.entry.title})",
            self.entry.data[CONF_WEBHOOK_ID],
            self._handle_webhook,
            allowed_methods=["POST"],
        )
        await self._async_start_mqtt()

    async def async_stop(self) -> None:
        webhook.async_unregister(self.hass, self.entry.data[CONF_WEBHOOK_ID])
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _async_start_mqtt(self) -> None:
        s = self.settings
        png_topic = s.get(CONF_MQTT_PNG_TOPIC)
        json_topic = s.get(CONF_MQTT_JSON_TOPIC)
        if not (png_topic or json_topic):
            return
        from homeassistant.components import mqtt

        if png_topic:

            async def _png(msg: Any) -> None:
                await self.async_print_png(bytes(msg.payload))

            self._unsubs.append(await mqtt.async_subscribe(self.hass, png_topic, _png, encoding=None))
        if json_topic:

            async def _json(msg: Any) -> None:
                try:
                    data = json.loads(msg.payload)
                except ValueError:
                    _LOGGER.warning("Ignoring non-JSON message on %s", msg.topic)
                    return
                await self.async_print_item(data)

            self._unsubs.append(await mqtt.async_subscribe(self.hass, json_topic, _json))

    # -- inputs --------------------------------------------------------------

    async def _handle_webhook(
        self, hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        if (request.content_length or 0) > MAX_UPLOAD_BYTES:
            return web.Response(status=413, text="Payload too large")
        ctype = request.content_type or ""
        _LOGGER.debug(
            "Label request received: type=%s length=%s", ctype, request.content_length
        )
        try:
            if ctype.startswith("multipart/") or ctype == "application/x-www-form-urlencoded":
                form = await request.post()
                png = next(
                    (v.file.read() for v in form.values() if hasattr(v, "file")), None
                )
                if png is None:
                    return web.Response(status=400, text="No file field in form")
                self._queue(self.async_print_png(png))
            elif ctype.startswith("image/") or ctype == "application/octet-stream":
                self._queue(self.async_print_png(await request.read()))
            elif ctype == "text/plain":
                # HomeBox template fields: X-Title / X-URL headers, description body.
                data = parse_homebox_text(
                    request.headers.get("X-Title", ""),
                    await request.text(),
                    request.headers.get("X-URL", ""),
                )
                if not data.get("name") and not data.get("asset_id"):
                    raise ValueError("text label needs an X-Title header")
                self._queue(self.async_print_item(data))
            elif ctype == "application/json":
                data = await request.json()
                if not isinstance(data, dict) or not (
                    data.get("name") or data.get("asset_id")
                ):
                    raise ValueError("JSON label needs at least a 'name' or 'asset_id'")
                self._queue(self.async_print_item(data))
            else:
                return web.Response(status=415, text="Unsupported content type")
        except (ValueError, OSError) as err:
            _LOGGER.warning("Rejected label request: %s", err)
            return web.Response(status=400, text="Invalid label data")
        _LOGGER.debug("Label request queued for printing")
        return web.Response(status=202, text="Queued")

    # -- printing ------------------------------------------------------------

    def _queue(self, coro: Any) -> None:
        """Run a print job in the background so the HTTP reply is immediate.

        Replying only after the Bluetooth print finishes can exceed the
        sender's timeout, which makes clients such as wget retry and print
        the same label repeatedly.
        """

        async def _run() -> None:
            try:
                await coro
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Label print failed")

        self.entry.async_create_background_task(self.hass, _run(), "niimbridge_print")

    async def async_print_png(self, png: bytes, *, preview_only: bool = False) -> None:
        spec = self.spec
        label = await self.hass.async_add_executor_job(fit_image_to_label, spec, png)
        await self._async_send(label, preview_only=preview_only)

    async def async_print_item(
        self, data: dict[str, Any], *, preview_only: bool = False
    ) -> None:
        if not isinstance(data, dict) or not (data.get("name") or data.get("asset_id")):
            raise ValueError("JSON label needs at least a 'name' or 'asset_id'")
        spec = self.spec
        label = await self.hass.async_add_executor_job(
            render_item_label,
            spec,
            str(data["name"]),
            str(data.get("asset_id", "")),
            str(data.get("location", "")),
            str(data.get("url", "")),
            str(data.get("floor", "")),
            str(data.get("area", "")),
        )
        await self._async_send(label, preview_only=preview_only, copies=data.get("copies"))

    @callback
    def _store_preview(self, png: bytes) -> None:
        self.last_png = png
        async_dispatcher_send(self.hass, f"{SIGNAL_LABEL_UPDATED}_{self.entry.entry_id}")

    async def _async_send(
        self, png: bytes, *, preview_only: bool, copies: int | None = None
    ) -> None:
        self._store_preview(png)
        if preview_only:
            return
        async with self._print_lock:
            await self._async_call_niimbot(png, copies)

    async def _async_call_niimbot(self, png: bytes, copies: int | None) -> None:
        s = self.settings
        spec = self.spec
        image_uri = "data:image/png;base64," + base64.b64encode(png).decode()
        await self.hass.services.async_call(
            "niimbot",
            "print",
            {
                "payload": [
                    {
                        "type": "dlimg",
                        "url": image_uri,
                        "x": 0,
                        "y": 0,
                        "xsize": spec.width,
                        "ysize": spec.height,
                    }
                ],
                "width": spec.width,
                "height": spec.height,
                "rotate": int(s.get(CONF_ROTATE, DEFAULT_ROTATE)),
                "density": int(s.get(CONF_DENSITY, DEFAULT_DENSITY)),
                "label_type": int(s.get(CONF_LABEL_TYPE, DEFAULT_LABEL_TYPE)),
                "copies": int(copies or s.get(CONF_COPIES, DEFAULT_COPIES)),
            },
            target={"device_id": s[CONF_DEVICE_ID]},
            blocking=True,
        )
