"""Renderer tests (no Home Assistant needed)."""

import importlib.util
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

_spec = importlib.util.spec_from_file_location(
    "renderer",
    Path(__file__).parent.parent / "custom_components" / "niimbridge" / "renderer.py",
)
renderer = importlib.util.module_from_spec(_spec)
sys.modules["renderer"] = renderer
_spec.loader.exec_module(renderer)


def _size(png: bytes) -> tuple[int, int]:
    return Image.open(BytesIO(png)).size


def test_item_label_matches_spec_size():
    spec = renderer.LabelSpec(320, 96)
    png = renderer.render_item_label(spec, "Drill", "A1", "Shed", "https://x/y")
    assert _size(png) == (320, 96)


def test_item_label_handles_long_name_and_no_extras():
    spec = renderer.LabelSpec(240, 120)
    assert _size(renderer.render_item_label(spec, "word " * 40)) == (240, 120)


def test_qr_percent_is_clamped():
    spec = renderer.LabelSpec(320, 96, qr_percent=500)
    assert _size(renderer.render_item_label(spec, "x", url="u")) == (320, 96)


def test_fit_image_scales_to_label():
    src = renderer.render_item_label(renderer.LabelSpec(640, 200), "Src")
    spec = renderer.LabelSpec(400, 240)
    assert _size(renderer.fit_image_to_label(spec, src)) == (400, 240)


def test_strip_location_from_name():
    assert renderer.strip_location_from_name("L1 Kitchen Lamp", "L1 Kitchen") == "Lamp"
    assert renderer.strip_location_from_name("Kitchen", "Kitchen") == "Kitchen"


def test_parse_homebox_asset_label():
    data = renderer.parse_homebox_text(
        "000-042", "\nKitchen Lamp\nLocation: L1 Kitchen", "https://hb/a/000-042"
    )
    assert data["asset_id"] == "000-042"
    assert data["name"] == "Kitchen Lamp"
    assert data["location"] == "L1 Kitchen"


def test_parse_homebox_item_label():
    data = renderer.parse_homebox_text("Drill", "\nLocation: Shed", "https://hb/item/abc")
    assert data["name"] == "Drill" and data["asset_id"] == ""
    assert data["location"] == "Shed"


def test_long_name_stays_one_line_and_fits():
    spec = renderer.LabelSpec(320, 96)
    png = renderer.render_item_label(spec, "word " * 60, "000-001", "L1 A", "u")
    assert _size(png) == (320, 96)


def test_asset_id_is_inverted_and_right_aligned():
    spec = renderer.LabelSpec(320, 96)
    png = renderer.render_item_label(spec, "Lamp", "000-042", "L3 Kitchen", "u")
    img = Image.open(BytesIO(png)).convert("L")
    # Top-right corner of the text box is the black asset-ID block.
    assert img.getpixel((spec.width - 20, 12)) == 0


def test_long_name_wraps_to_multiple_lines():
    from PIL import ImageDraw
    spec = renderer.LabelSpec(320, 96)
    draw = ImageDraw.Draw(Image.new("1", (10, 10)))
    lines, font = renderer._wrapped_fit(
        draw, "Under-Cabinet Light Strip Controller", lambda s: renderer._font(spec, s), 220, 55, 40
    )
    assert len(lines) >= 2
    assert all(draw.textlength(line, font=font) <= 220 for line in lines)
