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


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if not current or draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wrapped_fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    make_font: Any,
    box_w: int,
    box_h: int,
    max_size: int,
    min_size: int = 8,
) -> tuple[list[str], Any]:
    """Largest font whose word-wrapped text fits the box; ellipsis as a last resort."""
    font = make_font(min_size)
    lines = [text]
    for size in range(max(max_size, min_size), min_size - 1, -1):
        font = make_font(size)
        lines = _wrap(draw, text, font, box_w)
        widest = max((draw.textlength(line, font=font) for line in lines), default=0)
        if widest <= box_w and len(lines) * int(size * 1.15) <= box_h:
            return lines, font
    # Even the minimum size does not fit: keep the lines that fit, ellipsize the last.
    line_h = int(min_size * 1.15)
    keep = max(1, box_h // line_h)
    lines = _wrap(draw, text, font, box_w)[:keep]
    last = lines[-1]
    while len(last) > 1 and draw.textlength(last + "…", font=font) > box_w:
        last = last[:-1]
    if keep < len(_wrap(draw, text, font, box_w)) or draw.textlength(last, font=font) > box_w:
        lines[-1] = last.rstrip() + "…"
    return lines, font


def render_item_label(
    spec: LabelSpec,
    name: str,
    asset_id: str = "",
    location: str = "",
    url: str = "",
    area: str = "",
) -> bytes:
    """Standard layout: QR on the left; asset ID (mono), area, then name.

    The asset ID and area are single lines that shrink to fit. The name may wrap
    onto several lines, shrinking only as far as needed to fit the label.
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

    # Asset ID and area take fixed shares of the height; the name gets the rest
    # and may wrap onto several lines.
    asset_h = int(box_h * 0.22) if asset_id else 0
    place_h = int(box_h * 0.24) if place else 0
    name_h = box_h - asset_h - place_h

    name_lines: list[str] = []
    name_font: Any = None
    if display_name:
        limit = spec.font_size if spec.font_size > 0 else int(name_h / 1.15)
        name_lines, name_font = _wrapped_fit(
            draw, display_name, regular, box_w, name_h, max_size=limit
        )

    y = pad
    if asset_id:
        # White on black, right-aligned to the edge of the text box, and never
        # larger than the name.
        max_size = int(asset_h / 1.15)
        if name_font is not None:
            max_size = min(max_size, getattr(name_font, "size", max_size))
        inset = max(2, asset_h // 8)
        fitted, font = _one_line(
            draw, asset_id, _mono, box_w - 2 * inset, max_size=max_size
        )
        left, top, right, bottom = draw.textbbox((0, 0), fitted, font=font)
        w, h = right - left, bottom - top
        x1 = text_x + box_w
        x0 = x1 - w - 2 * inset
        draw.rectangle((x0, y, x1 - 1, y + h + 2 * inset - 1), fill=0)
        draw.text((x0 + inset - left, y + inset - top), fitted, font=font, fill=1)
        y += max(asset_h, h + 2 * inset)

    if place:
        fitted, font = _one_line(
            draw, place, regular, box_w, max_size=int(place_h / 1.35)
        )
        draw.text((text_x, y), fitted, font=font, fill=0)
        place_bottom = y + draw.textbbox((0, 0), fitted, font=font)[3]
        y += place_h
        if name_lines:
            # Thin rule centred between the area text and the top of the name.
            name_top = y + draw.textbbox((0, 0), name_lines[0], font=name_font)[1]
            rule_y = (place_bottom + name_top) // 2
            draw.line((text_x, rule_y, text_x + box_w - 1, rule_y), fill=0, width=1)

    if name_lines:
        size = getattr(name_font, "size", 12)
        for line in name_lines:
            draw.text((text_x, y), line, font=name_font, fill=0)
            y += int(size * 1.15)

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
