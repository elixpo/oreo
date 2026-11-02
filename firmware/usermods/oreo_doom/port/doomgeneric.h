// SPDX-License-Identifier: GPL-2.0-or-later
// Platform interface the engine's i_video.c / i_system.c expect, written for
// the Oreo Badge port. The engine draws 8-bit palette indices (CMAP256) into
// DG_ScreenBuffer and calls DG_DrawFrame() once per rendered frame.

#ifndef DOOM_GENERIC
#define DOOM_GENERIC

#include <stdint.h>
#include <stdlib.h>

#define DOOMGENERIC_RESX 320
#define DOOMGENERIC_RESY 200

typedef uint8_t pixel_t;
extern pixel_t *DG_ScreenBuffer;

#ifdef __cplusplus
extern "C" {
#endif

void doomgeneric_Create(int argc, char **argv);
void doomgeneric_Tick(void);

void DG_Init(void);
void DG_DrawFrame(void);
void DG_SleepMs(uint32_t ms);
uint32_t DG_GetTicksMs(void);
int DG_GetKey(int *pressed, unsigned char *key);
void DG_SetWindowTitle(const char *title);

#ifdef __cplusplus
}
#endif

#endif
