"""Label rendering. Pure Pillow/segno so it can be tested without Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps
import segno


@dataclass(frozen=True)
class LabelSpec:
    """Geometry and typography for a label."""

    width: int
    height: int
    font_path: str | None = None
    font_size: int = 0  # 0 = auto-fit
    qr_percent: int = 90


def _font(spec: LabelSpec, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if spec.font_path:
        try:
            return ImageFont.truetype(spec.font_path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def _qr_image(data: str, size: int) -> Image.Image:
    buf = BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=1, border=0)
    buf.seek(0)
    qr = Image.open(buf).convert("1")
    scale = max(1, size // qr.width)
    qr = qr.resize((qr.width * scale, qr.height * scale), Image.NEAREST)
    return qr


MONO_FONT = str(Path(__file__).parent / "fonts" / "DejaVuSansMono.ttf")


def strip_location_from_name(name: str, *places: str) -> str:
    """Remove area words from an item name, e.g. "Kitchen Lamp" -> "Lamp"."""
    result = name
    for place in sorted((p for p in places if p), key=len, reverse=True):
        result = re.sub(re.escape(place), "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s+", " ", result).strip(" -–—:|/·,")
    return result or name


_ASSET_ID_RE = re.compile(r"^[0-9]{3}-[0-9]{3,}$|^[0-9]{4,}$")


def parse_homebox_text(title: str, description: str, url: str = "") -> dict[str, str]:
    """Turn HomeBox's label template fields into label data.

    HomeBox asset labels have the asset ID as the title and "name\nLocation: X"
    as the description; item labels have the name as the title. The
    "Location:" key is dropped.
    """
    title = title.strip()
    location = ""
    others: list[str] = []
    for line in description.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("location:"):
            location = line.split(":", 1)[1].strip()
        else:
            others.append(line)
    asset_id = ""
    name = title
    if _ASSET_ID_RE.match(title):
        asset_id, name = title, (others[0] if others else "")
    elif m := re.search(r"/a/([0-9-]+)", url):
        asset_id = m.group(1)
    return {"name": name, "asset_id": asset_id, "location": location, "url": url}


def _mono(size: int) -> Any:
    try:
        return ImageFont.truetype(MONO_FONT, size)
    except OSError:
        return ImageFont.load_default(size)


def _one_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    make_font: Any,
    box_w: int,
    max_size: int,
    min_size: int = 8,
) -> tuple[str, Any]:
    """Largest single-line fit; shrink first, truncate with an ellipsis last."""
    font = make_font(min_size)
    for size in range(max(max_size, min_size), min_size - 1, -1):
        font = make_font(size)
        if draw.textlength(text, font=font) <= box_w:
            return text, font
    while len(text) > 1 and draw.textlength(text + "…", font=font) > box_w:
        text = text[:-1]
    return text.rstrip() + "…", font


def render_item_label(
    spec: LabelSpec,
    name: str,
    asset_id: str = "",
    location: str = "",
    url: str = "",
    area: str = "",
) -> bytes:
    """Standard layout: QR on the left; asset ID (mono), area, then name.

    Every text row is a single line that shrinks to fit rather than wrapping.
    """
    area = area or location
    img = Image.new("1", (spec.width, spec.height), 1)
    draw = ImageDraw.Draw(img)
    pad = max(4, spec.height // 12)

    qr_data = url or asset_id or name
    qr_size = max(16, spec.height * min(100, max(30, spec.qr_percent)) // 100)
    qr = _qr_image(qr_data, qr_size)
    qr_x = pad if qr_size <= spec.height - 2 * pad else (spec.height - qr.height) // 2
    img.paste(qr, (qr_x, (spec.height - qr.height) // 2))

    text_x = qr_x + qr.width + pad
    box_w = spec.width - text_x - pad
    box_h = spec.height - 2 * pad

    def regular(size: int) -> Any:
        return _font(spec, size)

    place = area
    display_name = strip_location_from_name(name, area) if name else ""

    # (text, font factory, share of the box height, fixed size or None=fit)
    rows = []
    if asset_id:
        rows.append((asset_id, _mono, 0.22))
    if place:
        rows.append((place, regular, 0.24))
    if display_name:
        rows.append((display_name, regular, 0.54))
    total = sum(share for _, _, share in rows) or 1.0

    # Fit the name first so the asset ID can be kept no larger than it.
    name_cap: int | None = None
    if display_name:
        name_h = int(box_h * 0.54 / total)
        limit = spec.font_size if spec.font_size > 0 else int(name_h / 1.15)
        _, name_font = _one_line(draw, display_name, regular, box_w, max_size=limit)
        name_cap = getattr(name_font, "size", None)

    y = pad
    for text, make_font, share in rows:
        row_h = int(box_h * share / total)
        max_size = int(row_h / 1.15)
        if text == display_name and spec.font_size > 0:
            max_size = spec.font_size
        elif make_font is _mono and name_cap:
            max_size = min(max_size, name_cap)
        if make_font is _mono:
            # Asset ID: white on black, right-aligned to the edge of the text box.
            inset = max(2, row_h // 8)
            fitted, font = _one_line(
                draw, text, make_font, box_w - 2 * inset, max_size=max_size
            )
            left, top, right, bottom = draw.textbbox((0, 0), fitted, font=font)
            w, h = right - left, bottom - top
            x1 = text_x + box_w
            x0 = x1 - w - 2 * inset
            draw.rectangle((x0, y, x1 - 1, y + h + 2 * inset - 1), fill=0)
            draw.text((x0 + inset - left, y + inset - top), fitted, font=font, fill=1)
            y += max(row_h, h + 2 * inset)
            continue
        fitted, font = _one_line(draw, text, make_font, box_w, max_size=max_size)
        draw.text((text_x, y), fitted, font=font, fill=0)
        y += row_h

    return _to_png(img)


def fit_image_to_label(spec: LabelSpec, png: bytes) -> bytes:
    """Scale an arbitrary image to fit the label, centred on white, 1-bit."""
    src = Image.open(BytesIO(png))
    if src.mode in ("RGBA", "LA", "P"):
        src = src.convert("RGBA")
        background = Image.new("RGBA", src.size, "white")
        src = Image.alpha_composite(background, src)
    src = src.convert("L")
    # A portrait source on a landscape label is almost certainly rotated.
    if (src.height > src.width) != (spec.height > spec.width):
        src = src.rotate(90, expand=True)
    src = ImageOps.contain(src, (spec.width, spec.height), Image.LANCZOS)
    canvas = Image.new("L", (spec.width, spec.height), 255)
    canvas.paste(src, ((spec.width - src.width) // 2, (spec.height - src.height) // 2))
    return _to_png(canvas.convert("1"))


def _to_png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
