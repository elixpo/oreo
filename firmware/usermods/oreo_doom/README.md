# oreo_doom: Doom on the Oreo Badge

> **Licence exception.** Everything in this directory is
> **GPL-2.0-or-later** (one file, `engine/sha1.c`, is GPL-3.0-or-later), not
> MIT like the rest of the repository. Firmware images that include it are
> distributed as a whole under **GPL-3.0**. See
> [`LICENSES/exceptions/oreo_doom-GPL`](../../../LICENSES/exceptions/oreo_doom-GPL).

The `_oreo_doom` MicroPython module runs the Doom engine on the badge. The
OreoOS app [`apps/doom`](../../../apps/doom) drives it one frame at a time and
copies each frame to the screen.

## Where it comes from

- `engine/` is the Doom engine from
  [doomgeneric](https://github.com/ozkl/doomgeneric) at commit
  `e257a09527062bfb986b6e5e0780839b6cbd5b71`, itself a port of
  [Chocolate Doom](https://www.chocolate-doom.org) and the original Doom
  source released by id Software. Copyright (C) 1993-1996 Id Software, Inc.;
  (C) 2005-2014 Simon Howard and other Chocolate Doom contributors;
  (C) 1998-2001 Free Software Foundation, Inc. (`sha1.c`). Each file keeps its
  original notice.
- Left out, because the badge does not use them or they were released without
  "or any later version": the platform front ends (`doomgeneric_*.c`, SDL and
  Allegro audio, `icon.c`, `gusconf.c`), `mus2mid.c`/`mus2mid.h`,
  `doomgeneric.c`, `dummy.c`, `doomgeneric.h`, `doom.h`, `config.h` and the
  build files.
- `port/` and `moddoom.c` are written for OreoOS (GPL-2.0-or-later) and
  replace the files left out: start-up and one-step ticking, button mapping,
  gyro aiming (turning added to the engine's mouse input during play),
  palette conversion to RGB565, the `exit()` trap that returns to OreoOS, and
  the OWZ reader.

## Changes to the engine files

Each changed file carries a "Modified 2026 by the OreoOS project" line.

| File | Change |
|---|---|
| `m_misc.c` | `M_FileExists` accepts `owz:` paths (game data in flash). |
| `w_file.c` | `W_OpenFile` opens `owz:` paths with the OWZ reader. |
| `m_menu.c` | With a single-episode IWAD, New Game goes straight to the skill menu instead of listing episodes that are not there. Quit Game returns to OreoOS and the title screen instead of exiting, so Doom can be started again without a reboot (no quit sound or wait: the badge has no speaker). |
| `d_englsh.h` | Yes/no prompts name the badge's buttons (B yes, HOME no) instead of Y and N. |
| `d_loop.c`, `r_bsp.c`, `r_draw.c`, `r_main.c`, `r_plane.c`, `r_things.c`, `statdump.c` | Large static tables tagged `OREO_EXT_BSS`, which places them in PSRAM on the badge. |

## Game data

The game is Episode 1 (nine levels) of [Freedoom](https://freedoom.github.io)
Phase 1 (BSD-3-Clause, see
[`LICENSES/notices/freedoom`](../../../LICENSES/notices/freedoom)). It is
never committed: [`tools/fetch_freedoom.py`](../../../tools/fetch_freedoom.py)
downloads release 0.13.0, checks its SHA-256 and packs it with
[`tools/pack_wad.py`](../../../tools/pack_wad.py) into OWZ (each lump zlib
compressed; sound and music emptied, as the badge has no speaker; the other
episodes' maps dropped and their title-screen demos replaced by an
Episode 1 one, which would otherwise replay out of sync), from 27.5 MiB to
6.9 MiB. All four episodes would need 9.7 MiB, which
leaves too little flash for OreoOS's filesystem. `./deploy --full` writes it
to the `doom` flash partition (see
`firmware/boards/OREO_BADGE/partitions-oreo-badge.csv`), which the module
memory-maps and inflates a lump at a time. Its text graphics are restyled
for the 2" screen by [`tools/doom_text.py`](../../../tools/doom_text.py): a
thin 5x7 font for messages, and the dark outlines removed from large text.

## Testing on a PC

`tests/doom_host/host_main.c` runs the same engine and port on Linux with a
simulated clock and scripted buttons, writing frames as PPM images:

```bash
cd firmware/usermods/oreo_doom
gcc -O2 -w -DCMAP256 -include port/oreo_doom_port.h -Iport -Iengine \
    engine/*.c port/*.c ../../../tests/doom_host/host_main.c -lz -lm -o host_doom
./host_doom ../../../oreoWare/doom/freedoom1.owz frames 400
```
