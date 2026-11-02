// SPDX-License-Identifier: GPL-2.0-or-later
// Host test for the Oreo Badge Doom port: runs the real engine on a laptop
// from an OWZ image, with a simulated clock, scripted button presses, and
// frames written as PPM. Usage:
//   host_doom <file.owz> <outdir> [ticks] [zone-MiB]
//   OREO_HOST_IDLE=1 host_doom ...      (no input: title and demo loop)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

#include "oreo_doom.h"

static uint32_t now_ms;

uint32_t oreo_platform_ms(void) {
    return now_ms;
}

void oreo_platform_sleep_ms(uint32_t ms) {
    now_ms += ms ? ms : 1;          // simulated time: the test runs at full speed
}

int oreo_platform_inflate(void *dst, size_t dst_len, const void *src, size_t src_len) {
    uLongf out = dst_len;
    int r = uncompress(dst, &out, src, src_len);
    return (r == Z_OK && out == dst_len) ? 0 : -1;
}

void *oreo_platform_alloc(size_t size) {
    return malloc(size);
}

static void write_ppm(const char *dir, int n) {
    char path[512];
    snprintf(path, sizeof path, "%s/frame_%04d.ppm", dir, n);
    FILE *f = fopen(path, "wb");
    if (!f) {
        return;
    }
    fprintf(f, "P6\n%d %d\n255\n", OREO_DOOM_W, OREO_DOOM_H);
    const uint8_t *p = oreo_doom_frame();
    for (int i = 0; i < OREO_DOOM_W * OREO_DOOM_H; ++i) {
        unsigned v = (p[2 * i] << 8) | p[2 * i + 1];
        unsigned char rgb[3] = {(v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3};
        fwrite(rgb, 1, 3, f);
    }
    fclose(f);
}

// Scripted input by tick: start a game from the menu, then walk and shoot.
// With OREO_HOST_IDLE set nothing is pressed, so the title screen's attract
// loop plays every demo.
static int idle;

static uint32_t buttons_at(int t) {
    if (idle) return 0;
    if (t >= 40 && t < 42) return OREO_BTN_HOME;         // open menu
    if (t >= 50 && t < 52) return OREO_BTN_A;            // New Game
    if (t >= 60 && t < 62) return OREO_BTN_A;            // episode 1
    if (t >= 70 && t < 72) return OREO_BTN_A;            // skill
    if (t >= 150 && t < 250) return OREO_BTN_UP;         // walk forward
    if (t >= 250 && t < 280) return OREO_BTN_LEFT;       // turn
    if (t >= 280 && t < 300) return OREO_BTN_A;          // fire
    if (t >= 300 && t < 330) return OREO_BTN_C | OREO_BTN_RIGHT;   // strafe
    if (t >= 330 && t < 332) return OREO_BTN_C | OREO_BTN_UP;      // next weapon
    if (t >= 340 && t < 360) return OREO_BTN_B;          // use
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s file.owz outdir [ticks] [zone-MiB]\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        perror(argv[1]);
        return 2;
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *owz = malloc(size);
    if (fread(owz, 1, size, f) != (size_t)size) {
        return 2;
    }
    fclose(f);
    oreo_owz_data = owz;
    oreo_owz_size = size;

    int ticks = argc > 3 ? atoi(argv[3]) : 400;
    idle = getenv("OREO_HOST_IDLE") != NULL;
    char *zone = argc > 4 ? argv[4] : "4";
    char *dargv[] = {"doom", "-iwad", "owz:/freedoom1.wad", "-mb", zone, "-nosound", NULL};
    int r = oreo_doom_start(6, dargv);
    printf("start -> %d\n", r);
    if (r != 0) {
        return 1;
    }
    int frames = 0;
    for (int t = 0; t < ticks; ++t) {
        int d = oreo_doom_tick(buttons_at(t));
        if (d < 0) {
            printf("engine exited at tick %d (code %d)\n", t, oreo_doom_exit_code());
            return 1;
        }
        frames += d;
        if (t % (idle ? 2000 : 50) == 0 || t == ticks - 1) {
            write_ppm(argv[2], t);
        }
    }
    printf("ran %d ticks, %d frames drawn, simulated %u ms\n", ticks, frames, now_ms);
    return 0;
}
