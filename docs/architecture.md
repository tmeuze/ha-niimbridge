# Architecture

How a print travels from HomeBox to the printer, and which file does each
step. The short version is in the README; this is the longer one.

## The path of one print

1. **HomeBox runs its print command** (`HBOX_LABEL_MAKER_PRINT_COMMAND`, `wget`
   under the hood) and posts to the webhook. In text mode it sends the item
   name, URL, copies and the template's size as headers. In image mode it
   sends the template's PNG.
2. **`bridge.py` receives it** in `_handle_webhook`. It reads the label size
   from the headers and, if another NiimBridge entry matches that size better,
   hands the request to that entry (`_route`). It replies `202` immediately
   and queues the print as a background task, because the Bluetooth connection
   takes longer than HomeBox is willing to wait.
3. **The entry builds the label.** Text mode looks the item up through the
   HomeBox integration for Home Assistant (`_lookup_homebox_entity`) to get the
   asset ID and location, then `renderer.py` draws it: QR code, an inverted
   asset ID, a `Floor | Location` row, a rule, and the wrapped name. Image
   mode converts the picture with a plain threshold (`fit_image_to_label`).
4. **`niimbot.print` prints it.** `_async_call_niimbot` passes the image to
   hass-niimbot as a data URI, with rotation, copies and, only if set,
   density and label type.

## Where things live

| File | Does |
|---|---|
| `bridge.py` | One `NiimBridge` per entry: webhook, routing, queue, lookup, the call to niimbot |
| `renderer.py` | Label drawing and image conversion. No Home Assistant imports, so it is easy to test |
| `config_flow.py` | Setup and Configure dialogs, and the print command shown to the user |
| `image.py` | The Label preview image entity |
| `__init__.py` | Setup, the `niimbridge.print_label` service, MQTT subscriptions |
| `fonts/` | DejaVu Sans Mono, bundled so labels look the same everywhere |
| `homebox-templates/`, `scripts/` | Starter HomeBox templates and the script that makes other sizes |

## Boundaries

NiimBridge never talks Bluetooth, and never writes to HomeBox. It reads item
details through the HomeBox integration for Home Assistant and prints through
hass-niimbot, so those two stay the owners of their own settings and devices.
The one thing it asks the user to change outside Home Assistant is the print
command on the HomeBox server.
