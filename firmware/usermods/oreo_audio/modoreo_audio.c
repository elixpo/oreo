// _oreo_audio: firmware-resident MP3 decoding and PCM gain for FaleraOS.
//
//   d = _oreo_audio.MP3Decoder()
//   consumed, samples, hz, channels = d.decode(chunk, pcm, flush=False)
//   d.info()   -> (hz, channels, bitrate_kbps, frames, skipped_bytes)
//   d.reset()  -> forget buffered input and decoder state (a new stream)
//   d.deinit() -> free the decoder's memory now
//   _oreo_audio.gain(pcm, q16)  -> scale int16 samples in place by q16/65536
//
// decode() takes as much of `chunk` as fits in the decoder's input buffer
// (pass the rest on the next call), decodes whole frames into `pcm` (a
// writable buffer of int16 samples, mono: stereo is downmixed here) and
// returns how many bytes it took, how many samples it wrote and their rate.
// A frame cut off at the end of a chunk stays buffered until the next one.
//
// The decoder state and its 8 KB input buffer live on the MicroPython heap
// (PSRAM on the badge). minimp3's ~16 KB scratch is taken from internal RAM
// when there is room, which is faster, and from the heap otherwise.

#include <string.h>

#include "py/runtime.h"
#include "py/mphal.h"

#include "mp3_core.h"

#if defined(ESP_PLATFORM)
#include "esp_heap_caps.h"
#endif

typedef struct _oreo_mp3_obj_t {
    mp_obj_base_t base;
    oreo_mp3_t *m;              // MicroPython heap
    void *scratch;              // internal RAM (heap_caps) or MicroPython heap
    bool scratch_caps;          // scratch came from heap_caps_malloc
} oreo_mp3_obj_t;

static void oreo_mp3_free(oreo_mp3_obj_t *self) {
    if (self->scratch != NULL) {
        #if defined(ESP_PLATFORM)
        if (self->scratch_caps) {
            heap_caps_free(self->scratch);
        }
        #endif
        // A heap scratch is reclaimed by the GC once nothing points at it.
        self->scratch = NULL;
    }
    self->m = NULL;
}

static oreo_mp3_t *oreo_mp3_get(oreo_mp3_obj_t *self) {
    if (self->m == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("decoder closed"));
    }
    return self->m;
}

static mp_obj_t oreo_mp3_make_new(const mp_obj_type_t *type, size_t n_args,
    size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 0, 0, false);
    oreo_mp3_obj_t *self = mp_obj_malloc_with_finaliser(oreo_mp3_obj_t, type);
    self->m = NULL;
    self->scratch = NULL;
    self->scratch_caps = false;
    size_t scratch_bytes = oreo_mp3_scratch_bytes();
    #if defined(ESP_PLATFORM)
    self->scratch = heap_caps_malloc(scratch_bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    self->scratch_caps = self->scratch != NULL;
    #endif
    if (self->scratch == NULL) {
        self->scratch = m_malloc(scratch_bytes);
    }
    self->m = m_malloc(sizeof(oreo_mp3_t));
    oreo_mp3_init(self->m, self->scratch);
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t mp3obj_decode(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_data, ARG_pcm, ARG_flush };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_data, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_pcm, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_flush, MP_ARG_BOOL, {.u_bool = false} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args,
        MP_ARRAY_SIZE(allowed_args), allowed_args, args);
    oreo_mp3_obj_t *self = MP_OBJ_TO_PTR(pos_args[0]);
    oreo_mp3_t *m = oreo_mp3_get(self);

    mp_buffer_info_t data;
    if (args[ARG_data].u_obj == mp_const_none) {
        data.buf = NULL;
        data.len = 0;
    } else {
        mp_get_buffer_raise(args[ARG_data].u_obj, &data, MP_BUFFER_READ);
    }
    mp_buffer_info_t pcm;
    mp_get_buffer_raise(args[ARG_pcm].u_obj, &pcm, MP_BUFFER_WRITE);
    if (((uintptr_t)pcm.buf & 1) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("pcm buffer not aligned"));
    }

    oreo_mp3_result_t r = oreo_mp3_decode(m, (const uint8_t *)data.buf, data.len,
        (int16_t *)pcm.buf, pcm.len / sizeof(int16_t), args[ARG_flush].u_bool);

    mp_obj_t items[4] = {
        mp_obj_new_int_from_uint(r.consumed),
        MP_OBJ_NEW_SMALL_INT(r.samples),
        MP_OBJ_NEW_SMALL_INT(r.hz),
        MP_OBJ_NEW_SMALL_INT(r.channels),
    };
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(oreo_mp3_decode_obj, 3, mp3obj_decode);

