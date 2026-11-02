// SPDX-License-Identifier: GPL-2.0-or-later
// Oreo Badge Doom port: the interface between the engine glue
// (oreo_doomgeneric.c, w_file_owz.c) and a platform (the MicroPython module
// on the badge, or the host test).

#ifndef OREO_DOOM_PORT_API_H
#define OREO_DOOM_PORT_API_H

#include <stddef.h>
#include <stdint.h>

#define OREO_DOOM_W 320
#define OREO_DOOM_H 240         // panel height; the 200 game rows are centred
#define OREO_DOOM_TOP 20

// Badge buttons, in OreoOS order (oreoOS/api.py BTN_*).
#define OREO_BTN_HOME  (1u << 0)
#define OREO_BTN_A     (1u << 1)
#define OREO_BTN_B     (1u << 2)
#define OREO_BTN_C     (1u << 3)
#define OREO_BTN_UP    (1u << 4)
#define OREO_BTN_DOWN  (1u << 5)
#define OREO_BTN_LEFT  (1u << 6)
#define OREO_BTN_RIGHT (1u << 7)

// Set by the platform before oreo_doom_start(): the OWZ image (pack_wad.py).
extern const uint8_t *oreo_owz_data;
extern size_t oreo_owz_size;

// Start the engine, or resume it if it is already running. Returns 0 on
// success, -2 if the engine stopped on a fatal error (it cannot restart
// without a reset), otherwise the engine's exit code.
int oreo_doom_start(int argc, char **argv);

// Feed the current button mask and run one engine step. With gyro set, `turn`
// is added to the player's turning (mouse units: 1 = 8/65536 of a full turn)
// and LEFT/RIGHT strafe instead of turning. Returns 1 when a new frame was
// drawn, 0 when not, 2 when the player chose Quit Game (the engine is back at
// the title screen and keeps running), and -1 once the engine has stopped on
// a fatal error; oreo_doom_exit_code() then gives its code.
int oreo_doom_tick(uint32_t buttons, int turn, int gyro);

// Called by the engine's Quit Game confirmation.
void oreo_doom_quit_to_os(void);

int oreo_doom_running(void);
int oreo_doom_exit_code(void);

// The panel image: 320x240 big-endian RGB565 (the ST7789's byte order).
const uint8_t *oreo_doom_frame(void);

// Provided by the platform.
uint32_t oreo_platform_ms(void);
void oreo_platform_sleep_ms(uint32_t ms);
// Inflate a zlib stream to exactly dst_len bytes; 0 on success.
int oreo_platform_inflate(void *dst, size_t dst_len, const void *src, size_t src_len);
void *oreo_platform_alloc(size_t size);

#endif
