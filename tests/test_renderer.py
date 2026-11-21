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


def test_fit_image_is_thresholded_not_dithered():
    from PIL import ImageDraw

    src = Image.new("RGB", (472, 142), "white")
    d = ImageDraw.Draw(src)
    d.text((10, 10), "TroubleSense Kitchen", fill="black", font=renderer._mono(22))
    d.line((10, 60, 460, 60), fill="black", width=1)
    buf = BytesIO()
    src.save(buf, "PNG")
    out = Image.open(BytesIO(renderer.fit_image_to_label(renderer.LabelSpec(320, 96), buf.getvalue()))).convert("L")
    px = out.load()
    # The thin rule must survive as a continuous line (about y=40 after scaling).
    rows = [y for y in range(out.height) if sum(px[x, y] == 0 for x in range(20, 300)) > 250]
    assert rows, "1px rule was lost or dithered away"


def test_split_floor():
    assert renderer.split_floor("L1 Kitchen") == ("L1", "Kitchen")
    assert renderer.split_floor("B2 Boiler Room") == ("B2", "Boiler Room")
    assert renderer.split_floor("Kitchen") == ("", "Kitchen")
    assert renderer.split_floor("Garage Left") == ("", "Garage Left")
    assert renderer.split_floor("L1") == ("", "L1")


def test_entity_id_from_url():
    uid = "01cafe97-e8fe-43c1-bdb7-2495e38b6889"
    assert renderer.entity_id_from_url(f"https://hb.example/item/{uid}") == uid
    assert renderer.entity_id_from_url("https://hb.example/a/000-042") is None


def test_floor_badge_is_inverted():
    spec = renderer.LabelSpec(320, 96)
    img = Image.open(BytesIO(renderer.render_item_label(spec, "Lamp", "000-1", "L1 Kitchen", "u"))).convert("L")
    # The floor badge sits at the start of the text column; find a solid black run there.
    px = img.load()
    text_x = 4 + int(96 * 0.9) + 4
    assert any(px[x, y] == 0 and px[x + 1, y] == 0 and px[x, y + 1] == 0
               for x in range(text_x, text_x + 20) for y in range(20, 40))
