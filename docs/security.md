# Security

NiimBridge's own posture. How to report a vulnerability is in a top-level
`SECURITY.md` if the project has one; this file is about the trust model.

## The webhook is the only secret

Home Assistant webhooks need no login, so anyone who knows the URL can make
the printer print. The random webhook ID is the protection. Treat it as a
password: don't paste it into issues, logs or docs, and note that it appears
in the HomeBox server's environment. To rotate it, remove and re-add the
integration. The cost is that a leaked ID can only waste labels, but it can
do that repeatedly.

## What it reads and sends

- **Reads:** the request body and headers, and item details from the HomeBox
  integration already logged in to HomeBox. NiimBridge holds no HomeBox
  credentials of its own.
- **Sends:** the rendered label to hass-niimbot over a Home Assistant service
  call. If the user turns on "Fetch Label Info Online" in the Niimbot
  integration, hass-niimbot sends the roll's product code to a NIIMBOT server.
  That is hass-niimbot's feature, not NiimBridge's.
- **Writes:** nothing outside Home Assistant.

## Input handling

Request bodies are untrusted. Images are decoded by Pillow and resized to the
label, text is drawn rather than interpreted, and label sizes from headers are
only used to choose among configured entries. VERIFY: no fuzzing or size limit
beyond Home Assistant's own request limit has been tested.

## Not in scope

The HomeBox container's network access to Home Assistant, and Bluetooth
pairing, belong to the user's setup.
