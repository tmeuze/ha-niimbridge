# Decisions

NiimBridge's record of the choices that shaped it, in the format conformIT
asks for. Numbered, stable, never reused. A reversed decision gets a new
entry and the old one stays. Entries 1 to 8 were written on 2026-11-24 from
the project's history, so the dates are those of the releases that carried
each change.

## 1. A separate project, not a feature of ha-homebox

**Chosen:** NiimBridge lives in its own repository. It started as an idea
for the ha-homebox fork and was split out in October 2026.

**Why:** printing to Niimbot hardware depends on hass-niimbot and has
nothing to do with HomeBox's inventory sync, and the upstream ha-homebox
maintainer might never want it.

**What it cost:** one more thing to install, and two integrations that both
talk to HomeBox.

**What would justify revisiting:** upstream asking for it natively.

## 2. Webhook first, MQTT optional

**Chosen:** the primary input is a Home Assistant webhook. MQTT topics are
an optional extra.

**Why:** HomeBox's print command can post straight to a webhook, so nothing
extra has to run. MQTT needs a broker and credentials in the HomeBox
container.

**What it cost:** the webhook URL is the only secret, because webhooks take
no login.

**Rejected:** MQTT only; a separate bridge service.

## 3. The command uses wget, because HomeBox has no curl

**Chosen:** the documented `HBOX_LABEL_MAKER_PRINT_COMMAND` calls `wget`.

**Why:** the regular HomeBox image ships GNU wget and mosquitto-clients but
no curl. HomeBox splits the command into arguments and runs it without a
shell, so every option has to be a single token.

**What it cost:** the hardened HomeBox image, which has no tools at all,
cannot be used.

## 4. Reply immediately and print in the background

**Chosen:** the webhook returns 202 straight away and the print runs as a
background task.

**Why:** the Bluetooth connection takes many seconds, and HomeBox stops a
print command after 60 seconds. Early versions made HomeBox retry and print
the same label over and over.

**What it cost:** HomeBox can't see print errors. They appear in the Home
Assistant log.

## 5. Draw the label ourselves in text mode (0.3.0)

**Chosen:** the recommended command sends the item name and URL, and
NiimBridge draws the label. It looks the item up through the HomeBox
integration for Home Assistant to get the asset ID and location.

**Why:** HomeBox v0.27 replaced its built-in label with label templates,
and its print command no longer passes the asset ID or location. A template
can't split "L1 Kitchen" into an inverted floor and a location either.

**What it cost:** a soft dependency on the HomeBox integration. Without it
the label has only the name and QR code. Image mode, which prints the
template's own picture, remains for people who want HomeBox's exact design.

## 6. Threshold, not dithering (0.3.0)

**Chosen:** pictures are converted to 1-bit with a plain threshold of 176.

**Why:** Pillow's default dithering turned anti-aliased text and thin rules
into speckle on the printed label.

**What it cost:** photographs and gradients look worse. That is not what
this prints.

## 7. Printer defaults for density and label type (0.3.2)

**Chosen:** density and label type default to 0 and "printer default", and
are sent to `niimbot.print` only when set.

**Why:** on a D110-M, density 3 with label type 1 failed with "No response
for request 0xe3", and the same label printed fine without them. This also
failed when `niimbot.print` was called directly, so it isn't NiimBridge's
doing.

**What it cost:** existing entries keep their old saved values until the
user changes them. The cause is partly VERIFY: it is confirmed on one
D110-M, not on other models.

## 8. Route by label size (0.4.0)

**Chosen:** HomeBox sends the template size in `X-Width-Mm` and
`X-Height-Mm`. The request goes to the NiimBridge entry whose label size
matches within 1 mm, ignoring orientation, and falls back to the entry that
received it.

**Why:** HomeBox supports one print command, hence one webhook, but its own
guidance is one template per label stock, so size identifies the printer.

**What it cost:** two printers loaded with the same label size can't be told
apart; the receiving entry wins. Routing is tested with fakes only (see
STATE.md).

**Rejected:** a routing header per printer, which HomeBox can't vary per
template; one webhook per printer, which HomeBox can't choose between.

**What would justify revisiting:** HomeBox gaining a per-template print
command, or a template field NiimBridge could read to pick a printer.
