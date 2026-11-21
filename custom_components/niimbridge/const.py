"""Constants for NiimBridge."""

from __future__ import annotations

DOMAIN = "niimbridge"

CONF_DEVICE_ID = "device_id"
CONF_WEBHOOK_ID = "webhook_id"
CONF_LABEL_SIZE = "label_size"
CONF_WIDTH = "width"
CONF_HEIGHT = "height"
CONF_ROTATE = "rotate"
CONF_DENSITY = "density"
CONF_LABEL_TYPE = "label_type"
CONF_COPIES = "copies"
CONF_FONT = "font"
CONF_FONT_SIZE = "font_size"
CONF_QR_PERCENT = "qr_percent"
CONF_MQTT_PNG_TOPIC = "mqtt_png_topic"
CONF_MQTT_JSON_TOPIC = "mqtt_json_topic"

CUSTOM_SIZE = "custom"

# Landscape design size in pixels at 203 DPI (8 dots/mm). Rotation is applied
# separately so tape-fed printers (D110) can use the natural landscape design.
LABEL_SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "30x15": (240, 120),
    "40x12": (320, 96),
    "40x30": (320, 240),
    "50x15": (400, 120),
    "50x30": (400, 240),
    "50x80": (400, 640),
}

DEFAULT_LABEL_SIZE = "40x12"
DEFAULT_ROTATE = 90
DEFAULT_DENSITY = 3
DEFAULT_LABEL_TYPE = 1
DEFAULT_COPIES = 1
DEFAULT_FONT_SIZE = 0  # 0 = auto-fit
DEFAULT_QR_PERCENT = 90  # QR height as a percentage of label height

MAX_UPLOAD_BYTES = 2_000_000
SIGNAL_LABEL_UPDATED = f"{DOMAIN}_label_updated"

DOTS_PER_MM = 8  # Niimbot printers print at 203 DPI
