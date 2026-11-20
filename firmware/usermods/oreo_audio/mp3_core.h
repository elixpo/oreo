// Streaming MP3 decoding for FaleraOS, on top of minimp3 (minimp3/).
//
// Plain C with no MicroPython in it, so the host tests build it with cc
// (tests/test_mp3_decoder.py) and the firmware wraps it (modoreo_audio.c).
//
// The caller feeds the stream in chunks of any size; whole frames are
// decoded into a caller-supplied int16 buffer, downmixed to mono, and a
// partial frame at the end of a chunk waits in `in` for the next one.

#ifndef OREO_MP3_CORE_H
#define OREO_MP3_CORE_H

#include <stddef.h>
#include <stdint.h>

#include "minimp3/minimp3.h"

// The largest Layer III frame is 1441 bytes (MPEG-1, 320 kb/s, 32 kHz,
// padded); free-format frames may reach 2304. A frame is decoded only once
// it and the next frame's header are buffered (minimp3 checks that header to
// stay in sync), so decoding waits for OREO_MP3_DECODE_MIN bytes unless the
// stream has ended.
#define OREO_MP3_IN_BYTES       8192
#define OREO_MP3_DECODE_MIN     3072
#define OREO_MP3_FRAME_SAMPLES  1152        // per channel, MPEG-1 Layer III

typedef struct {
    mp3dec_t dec;
    // minimp3's per-frame work area (~16 KB, an mp3dec_scratch_t). It is
    // not on the stack: a MicroPython thread has 16 KB at most.
    void *scratch;
    uint8_t in[OREO_MP3_IN_BYTES];
    size_t in_len;
    int16_t frame[OREO_MP3_FRAME_SAMPLES * 2];   // one decoded frame, interleaved
    int pending;                // mono samples of a decoded frame not yet handed out
    int pending_hz;
    int pending_channels;
    int hz;                     // of the last frame handed out, 0 before the first
    int channels;
    int bitrate_kbps;
    uint32_t frames;            // frames decoded since the last reset
    uint32_t skipped;           // bytes dropped while looking for a frame
} oreo_mp3_t;

typedef struct {
    size_t consumed;            // bytes of the input chunk taken (the rest: call again)
    int samples;                // mono samples written to pcm
    int hz;                     // their sample rate (0 when samples == 0 and none yet)
    int channels;               // channels in the stream (1 or 2)
} oreo_mp3_result_t;

// Bytes of scratch memory oreo_mp3_init needs (minimp3's work area).
size_t oreo_mp3_scratch_bytes(void);

// scratch: oreo_mp3_scratch_bytes() of memory the decoder keeps using.
void oreo_mp3_init(oreo_mp3_t *m, void *scratch);
void oreo_mp3_reset(oreo_mp3_t *m);

// Take as much of data[0:len] as fits, then decode whole frames into
// pcm[0:cap] (mono int16) until it is full, the buffered input runs short,
// or the sample rate changes (all samples of one call share one rate). At
// the end of a stream pass flush = 1 to decode what is left. cap must be at
// least OREO_MP3_FRAME_SAMPLES for any frame to fit.
oreo_mp3_result_t oreo_mp3_decode(oreo_mp3_t *m, const uint8_t *data, size_t len,
    int16_t *pcm, size_t cap, int flush);

// Scale n int16 samples in place by gain / 65536, with saturation.
void oreo_pcm_gain(int16_t *pcm, size_t n, int32_t gain);

#endif
