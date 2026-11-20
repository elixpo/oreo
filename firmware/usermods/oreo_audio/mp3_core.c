// Streaming MP3 decoding for FaleraOS. See mp3_core.h.

#include <string.h>

#include "mp3_core.h"

// The scratch lives next to the decoder state: mp3dec_t is the first member
// of oreo_mp3_t, so minimp3's `dec` pointer is the oreo_mp3_t.
#define MINIMP3_SCRATCH_PTR(d)  ((mp3dec_scratch_t *)((oreo_mp3_t *)(d))->scratch)
#define MINIMP3_ONLY_MP3        // Layer III only: radio streams, smaller code
#define MINIMP3_NO_SIMD
#define MINIMP3_IMPLEMENTATION
#include "minimp3/minimp3.h"

// While resyncing, keep this much of the buffer's end: the start of a real
// frame there cannot be told apart from garbage until the rest arrives.
#define KEEP_TAIL  (MAX_FREE_FORMAT_FRAME_SIZE + HDR_SIZE)

size_t oreo_mp3_scratch_bytes(void) {
    return sizeof(mp3dec_scratch_t);
}

void oreo_mp3_init(oreo_mp3_t *m, void *scratch) {
    m->scratch = scratch;
    oreo_mp3_reset(m);
}

void oreo_mp3_reset(oreo_mp3_t *m) {
    mp3dec_init(&m->dec);
    m->in_len = 0;
    m->pending = 0;
    m->pending_hz = 0;
    m->pending_channels = 0;
    m->hz = 0;
    m->channels = 0;
    m->bitrate_kbps = 0;
    m->frames = 0;
    m->skipped = 0;
}

static void drop_input(oreo_mp3_t *m, size_t n) {
    if (n >= m->in_len) {
        m->in_len = 0;
        return;
    }
    memmove(m->in, m->in + n, m->in_len - n);
    m->in_len -= n;
}

// Interleaved frame -> mono, (L + R) / 2.
static void downmix(const int16_t *src, int16_t *dst, int samples, int channels) {
    if (channels == 1) {
        memcpy(dst, src, (size_t)samples * sizeof(int16_t));
        return;
    }
    for (int i = 0; i < samples; i++) {
        dst[i] = (int16_t)(((int32_t)src[2 * i] + (int32_t)src[2 * i + 1]) >> 1);
    }
}

oreo_mp3_result_t oreo_mp3_decode(oreo_mp3_t *m, const uint8_t *data, size_t len,
    int16_t *pcm, size_t cap, int flush) {
    oreo_mp3_result_t r = {0, 0, m->hz, m->channels};

    // A frame decoded on the last call but held back for its new rate.
    if (m->pending) {
        if (cap < (size_t)m->pending) {
            return r;
        }
        downmix(m->frame, pcm, m->pending, m->pending_channels);
        r.samples = m->pending;
        r.hz = m->hz = m->pending_hz;
        r.channels = m->channels = m->pending_channels;
        m->pending = 0;
    }

    size_t room = OREO_MP3_IN_BYTES - m->in_len;
    size_t take = len < room ? len : room;
    if (take) {
        memcpy(m->in + m->in_len, data, take);
        m->in_len += take;
    }
    r.consumed = take;
    // More input is still to come in this chunk: don't flush yet.
    if (take < len) {
        flush = 0;
    }

    while (cap - (size_t)r.samples >= OREO_MP3_FRAME_SAMPLES) {
        if (m->in_len < (flush ? (size_t)HDR_SIZE : (size_t)OREO_MP3_DECODE_MIN)) {
            break;
        }
        mp3dec_frame_info_t info;
        memset(&info, 0, sizeof(info));
        int n = mp3dec_decode_frame(&m->dec, m->in, (int)m->in_len, m->frame, &info);
        if (n <= 0) {
            // No frame here: skip what minimp3 says is not one, but keep a
            // tail that may be the start of the next frame.
            size_t skip = (size_t)info.frame_bytes;
            if (!flush && m->in_len > KEEP_TAIL && skip > m->in_len - KEEP_TAIL) {
                skip = m->in_len - KEEP_TAIL;
            } else if (!flush && m->in_len <= KEEP_TAIL) {
                skip = 0;
            }
            if (skip == 0) {
                if (flush) {
                    m->in_len = 0;      // nothing decodable is left
                }
                break;
            }
            m->skipped += (uint32_t)skip;
            drop_input(m, skip);
            continue;
        }
        drop_input(m, (size_t)info.frame_bytes);
        m->skipped += (uint32_t)info.frame_offset;
        m->frames++;
        m->bitrate_kbps = info.bitrate_kbps;
        if (r.samples > 0 && info.hz != r.hz) {
            // A new rate: hand this frame out on the next call.
            m->pending = n;
            m->pending_hz = info.hz;
            m->pending_channels = info.channels;
            break;
        }
        downmix(m->frame, pcm + r.samples, n, info.channels);
        r.samples += n;
        r.hz = m->hz = info.hz;
        r.channels = m->channels = info.channels;
    }
    return r;
}

void oreo_pcm_gain(int16_t *pcm, size_t n, int32_t gain) {
    if (gain == 65536) {
        return;
    }
    if (gain <= 0) {
        memset(pcm, 0, n * sizeof(int16_t));
        return;
    }
    for (size_t i = 0; i < n; i++) {
        int32_t v = (int32_t)(((int64_t)pcm[i] * gain) >> 16);
        if (v > 32767) {
            v = 32767;
        } else if (v < -32768) {
            v = -32768;
        }
        pcm[i] = (int16_t)v;
    }
}
