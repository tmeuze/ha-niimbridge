# NiimBridge

A Home Assistant (HACS) integration that bridges [HomeBox](https://homebox.software/) label printing to a Niimbot printer through the [hass-niimbot](https://github.com/eigger/hass-niimbot) integration.

HomeBox runs a print command when you print a label; that command posts to a webhook NiimBridge creates in Home Assistant; NiimBridge draws or resizes the label for your label stock and calls `niimbot.print`. Bluetooth is handled entirely by hass-niimbot.

## Requirements

- Home Assistant 2024.6 or newer
- [hass-niimbot](https://github.com/eigger/hass-niimbot) installed with your printer added
- HomeBox v0.27 or newer (label templates and server-side printing; see [HomeBox's Label Templates guide](https://homebox.software/en/user-guide/label-templates))
- Optional but recommended: the HomeBox integration for Home Assistant, so NiimBridge can look up an item's asset ID and location (see [Print modes](#print-modes))

## Install

1. HACS → three-dot menu → Custom repositories → add `https://github.com/tmeuze/ha-niimbridge` as **Integration**.
2. Download NiimBridge and restart Home Assistant.
3. Settings → Devices & services → Add integration → **NiimBridge**.
4. Pick your Niimbot printer and label settings. The last step shows your webhook URL and the exact HomeBox command to use. To see it again later: Settings → Devices & services → NiimBridge → **Configure**.

## HomeBox setup

HomeBox does not talk to printers itself. Server-side printing is set with an environment variable (it is not a UI setting), and since v0.27 every print needs a label template.

### 1. Create a label template and make it your default

HomeBox's quick print and print dialog render a **label template**, so you need at least one, even if you use the text print mode below.

1. In HomeBox open **Label Templates** (sidebar, under Profile) → **Import JSON** and choose one of the starter templates from [`homebox-templates/`](homebox-templates): `niimbot-40x12.json`, `niimbot-30x15.json` or `niimbot-50x30.json`. Each is sized in millimetres for that label at 203 DPI, the resolution of Niimbot printers, so it prints 1:1 with no scaling. HomeBox's guide recommends one template per label stock; `scripts/make_homebox_template.py WIDTH_MM HEIGHT_MM` generates other sizes.
2. On the template card open the **⋯** menu → **Set as default for quick printing**. The default is a personal preference, so each user picks their own.
3. Optionally use **Share with collection** so other members can use it. Imported templates start private.

The starter template has a QR code (asset URL), the asset ID white on black, the location, a rule and the item name with auto-fit. If you design your own, HomeBox's tips apply: keep text inside a small margin, use **Auto-fit** for item names, and give QR codes room to scan (HomeBox suggests at least 15 mm on a 300 DPI printer; a 12 mm tall label limits the QR code to about 11 mm, so check that your phone scans it).

### 2. Set the print command

Set `HBOX_LABEL_MAKER_PRINT_COMMAND` on the HomeBox server and restart it. The Configure dialog shows the command with your webhook URL filled in. For Docker Compose:

```yaml
environment:
  - HBOX_LABEL_MAKER_PRINT_COMMAND=wget -q -O /dev/null --tries=1 --timeout=10 --header=Content-Type:text/plain --header=X-Title:{{.TitleText}} --header=X-URL:{{.URL}} --header=X-Copies:{{.Copies}} --header=X-Width-Mm:{{.WidthMm}} --header=X-Height-Mm:{{.HeightMm}} --post-data={{.DescriptionText}} http://homeassistant.local:8123/api/webhook/<random-id>
```

Notes from HomeBox's documentation that apply here:

- HomeBox splits the command into arguments before substituting values and runs it directly, not through a shell, so each option must contain no spaces. The values of `{{.TitleText}}` and the other placeholders stay inside their own argument.
- If the command contains `{{.Copies}}`, HomeBox runs it once with the copy count; otherwise it runs it once per copy. NiimBridge uses the `X-Copies` header to print that many labels in one job.
- HomeBox stops a print command after 60 seconds. NiimBridge replies immediately and prints in the background, so a slow Bluetooth connection causes neither a timeout nor a repeat.
- The regular HomeBox image includes `wget` (the hardened image has no tools, so use the regular one). The HomeBox container must be able to reach Home Assistant at the webhook URL; if the URL NiimBridge shows isn't reachable from HomeBox, use an address that is, such as the HA server's LAN IP.
- Webhook URLs need no login, so the random ID is the secret. Don't share it. To get a new one, remove and re-add the integration.

### 3. Print

Use **Print label** on an item (one click uses your default template; the arrow offers template and copies), **Quick Print Selected** on a list, or **Batch print**. Choose the **Label printer** destination when asked. The template editor's **Test print** button sends one label through the same command, which is a handy way to test the whole chain.

HomeBox's `/api/v1/status` reports whether a print command is set (`labelPrinting`). If the **Label printer** option is missing in HomeBox, no print command is configured.

## Print modes

NiimBridge accepts three kinds of request on the same webhook.

**Text mode (recommended).** The command above sends the item's page URL and name. NiimBridge draws the label itself using the layout below. If the HomeBox integration for Home Assistant is installed and logged in to the same HomeBox, NiimBridge uses it to look the item up from the URL, which gives it the asset ID and location (HomeBox's print command no longer passes those). Without that integration the label is drawn from the name and URL only, with no asset ID or location row.

**Image mode.** Print the template's own picture, so the design from HomeBox's editor is exactly what prints:

```
HBOX_LABEL_MAKER_PRINT_COMMAND=wget -q -O /dev/null --tries=1 --timeout=10 --header=Content-Type:image/png --header=X-Width-Mm:{{.WidthMm}} --header=X-Height-Mm:{{.HeightMm}} --header=X-Copies:{{.Copies}} --post-file={{.FileName}} http://<ha>/api/webhook/<id>
```

NiimBridge sizes the label from `X-Width-Mm` and `X-Height-Mm` (8 dots per mm, so the template's size wins over the preset) and converts the picture with a plain black/white threshold, not dithering, so thin lines and small text stay clean. Make the template the same millimetre size as your label for the sharpest result. HomeBox's template renderer uses its built-in fonts and cannot split a location such as `L1 Kitchen` into an inverted floor, so use text mode if you want those.

**JSON, the service and MQTT.** The webhook also accepts JSON for the standard layout:

```json
{"name": "Anker USB-C Charger", "asset_id": "000-042", "area": "L1 Kitchen", "url": "https://homebox.example/item/abc", "copies": 1}
```

`niimbridge.print_label` prints the same layout from an automation (`preview_only` renders without printing). The regular HomeBox image also ships `mosquitto_pub`: set a PNG topic and/or a JSON topic in the options, and for image mode over MQTT use `mosquitto_pub -h <broker> -u <user> -P <password> -t homebox/labels -f {{.FileName}}` as the print command.

## The standard label

Drawn in text, JSON, service and MQTT-JSON modes: a QR code on the left (item URL, else asset ID, else name) and three rows on the right:

1. asset ID in a small monospace font, white on black and right-aligned
2. `Floor | Location`, with the floor inverted, followed by a thin rule. A location written as `L1 Kitchen` is split at its first word when that looks like a floor code (`L1`, `B2`, `3`); other locations such as `Garage` are shown whole with no floor. JSON and the service also accept `floor` and `area` explicitly.
3. the item name, with the location text removed if the name contains it. It wraps onto more lines when long, shrinking only as far as needed.

All text uses bold DejaVu Sans Mono by default, chosen because it stays legible at 1-bit on small labels (the strokes survive thresholding and `1`, `l` and `I` are clearly different); the asset ID uses the regular weight because heavy strokes fill in on white-on-black. You can set your own font file in the options. The asset ID and location are single lines that shrink to fit; the name is cut off with an ellipsis only at the minimum size. The **Label preview** image entity shows the last rendered label.

## Label settings

| Setting | Notes |
|---|---|
| Label size | Presets are landscape pixels at 203 DPI (30×15, 40×12, 40×30, 50×15, 50×30, 50×80 mm), custom pixels, or **Auto**, which uses the size of the roll loaded in the printer (see [Label details from the printer](#label-details-from-the-printer)). Image mode takes the size from HomeBox instead |
| Rotation | Applied by niimbot when printing. D110-style tape printers typically need 90 |
| Density, label type | **0 / Printer default** (the default): not sent, so the printer and the loaded roll decide. Set a value only if you need to override it |
| Copies | Passed through to `niimbot.print`; copies from HomeBox override the configured value |
| QR code size | Percent of label height for the standard layout (30–100, default 90) |
| Font, font size | Optional font file (looked up in `/config/www/fonts`) replaces the default; size 0 auto-fits |

## Label details from the printer

hass-niimbot can read the loaded roll's details from the printer's RFID tag. Turn on **Fetch Label Info Online** in the Niimbot integration's options (off by default; it sends only the roll's product code to a NIIMBOT server). Then:

- hass-niimbot itself fills in the print size and label type when a print leaves them out.
- NiimBridge's **Auto** label size reads the roll's size from the printer's Cloud Label Info sensor, so the label is drawn for whatever roll is loaded.

This needs a roll with an RFID tag. With other rolls the sensor has no size, and NiimBridge falls back to the custom width and height in its options.

## Multiple printers

Each NiimBridge entry drives one printer, with its own settings, webhook URL and preview image. Add the integration once per printer (Settings → Devices & services → NiimBridge → **Add service**) and give each its own label size.

HomeBox supports only one print command, so it can only call one webhook. NiimBridge therefore **routes by label size**: HomeBox sends the template's size in `X-Width-Mm` and `X-Height-Mm` (the commands above include them), and the request goes to the NiimBridge entry whose label size matches, within 1 mm and ignoring orientation. This fits HomeBox's own practice of one template per label stock:

1. Create one HomeBox template per label stock (for example 40×12 mm for the D110-M, 50×30 mm for the B1), each at that label's exact millimetre size.
2. Give each NiimBridge entry the matching label size.
3. Put any one entry's command in HomeBox. Which entry receives the request doesn't matter: it forwards to the right printer. If no entry matches, or the size isn't sent, the receiving entry prints it.

With **Auto** label size, an entry matches the size of the roll currently loaded in its printer. If two entries have the same label size, the receiving entry wins, then the first match. Routing applies to HomeBox's webhook requests; `niimbridge.print_label` needs `config_entry_id` when there is more than one entry, and MQTT topics belong to the entry that subscribes to them.

## Troubleshooting

- **Nothing happens when printing in HomeBox.** Check that a default template exists (quick print is disabled without one) and that `labelPrinting` is true at `/api/v1/status`. Then test the webhook without HomeBox: `curl -i -X POST -H "Content-Type: text/plain" -H "X-Title: Test" http://<ha>/api/webhook/<random-id>` should answer `202`.
- **Label has no asset ID or location.** In text mode that needs the HomeBox integration for Home Assistant to look the item up, because HomeBox's print command only receives the item name and URL.
- **Text or lines look speckled.** Use text mode, or image mode with a template that matches your label's millimetre size at 203 DPI.
- **`Failed to print: No response for request 0xe3` or `GATT Error … Internal error`.** Leave density and label type at **0 / Printer default** in NiimBridge's options. On a D110-M, sending density 3 and label type 1 made hass-niimbot fail (also when called directly, without NiimBridge), and leaving them out printed fine.
- **`No connectable radio sees …`.** The printer is asleep or out of range of your Bluetooth adapter or ESPHome proxy; wake it and try again.
- **Printing is slow.** Most of the time is the Bluetooth connection in hass-niimbot; see its connection options. Turn on debug logging (`custom_components.niimbridge: debug`) to see when each request arrives.
- **Several copies when you expected one.** Make sure `--header=X-Copies:{{.Copies}}` is in the command and the copies setting is 1.

## License

MIT. The bundled font DejaVu Sans Mono has its own license in `custom_components/niimbridge/fonts/LICENSE_DEJAVU.txt`.
