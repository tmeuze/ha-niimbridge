# Where this got to

Working notes for NiimBridge. Delete this file once the open items below
have been confirmed on real hardware, since from then on the changelog and
README carry the story.

**Last updated:** 2026-11-24, after releasing v0.4.0.

## What works

- Text mode, image mode and JSON all print on a D110-M through hass-niimbot.
  Verified by hand against a self-hosted HomeBox and Home Assistant.
  That test predates routing and the asset ID and
  location lookup.
- 28 unit tests pass, and CI (HACS validation and hassfest) passes on main.

## What isn't verified

- **A full print with the new layout and the HomeBox lookup.** The unit
  tests cover the lookup against a fake, not the live integration.
- **Routing between two real printers.** The D110-M and a B1 are available,
  but only fakes have been run.
- **The Auto label size.** The attribute names read from the Cloud Label
  Info sensor were taken from hass-niimbot's source and haven't been
  checked against a live sensor (VERIFY).
- **Density and label type on other models.** The failure on the D110-M is
  understood; a plain D110 and the B1 haven't been tried with the defaults.

## Things the user still has to do

- Update NiimBridge in HACS, restart Home Assistant, and set density to 0
  and label type to Printer default on existing entries.
- Put the current command from Configure into `HBOX_LABEL_MAKER_PRINT_COMMAND`
  on the HomeBox server. Routing needs the two size headers.
- Delete three empty files in `homebox-templates/` that a shell mistake
  created (names like `niimbot-30 15x.json`). They are untracked.

## What the earlier notes got wrong

- HomeBox's print command was assumed to pass the asset ID and location
  (as the old built-in label did). From v0.27 it passes only the item name
  and URL, which is why text mode now does a lookup.
- The preview image was assumed safe to update from the print thread. Home
  Assistant logged an error and the preview stopped refreshing; fixed in
  0.3.1.

## Open

- Submitting to the default HACS repository list has not been started.
- Whether the NFC check-in work (a different project, ha-homebox) shares
  any code with this one. Probably not.
