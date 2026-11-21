#!/usr/bin/env python3
"""Generate a HomeBox label template (Import JSON) for a Niimbot label size.

    python scripts/make_homebox_template.py 40 12 > homebox-templates/niimbot-40x12.json

Layout: QR code on the left; asset ID white-on-black at the top right; area
(HomeBox's location), a thin rule, then the item name (auto-fit, wraps).
Coordinates are HomeBox canvas pixels at 96 dpi; the template is 203 dpi, the
resolution of Niimbot printers, so it prints 1:1.
"""
import json
import sys

PX_PER_MM = 96 / 25.4


def make(w_mm: float, h_mm: float) -> dict:
    W, H = w_mm * PX_PER_MM, h_mm * PX_PER_MM
    pad = max(1.5, H * 0.045)
    qr = H - 2 * pad
    tx = pad * 2 + qr                      # text column left edge
    tw = W - tx - pad                      # text column width
    id_h = H * 0.26
    area_h = H * 0.2
    name_top = pad + id_h + area_h + H * 0.04
    name_h = H - pad - name_top

    def base(**kw):
        return {"originX": "left", "originY": "top", "scaleX": 1, "scaleY": 1, "angle": 0, **kw}

    def text(t, left, top, width, height, size, **kw):
        data = {"autofit": True, "wrap": True, "fixedWidth": round(width, 2),
                "fixedHeight": round(height, 2), "maxFontSize": size}
        return base(type="textbox", text=t, left=round(left, 2), top=round(top, 2),
                    width=round(width, 2), fontSize=size, fill=kw.pop("fill", "#000000"),
                    textAlign=kw.pop("align", "left"), data=data, **kw)

    def qr_group(left, size):
        """A barcode as the HomeBox editor stores it: a Group with a placeholder."""
        half = round(size / 2, 2)
        child = dict(originX="left", originY="top", scaleX=1, scaleY=1, angle=0)
        return base(
            type="Group", left=round(left, 2), top=round(left, 2),
            width=round(size, 2), height=round(size, 2),
            objects=[
                dict(type="Rect", left=-half, top=-half, width=round(size, 2),
                     height=round(size, 2), fill="#f0f0f0", stroke="#cccccc",
                     strokeWidth=1, **child),
                dict(type="IText", text="[QR]", left=-half + 5, top=-8, fontSize=12,
                     fontFamily="Arial", fill="#666666", **child),
            ],
            data={"type": "barcode", "format": "qr", "contentSource": "asset_url"},
        )

    objects = [
        qr_group(pad, qr),
        base(type="rect", left=round(tx + tw - tw * 0.5, 2), top=round(pad, 2),
             width=round(tw * 0.5, 2), height=round(id_h, 2), fill="#000000"),
        text("{{asset_id}}", tx + tw - tw * 0.5 + 1, pad + 0.5, tw * 0.5 - 2, id_h - 1,
             round(id_h * 0.8, 1), fill="#ffffff", align="right"),
        text("{{location}}", tx, pad + id_h + 0.5, tw, area_h - 1, round(area_h * 0.8, 1)),
        base(type="line", left=round(tx, 2), top=round(pad + id_h + area_h, 2),
             x1=0, y1=0, x2=round(tw, 2), y2=0, stroke="#000000", strokeWidth=0.75),
        text("{{name}}", tx, name_top, tw, name_h, round(min(name_h, H * 0.34), 1)),
    ]
    return {
        "name": f"NiimBridge {w_mm:g}x{h_mm:g} mm",
        "description": f"Niimbot {w_mm:g}x{h_mm:g} mm label: QR, asset ID (inverted), location, name.",
        "width": w_mm, "height": h_mm, "dpi": 203, "preset": None,
        "outputFormat": "png", "isShared": False, "offsetX": 0, "offsetY": 0,
        "canvasData": {"version": "6.0.0", "objects": objects},
    }


if __name__ == "__main__":
    w, h = float(sys.argv[1]), float(sys.argv[2])
    json.dump(make(w, h), sys.stdout, indent=2)
    print()
