// SPDX-License-Identifier: GPL-2.0-or-later
// Oreo Badge port of the Doom engine: engine start-up and one-step ticking,
// the badge's buttons as Doom keys, and the 8-bit frame converted to the
// panel's RGB565. Replaces doomgeneric.c and dummy.c from doomgeneric.
//
// Controls:
//   D-pad      move / turn (menus: navigate)
//   A          fire (menus: select)
//   B          use, open doors (prompts: yes)
//   C (hold)   strafe with LEFT/RIGHT; C+UP cycles weapons 1-7
//   HOME       menu (the OreoOS app turns a second HOME within 1 s into exit)

#include <setjmp.h>
#include <string.h>

#include "doom.h"
#include "doomgeneric.h"
#include "doomkeys.h"
#include "doomtype.h"
#include "i_video.h"
#include "m_argv.h"
#include "oreo_doom.h"

pixel_t *DG_ScreenBuffer = NULL;

// Engine symbols normally provided by doomgeneric.c / dummy.c.
boolean net_client_connected = false;
boolean drone = false;
void I_InitTimidityConfig(void) {
}

void M_FindResponseFile(void);

extern struct color colors[256];
extern boolean palette_changed;

static jmp_buf trap;
static int in_engine;
static int started;
static int running;
static int exit_code;
static int frame_drawn;

static uint8_t *frame;          // OREO_DOOM_W * OREO_DOOM_H * 2
static uint8_t lut[256][2];     // palette index -> big-endian RGB565

void oreo_doom_exit(int code) {
    exit_code = code;
    running = 0;
    if (in_engine) {
        longjmp(trap, 1);
    }
    for (;;) {
        // Not reachable: the engine only exits from inside start/tick.
    }
}

void doomgeneric_Create(int argc, char **argv) {
    myargc = argc;
    myargv = argv;
    M_FindResponseFile();
    DG_Init();
    D_DoomMain();
}

// ── keys ──────────────────────────────────────────────────────────────────

#define KEYQ 32
static struct { uint8_t pressed, key; } keyq[KEYQ];
static unsigned keyq_head, keyq_tail;
static uint32_t prev_buttons;
static int weapon = 1;
static int up_cycled_weapon;

static void push_key(int pressed, unsigned char key) {
    unsigned next = (keyq_head + 1) % KEYQ;
    if (next != keyq_tail) {
        keyq[keyq_head].pressed = pressed;
        keyq[keyq_head].key = key;
        keyq_head = next;
    }
}

int DG_GetKey(int *pressed, unsigned char *key) {
    if (keyq_tail == keyq_head) {
        return 0;
    }
    *pressed = keyq[keyq_tail].pressed;
    *key = keyq[keyq_tail].key;
    keyq_tail = (keyq_tail + 1) % KEYQ;
    return 1;
}

static void feed_buttons(uint32_t buttons) {
    uint32_t changed = buttons ^ prev_buttons;
    prev_buttons = buttons;
    if (!changed) {
        return;
    }
    for (uint32_t bit = 1; bit <= OREO_BTN_RIGHT; bit <<= 1) {
        if (!(changed & bit)) {
            continue;
        }
        int down = (buttons & bit) != 0;
        switch (bit) {
            case OREO_BTN_HOME:
                push_key(down, KEY_ESCAPE);
                break;
            case OREO_BTN_A:
                push_key(down, KEY_FIRE);
                push_key(down, KEY_ENTER);
                break;
            case OREO_BTN_B:
                push_key(down, KEY_USE);
                push_key(down, 'y');
                break;
            case OREO_BTN_C:
                push_key(down, KEY_RALT);       // strafe modifier
                break;
            case OREO_BTN_UP:
                if (down && (buttons & OREO_BTN_C)) {
                    weapon = weapon % 7 + 1;
                    push_key(1, '0' + weapon);
                    push_key(0, '0' + weapon);
                    up_cycled_weapon = 1;
                } else if (!down && up_cycled_weapon) {
                    up_cycled_weapon = 0;
                } else {
                    push_key(down, KEY_UPARROW);
                }
                break;
            case OREO_BTN_DOWN:
                push_key(down, KEY_DOWNARROW);
                break;
            case OREO_BTN_LEFT:
                push_key(down, KEY_LEFTARROW);
                break;
            case OREO_BTN_RIGHT:
                push_key(down, KEY_RIGHTARROW);
                break;
        }
    }
}

// ── platform hooks the engine calls ───────────────────────────────────────

void DG_Init(void) {
}

void DG_SetWindowTitle(const char *title) {
    (void)title;
}

void DG_SleepMs(uint32_t ms) {
    oreo_platform_sleep_ms(ms);
}

uint32_t DG_GetTicksMs(void) {
    return oreo_platform_ms();
}

void DG_DrawFrame(void) {
    if (palette_changed) {
        for (int i = 0; i < 256; ++i) {
            unsigned v = ((colors[i].r & 0xF8) << 8) | ((colors[i].g & 0xFC) << 3) | (colors[i].b >> 3);
            lut[i][0] = v >> 8;
            lut[i][1] = v & 0xFF;
        }
        palette_changed = false;
    }
    uint8_t *out = frame + OREO_DOOM_TOP * OREO_DOOM_W * 2;
    const pixel_t *in = DG_ScreenBuffer;
    for (int i = 0; i < DOOMGENERIC_RESX * DOOMGENERIC_RESY; ++i) {
        out[0] = lut[in[i]][0];
        out[1] = lut[in[i]][1];
        out += 2;
    }
    frame_drawn = 1;
}

// ── public interface (oreo_doom.h) ────────────────────────────────────────

int oreo_doom_start(int argc, char **argv) {
    if (running) {
        return 0;               // resume the running game
    }
    if (started) {
        return -2;              // the engine has quit; it cannot restart in place
    }
    started = 1;
    if (!DG_ScreenBuffer) {
        DG_ScreenBuffer = oreo_platform_alloc(DOOMGENERIC_RESX * DOOMGENERIC_RESY);
        frame = oreo_platform_alloc(OREO_DOOM_W * OREO_DOOM_H * 2);
        if (!DG_ScreenBuffer || !frame) {
            return -1;
        }
        memset(frame, 0, OREO_DOOM_W * OREO_DOOM_H * 2);   // black bars
    }
    exit_code = 0;
    if (setjmp(trap)) {
        in_engine = 0;
        return exit_code ? exit_code : -1;
    }
    in_engine = 1;
    doomgeneric_Create(argc, argv);
    in_engine = 0;
    running = 1;
    return 0;
}

int oreo_doom_tick(uint32_t buttons) {
    if (!running) {
        return -1;
    }
    feed_buttons(buttons);
    frame_drawn = 0;
    if (setjmp(trap)) {
        in_engine = 0;
        return -1;
    }
    in_engine = 1;
    doomgeneric_Tick();
    in_engine = 0;
    return frame_drawn;
}

int oreo_doom_running(void) {
    return running;
}

int oreo_doom_exit_code(void) {
    return exit_code;
}

const uint8_t *oreo_doom_frame(void) {
    return frame;
}
