# Changelog

## [0.3.0] - 2026-11-20

Adapts NiimBridge to HomeBox v0.27, which replaced the built-in label with label templates.

### Added

- Starter HomeBox label templates (`homebox-templates/`, Import JSON) for 40x12, 30x15 and 50x30 mm labels at 203 DPI, and `scripts/make_homebox_template.py` to generate other sizes.
- Text mode looks the item up through the HomeBox integration for Home Assistant (when installed) from the `X-URL` header, because HomeBox's print command no longer passes the asset ID or location.
- `Floor | Location` row with the floor inverted: a location such as `L1 Kitchen` is split at its first word when it looks like a floor code. `floor` is also accepted by JSON and `niimbridge.print_label`.
- Image mode reads `X-Width-Mm`, `X-Height-Mm` and `X-Copies` headers, so the label size and copy count come from HomeBox.
- README rewritten around HomeBox's documented template and print-command setup, with troubleshooting.

### Changed

- Default font is bold DejaVu Sans Mono (the asset ID uses the regular weight), for legibility at 1-bit on small labels.
- The Configure dialog shows the new print command (`X-URL` and `X-Copies` headers).

### Fixed

- Images are converted with a plain threshold instead of Pillow's default dithering, which turned anti-aliased text and thin rules into speckle.

## [0.2.0] - 2026-11-01

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
