// SPDX-License-Identifier: GPL-2.0-or-later
// Force-included into every engine file (-include). The engine leaves with
// exit() on "Quit Game" and on fatal errors; on the badge that would reboot,
// so exit() returns control to the caller of oreo_doom_start/tick instead.

#ifndef OREO_DOOM_PORT_H
#define OREO_DOOM_PORT_H

#include <stdlib.h>

void oreo_doom_exit(int code) __attribute__((noreturn));
#define exit(code) oreo_doom_exit(code)

// The renderer's large zero-initialised tables (~200 KiB) go to PSRAM on the
// badge, keeping internal RAM for MicroPython, Wi-Fi and BLE. The section is
// ESP-IDF's EXT_RAM_BSS_ATTR one, which the linker places in PSRAM when
// CONFIG_SPIRAM_ALLOW_BSS_SEG_EXTERNAL_MEMORY is set (the board sets it).
#ifdef OREO_DOOM_BADGE
#define OREO_EXT_BSS __attribute__((section(".ext_ram.bss.oreo_doom")))
#else
#define OREO_EXT_BSS
#endif

#endif
