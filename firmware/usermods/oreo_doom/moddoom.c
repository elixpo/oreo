// SPDX-License-Identifier: GPL-2.0-or-later
// _oreo_doom: Doom on the Oreo Badge.
//
// The game data is an OWZ image (tools/pack_wad.py) in the "doom" flash
// partition, memory-mapped and inflated a lump at a time by the ESP32-S3 ROM
// inflater. The Doom app (apps/doom) drives the engine one step per frame:
//
//   import _oreo_doom as doom
//   doom.available()          # True when the doom partition holds an OWZ
//   doom.start()              # 0 when running (resumes an existing game)
//   drawn = doom.tick(mask)   # button mask in oreoOS.api BTN_* bit order
//   display.blit_fullscreen(doom.frame())

#include <string.h>

#include "py/mphal.h"
#include "py/runtime.h"

#include "esp_heap_caps.h"
#include "esp_partition.h"
#include "miniz.h"

#include "port/oreo_doom.h"

#define DOOM_PARTITION "doom"

static const esp_partition_t *partition;
static esp_partition_mmap_handle_t mmap_handle;
static const uint8_t *mapped;
static tinfl_decompressor inflator;     // ~11 KiB: kept off the task stack

// ── platform hooks for the port ───────────────────────────────────────────

uint32_t oreo_platform_ms(void) {
    return mp_hal_ticks_ms();
}

void oreo_platform_sleep_ms(uint32_t ms) {
    mp_hal_delay_ms(ms);
}

int oreo_platform_inflate(void *dst, size_t dst_len, const void *src, size_t src_len) {
    size_t in = src_len;
    size_t out = dst_len;
    tinfl_init(&inflator);
    tinfl_status status = tinfl_decompress(&inflator, src, &in, dst, dst, &out,
        TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
    return (status == TINFL_STATUS_DONE && out == dst_len) ? 0 : -1;
}

void *oreo_platform_alloc(size_t size) {
    void *p = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    return p ? p : malloc(size);
}

// ── game data ─────────────────────────────────────────────────────────────

static const esp_partition_t *find_partition(void) {
    return esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY,
        DOOM_PARTITION);
}

static bool partition_has_owz(const esp_partition_t *p) {
    uint8_t magic[4];
    return p && esp_partition_read(p, 0, magic, sizeof magic) == ESP_OK
           && memcmp(magic, "OWZ1", 4) == 0;
}

static void map_game_data(void) {
    if (mapped) {
        return;
    }
    partition = find_partition();
    if (!partition_has_owz(partition)) {
        mp_raise_OSError(MP_ENOENT);
    }
    const void *ptr;
    if (esp_partition_mmap(partition, 0, partition->size, ESP_PARTITION_MMAP_DATA,
            &ptr, &mmap_handle) != ESP_OK) {
        mp_raise_OSError(MP_ENOMEM);
    }
    mapped = ptr;
    // OWZ size: the directory ends the image (header field + count * 20).
    uint32_t count = mapped[8] | (mapped[9] << 8) | (mapped[10] << 16) | ((uint32_t)mapped[11] << 24);
    uint32_t dir = mapped[12] | (mapped[13] << 8) | (mapped[14] << 16) | ((uint32_t)mapped[15] << 24);
    oreo_owz_data = mapped;
    oreo_owz_size = dir + (size_t)count * 20;
    if (oreo_owz_size > partition->size) {
        oreo_owz_size = partition->size;
    }
}

// ── Python API ────────────────────────────────────────────────────────────

static mp_obj_t doom_available(void) {
    return mp_obj_new_bool(partition_has_owz(find_partition()));
}
static MP_DEFINE_CONST_FUN_OBJ_0(doom_available_obj, doom_available);

static mp_obj_t doom_start(size_t n_args, const mp_obj_t *args) {
    static char zone[4];
    static char *argv[] = {"doom", "-iwad", "owz:/freedoom1.wad", "-mb", zone, NULL};
    int zone_mb = n_args > 0 ? mp_obj_get_int(args[0]) : 4;
    if (zone_mb < 2 || zone_mb > 6) {
        mp_raise_ValueError(MP_ERROR_TEXT("zone must be 2-6 MiB"));
    }
    map_game_data();
    zone[0] = '0' + zone_mb;
    zone[1] = 0;
    return mp_obj_new_int(oreo_doom_start(5, argv));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(doom_start_obj, 0, 1, doom_start);

static mp_obj_t doom_tick(mp_obj_t buttons) {
    return mp_obj_new_int(oreo_doom_tick(mp_obj_get_int(buttons)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(doom_tick_obj, doom_tick);

static mp_obj_t doom_frame(void) {
    const uint8_t *frame = oreo_doom_frame();
    if (!frame) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Doom not started"));
    }
    return mp_obj_new_memoryview('B', OREO_DOOM_W * OREO_DOOM_H * 2, (void *)frame);
}
static MP_DEFINE_CONST_FUN_OBJ_0(doom_frame_obj, doom_frame);

static mp_obj_t doom_running(void) {
    return mp_obj_new_bool(oreo_doom_running());
}
static MP_DEFINE_CONST_FUN_OBJ_0(doom_running_obj, doom_running);

static mp_obj_t doom_exit_code(void) {
    return mp_obj_new_int(oreo_doom_exit_code());
}
static MP_DEFINE_CONST_FUN_OBJ_0(doom_exit_code_obj, doom_exit_code);

static const mp_rom_map_elem_t doom_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__oreo_doom)},
    {MP_ROM_QSTR(MP_QSTR_available), MP_ROM_PTR(&doom_available_obj)},
    {MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&doom_start_obj)},
    {MP_ROM_QSTR(MP_QSTR_tick), MP_ROM_PTR(&doom_tick_obj)},
    {MP_ROM_QSTR(MP_QSTR_frame), MP_ROM_PTR(&doom_frame_obj)},
    {MP_ROM_QSTR(MP_QSTR_running), MP_ROM_PTR(&doom_running_obj)},
    {MP_ROM_QSTR(MP_QSTR_exit_code), MP_ROM_PTR(&doom_exit_code_obj)},
};
static MP_DEFINE_CONST_DICT(doom_module_globals, doom_module_globals_table);

const mp_obj_module_t oreo_doom_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&doom_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__oreo_doom, oreo_doom_module);
