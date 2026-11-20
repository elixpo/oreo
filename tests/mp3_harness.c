// Host harness for the firmware's MP3 decoder (firmware/usermods/oreo_audio).
// tests/test_mp3_decoder.py builds it with cc together with mp3_core.c.
//
//   mp3_harness IN.mp3 OUT.pcm [SEED]
//       Feed IN.mp3 to the decoder in pseudo-random chunks of 1..1500 bytes
//       (SEED picks them), with a PCM buffer of 1152..4608 samples, write the
//       mono s16le output to OUT.pcm and print "hz channels samples frames
//       skipped" on stdout.
//   mp3_harness --bench IN.mp3 REPEATS
//       Decode IN.mp3 REPEATS times and print "audio_seconds cpu_seconds".

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "mp3_core.h"

static unsigned char *read_file(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *buf = malloc((size_t)n);
    if (buf && fread(buf, 1, (size_t)n, f) != (size_t)n) {
        free(buf);
        buf = NULL;
    }
    fclose(f);
    *len = (size_t)n;
    return buf;
}

static unsigned rng = 1;
static unsigned next_rand(void) {
    rng = rng * 1103515245u + 12345u;
    return (rng >> 16) & 0x7fff;
}

// Decode the whole file; returns total samples, writes them to out if given.
static long decode_all(oreo_mp3_t *m, const unsigned char *mp3, size_t len,
    FILE *out, int random_chunks, int *hz, int *channels) {
    static int16_t pcm[4608];
    size_t pos = 0;
    long total = 0;
    int idle = 0;
    oreo_mp3_reset(m);
    for (;;) {
        size_t chunk = random_chunks ? 1 + next_rand() % 1500 : 4096;
        if (chunk > len - pos) {
            chunk = len - pos;
        }
        size_t cap = random_chunks ? 1152 + next_rand() % (4608 - 1152 + 1) : 4608;
        int flush = pos + chunk >= len;
        oreo_mp3_result_t r = oreo_mp3_decode(m, mp3 + pos, chunk, pcm, cap, flush);
        pos += r.consumed;
        if (r.samples > 0) {
            if (out) {
                fwrite(pcm, sizeof(int16_t), (size_t)r.samples, out);
            }
            total += r.samples;
            *hz = r.hz;
            *channels = r.channels;
        }
        if (pos >= len && r.consumed == 0 && r.samples == 0) {
            if (++idle > 2) {
                break;
            }
        } else {
            idle = 0;
        }
    }
    return total;
}

int main(int argc, char **argv) {
    static oreo_mp3_t m;
    void *scratch = malloc(oreo_mp3_scratch_bytes());
    oreo_mp3_init(&m, scratch);
    int hz = 0, channels = 0;

    if (argc == 4 && strcmp(argv[1], "--bench") == 0) {
        size_t len;
        unsigned char *mp3 = read_file(argv[2], &len);
        if (!mp3) {
            return 2;
        }
        int repeats = atoi(argv[3]);
        long samples = 0;
        clock_t t0 = clock();
        for (int i = 0; i < repeats; i++) {
            samples += decode_all(&m, mp3, len, NULL, 0, &hz, &channels);
        }
        double cpu = (double)(clock() - t0) / CLOCKS_PER_SEC;
        printf("%f %f\n", hz ? (double)samples / hz : 0.0, cpu);
        return 0;
    }
    if (argc < 3) {
        fprintf(stderr, "usage: mp3_harness IN.mp3 OUT.pcm [SEED]\n");
        return 2;
    }
    if (argc > 3) {
        rng = (unsigned)strtoul(argv[3], NULL, 10);
    }
    size_t len;
    unsigned char *mp3 = read_file(argv[1], &len);
    FILE *out = fopen(argv[2], "wb");
    if (!mp3 || !out) {
        return 2;
    }
    long total = decode_all(&m, mp3, len, out, 1, &hz, &channels);
    fclose(out);
    printf("%d %d %ld %u %u\n", hz, channels, total, (unsigned)m.frames, (unsigned)m.skipped);
    return 0;
}
