"""Tests for header handling in the bridge (needs homeassistant importable)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("homeassistant")  # CI installs only Pillow, segno and pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.niimbridge.bridge import NiimBridge  # noqa: E402


def _bridge():
    entry = MagicMock()
    entry.data = {"device_id": "d", "webhook_id": "w", "label_size": "40x12"}
    entry.options = {}
    hass = MagicMock()
    hass.config.path = lambda *a: "/x"
    return NiimBridge(hass, entry)


def test_template_meta_uses_header_size_and_copies():
    meta = _bridge()._template_meta({"X-Width-Mm": "40", "X-Height-Mm": "12", "X-Copies": "3"})
    assert (meta["spec"].width, meta["spec"].height) == (320, 96)
    assert meta["copies"] == 3


def test_template_meta_ignores_bad_headers():
    assert _bridge()._template_meta({"X-Width-Mm": "abc", "X-Height-Mm": "12"}) == {}
    assert _bridge()._template_meta({}) == {}


def test_homebox_lookup_uses_homebox_integration():
    import asyncio
    from unittest.mock import AsyncMock

    bridge = _bridge()
    api = MagicMock()
    api.async_get_hb_item = AsyncMock(
        return_value={"name": "Lamp", "assetId": "000-043", "parent": {"name": "L1 Kitchen"}}
    )
    entry = MagicMock()
    entry.runtime_data.api = api
    bridge.hass.config_entries.async_entries.return_value = [entry]
    uid = "01cafe97-e8fe-43c1-bdb7-2495e38b6889"
    found = asyncio.run(bridge._lookup_homebox_entity(f"https://hb/item/{uid}"))
    assert found == {"name": "Lamp", "asset_id": "000-043", "location": "L1 Kitchen"}
    api.async_get_hb_item.assert_awaited_once_with(uid)


def test_homebox_lookup_failure_falls_back():
    import asyncio
    from unittest.mock import AsyncMock

    bridge = _bridge()
    entry = MagicMock()
    entry.runtime_data.api.async_get_hb_item = AsyncMock(side_effect=RuntimeError("boom"))
    bridge.hass.config_entries.async_entries.return_value = [entry]
    uid = "01cafe97-e8fe-43c1-bdb7-2495e38b6889"
    assert asyncio.run(bridge._lookup_homebox_entity(f"https://hb/item/{uid}")) is None
    assert asyncio.run(bridge._lookup_homebox_entity("https://hb/a/000-1")) is None