static mp_obj_t oreo_mp3_info(mp_obj_t self_in) {
    oreo_mp3_t *m = oreo_mp3_get(MP_OBJ_TO_PTR(self_in));
    mp_obj_t items[5] = {
        MP_OBJ_NEW_SMALL_INT(m->hz),
        MP_OBJ_NEW_SMALL_INT(m->channels),
        MP_OBJ_NEW_SMALL_INT(m->bitrate_kbps),
        mp_obj_new_int_from_uint(m->frames),
        mp_obj_new_int_from_uint(m->skipped),
    };
    return mp_obj_new_tuple(5, items);
}
static MP_DEFINE_CONST_FUN_OBJ_1(oreo_mp3_info_obj, oreo_mp3_info);

static mp_obj_t oreo_mp3_reset_m(mp_obj_t self_in) {
    oreo_mp3_reset(oreo_mp3_get(MP_OBJ_TO_PTR(self_in)));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(oreo_mp3_reset_obj, oreo_mp3_reset_m);

static mp_obj_t oreo_mp3_deinit(mp_obj_t self_in) {
    oreo_mp3_free(MP_OBJ_TO_PTR(self_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(oreo_mp3_deinit_obj, oreo_mp3_deinit);

static const mp_rom_map_elem_t oreo_mp3_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_decode), MP_ROM_PTR(&oreo_mp3_decode_obj) },
    { MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&oreo_mp3_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&oreo_mp3_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&oreo_mp3_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&oreo_mp3_deinit_obj) },
};
static MP_DEFINE_CONST_DICT(oreo_mp3_locals, oreo_mp3_locals_table);

static MP_DEFINE_CONST_OBJ_TYPE(
    oreo_mp3_type,
    MP_QSTR_MP3Decoder,
    MP_TYPE_FLAG_NONE,
    make_new, oreo_mp3_make_new,
    locals_dict, &oreo_mp3_locals
    );

static mp_obj_t oreo_audio_gain(mp_obj_t pcm_obj, mp_obj_t gain_obj) {
    mp_buffer_info_t pcm;
    mp_get_buffer_raise(pcm_obj, &pcm, MP_BUFFER_WRITE);
    if (((uintptr_t)pcm.buf & 1) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("pcm buffer not aligned"));
    }
    oreo_pcm_gain((int16_t *)pcm.buf, pcm.len / sizeof(int16_t), mp_obj_get_int(gain_obj));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(oreo_audio_gain_obj, oreo_audio_gain);

static const mp_rom_map_elem_t oreo_audio_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__oreo_audio) },
    { MP_ROM_QSTR(MP_QSTR_MP3Decoder), MP_ROM_PTR(&oreo_mp3_type) },
    { MP_ROM_QSTR(MP_QSTR_gain), MP_ROM_PTR(&oreo_audio_gain_obj) },
    { MP_ROM_QSTR(MP_QSTR_FRAME_SAMPLES), MP_ROM_INT(OREO_MP3_FRAME_SAMPLES) },
};
static MP_DEFINE_CONST_DICT(oreo_audio_module_globals, oreo_audio_module_globals_table);

const mp_obj_module_t oreo_audio_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&oreo_audio_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__oreo_audio, oreo_audio_module);
