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
from homeassistant.helpers import entity_registry as er
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
    AUTO_SIZE,
    CUSTOM_SIZE,
    DEFAULT_COPIES,
    DEFAULT_DENSITY,
    DEFAULT_FONT_SIZE,
    DEFAULT_LABEL_SIZE,
    DEFAULT_LABEL_TYPE,
    DEFAULT_QR_PERCENT,
    DEFAULT_ROTATE,
    DOMAIN,
    DOTS_PER_MM,
    ROUTE_TOLERANCE_MM,
    LABEL_SIZE_PRESETS,
    MAX_UPLOAD_BYTES,
    SIGNAL_LABEL_UPDATED,
)
from .renderer import (
    LabelSpec,
    entity_id_from_url,
    fit_image_to_label,
    parse_homebox_text,
    render_item_label,
)

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
        roll = self._roll_size_px() if size == AUTO_SIZE else None
        if roll:
            width, height = roll
        elif size in LABEL_SIZE_PRESETS and size not in (CUSTOM_SIZE, AUTO_SIZE):
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

    def _roll_size_px(self) -> tuple[int, int] | None:
        """Landscape label size in dots from the printer's loaded roll, if known.

        hass-niimbot's Cloud Label Info sensor carries the roll's size when
        "Fetch Label Info Online" is enabled and an RFID roll is loaded.
        """
        registry = er.async_get(self.hass)
        for entity in er.async_entries_for_device(registry, self.settings[CONF_DEVICE_ID]):
            if entity.platform != "niimbot" or entity.translation_key != "cloud_label_info":
                continue
            state = self.hass.states.get(entity.entity_id)
            attrs = state.attributes if state else {}
            try:
                w_mm = float(attrs.get("label_width_mm"))
                h_mm = float(attrs.get("label_height_mm"))
            except (TypeError, ValueError):
                return None
            if w_mm <= 0 or h_mm <= 0:
                return None
            long_mm, short_mm = max(w_mm, h_mm), min(w_mm, h_mm)
            return (
                min(1600, max(10, round(long_mm * DOTS_PER_MM))),
                min(1600, max(10, round(short_mm * DOTS_PER_MM))),
            )
        return None

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

    def _template_meta(self, headers: Any) -> dict[str, Any]:
        """Label size and copies that HomeBox's print command may send as headers."""

        def num(name: str) -> float | None:
            try:
                value = float(headers.get(name, ""))
            except ValueError:
                return None
            return value if value > 0 else None

        meta: dict[str, Any] = {}
        w_mm, h_mm = num("X-Width-Mm"), num("X-Height-Mm")
        if w_mm and h_mm:
            spec = self.spec
            meta["spec"] = LabelSpec(
                min(1600, max(10, round(w_mm * DOTS_PER_MM))),
                min(1600, max(10, round(h_mm * DOTS_PER_MM))),
                spec.font_path,
                spec.font_size,
                spec.qr_percent,
            )
        if copies := num("X-Copies"):
            meta["copies"] = min(50, max(1, int(copies)))
        return meta

    # -- routing -------------------------------------------------------------

    def label_mm(self) -> tuple[float, float]:
        """This printer's label size in mm as (long side, short side)."""
        spec = self.spec
        long_px, short_px = max(spec.width, spec.height), min(spec.width, spec.height)
        return long_px / DOTS_PER_MM, short_px / DOTS_PER_MM

    def _route(self, headers: Any) -> NiimBridge:
        """Pick the NiimBridge entry whose label size matches the request.

        HomeBox sends the template's size (X-Width-Mm / X-Height-Mm), and its
        docs recommend one template per label stock, so the size identifies the
        printer. The receiving entry wins when it matches; with no match (or no
        size) the request stays with the receiving entry.
        """
        try:
            w_mm, h_mm = float(headers.get("X-Width-Mm")), float(headers.get("X-Height-Mm"))
        except (TypeError, ValueError):
            return self
        long_mm, short_mm = max(w_mm, h_mm), min(w_mm, h_mm)

        def matches(bridge: NiimBridge) -> bool:
            b_long, b_short = bridge.label_mm()
            return (
                abs(b_long - long_mm) <= ROUTE_TOLERANCE_MM
                and abs(b_short - short_mm) <= ROUTE_TOLERANCE_MM
            )

        if matches(self):
            return self
        for bridge in self.hass.data.get(DOMAIN, {}).values():
            if bridge is not self and matches(bridge):
                _LOGGER.debug(
                    "Routing %.1fx%.1f mm label from %s to %s",
                    long_mm,
                    short_mm,
                    self.entry.entry_id,
                    bridge.entry.entry_id,
                )
                return bridge
        return self

    # -- inputs --------------------------------------------------------------

    async def _handle_webhook(
        self, hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        target = self._route(request.headers)
        return await target._handle_request(request)

    async def _handle_request(self, request: web.Request) -> web.Response:
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
                self._queue(self.async_print_png(png, **self._template_meta(request.headers)))
            elif ctype.startswith("image/") or ctype == "application/octet-stream":
                self._queue(
                    self.async_print_png(
                        await request.read(), **self._template_meta(request.headers)
                    )
                )
            elif ctype == "text/plain":
                # HomeBox print command fields: X-Title / X-URL headers; the body
                # carries the description on pre-0.27 HomeBox versions.
                title = request.headers.get("X-Title", "")
                url = request.headers.get("X-URL", "")
                body = await request.text()
                if not (title or url):
                    raise ValueError("text label needs an X-Title or X-URL header")
                meta = self._template_meta(request.headers)
                self._queue(
                    self.async_print_homebox_text(
                        title, body, url, copies=meta.get("copies")
                    )
                )
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

    async def async_print_png(
        self,
        png: bytes,
        *,
        preview_only: bool = False,
        spec: LabelSpec | None = None,
        copies: int | None = None,
    ) -> None:
        spec = spec or self.spec
        label = await self.hass.async_add_executor_job(fit_image_to_label, spec, png)
        await self._async_send(label, preview_only=preview_only, copies=copies, spec=spec)

    async def _lookup_homebox_entity(self, url: str) -> dict[str, str] | None:
        """Fetch name, asset ID and location for a HomeBox page URL, if possible.

        Uses the API client of the HomeBox integration when it is installed, so
        NiimBridge needs no credentials of its own.
        """
        entity_id = entity_id_from_url(url)
        if not entity_id:
            return None
        for entry in self.hass.config_entries.async_entries("homebox"):
            api = getattr(getattr(entry, "runtime_data", None), "api", None)
            if api is None:
                continue
            try:
                entity = await api.async_get_hb_item(entity_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("HomeBox lookup failed for %s: %s", entity_id, err)
                continue
            parent = entity.get("parent") or entity.get("location") or {}
            return {
                "name": str(entity.get("name") or ""),
                "asset_id": str(entity.get("assetId") or ""),
                "location": str(parent.get("name") or "") if isinstance(parent, dict) else "",
            }
        return None

    async def async_print_homebox_text(
        self, title: str, body: str, url: str, *, copies: int | None = None
    ) -> None:
        """Print a label from HomeBox's print-command fields."""
        data = parse_homebox_text(title, body, url)
        if found := await self._lookup_homebox_entity(url):
            _LOGGER.debug("HomeBox lookup for %s: %s", url, found)
            data.update({k: v for k, v in found.items() if v})
        else:
            _LOGGER.debug("No HomeBox lookup result for %s; using request fields only", url)
        if copies:
            data["copies"] = copies
        await self.async_print_item(data)

    async def async_print_item(
        self, data: dict[str, Any], *, preview_only: bool = False
    ) -> None:
        if not isinstance(data, dict) or not (data.get("name") or data.get("asset_id")):
            raise ValueError("JSON label needs at least a 'name' or 'asset_id'")
        spec = self.spec
        label = await self.hass.async_add_executor_job(
            render_item_label,
            spec,
            str(data.get("name", "")),
            str(data.get("asset_id", "")),
            str(data.get("location", "")),
            str(data.get("url", "")),
            str(data.get("area", "")),
            str(data.get("floor", "")),
        )
        await self._async_send(label, preview_only=preview_only, copies=data.get("copies"))

    @callback
    def _store_preview(self, png: bytes) -> None:
        self.last_png = png
        async_dispatcher_send(self.hass, f"{SIGNAL_LABEL_UPDATED}_{self.entry.entry_id}")

    async def _async_send(
        self,
        png: bytes,
        *,
        preview_only: bool,
        copies: int | None = None,
        spec: LabelSpec | None = None,
    ) -> None:
        self._store_preview(png)
        if preview_only:
            return
        async with self._print_lock:
            await self._async_call_niimbot(png, copies, spec or self.spec)

    async def _async_call_niimbot(
        self, png: bytes, copies: int | None, spec: LabelSpec
    ) -> None:
        s = self.settings
        image_uri = "data:image/png;base64," + base64.b64encode(png).decode()
        data: dict[str, Any] = {
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
            "copies": int(copies or s.get(CONF_COPIES, DEFAULT_COPIES)),
        }
        # Density and label type are only sent when set. On a D110-M, sending
        # density 3 / label type 1 made hass-niimbot fail with "No response for
        # request 0xe3", while leaving them out printed fine.
        if (density := int(s.get(CONF_DENSITY, DEFAULT_DENSITY))) > 0:
            data["density"] = density
        if (label_type := int(s.get(CONF_LABEL_TYPE, DEFAULT_LABEL_TYPE))) > 0:
            data["label_type"] = label_type
        await self.hass.services.async_call(
            "niimbot",
            "print",
            data,
            target={"device_id": s[CONF_DEVICE_ID]},
            blocking=True,
        )
