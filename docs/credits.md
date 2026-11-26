# Credits

What NiimBridge depends on, under which licence, and what it did not adopt.

| Thing | Used for | Licence |
|---|---|---|
| [hass-niimbot](https://github.com/eigger/hass-niimbot) | Bluetooth printing (`niimbot.print`) | VERIFY, see its repository |
| [HomeBox](https://homebox.software/) | The inventory and label templates this feeds from | AGPL-3.0, VERIFY |
| [Pillow](https://python-pillow.org) | Drawing and converting labels | MIT-CMU (HPND) |
| [segno](https://github.com/heuer/segno) | QR codes | BSD-3-Clause |
| [DejaVu Sans Mono](https://dejavu-fonts.github.io) | Bundled label font | Bitstream Vera licence, copy in `custom_components/niimbridge/fonts/LICENSE_DEJAVU.txt` |

[niimblue](https://github.com/MultiMote/niimblue) was a useful reference for
how Niimbot labels are shaped. No code was taken from it.

## Considered and not adopted

- **An MQTT-only design.** Kept as an option only; see decision 2 in
  [decisions.md](decisions.md).
- **Driving the printer over Bluetooth directly.** hass-niimbot already does
  this and handles proxies and reconnects.
