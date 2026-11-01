# Changelog

## [Unreleased]

### Changed

- New standard label layout: asset ID in a small monospace font (white on black, right-aligned), the area name with a thin separator rule below it, then the item name with the area name removed. The asset ID and area shrink to fit on one line; the item name wraps when long. No "Location:" style keys.
- The webhook accepts HomeBox label text (`text/plain` with `X-Title` and `X-URL` headers) so NiimBridge draws the label itself. The PNG input still works.
- JSON and `niimbridge.print_label` accept `area` (alias `location`); `name` is optional when `asset_id` is set.
- Bundles DejaVu Sans Mono (see `fonts/LICENSE_DEJAVU.txt`).

## [0.1.0] - 2026-10-06

### Added

- Webhook input that accepts HomeBox's label PNG, a raw PNG body, or JSON.
- Optional MQTT inputs (PNG and JSON topics).
- Standard label layout (QR code, name, asset ID, location) with label-size presets, rotation, density, label type, copies, font, font size and QR size options.
- Label preview image entity.
- `niimbridge.print_label` service.
- Prints through the hass-niimbot `niimbot.print` service; replies to the webhook immediately and prints in the background.
