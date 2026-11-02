// SPDX-License-Identifier: GPL-2.0-or-later
// WAD file class for OWZ images (tools/pack_wad.py): presents a compressed,
// per-lump zlib OWZ as an ordinary uncompressed WAD to the engine.
//
// The virtual WAD is laid out as the engine expects: 12-byte header, every
// lump's uncompressed data in directory order, then the 16-byte-per-lump
// directory. Reads of the header and directory are synthesised; reads inside
// a lump inflate that lump. W_ReadLump reads whole lumps, so the common case
// inflates straight into the engine's buffer with no copy.

#include <string.h>

#include "m_misc.h"
#include "oreo_doom.h"
#include "w_file.h"
#include "z_zone.h"

const uint8_t *oreo_owz_data;
size_t oreo_owz_size;

#define OWZ_HEADER 16
#define OWZ_ENTRY 20
#define WAD_HEADER 12
#define WAD_ENTRY 16

typedef struct {
    char name[8];
    uint32_t size;          // uncompressed
    uint32_t offset;        // virtual offset in the uncompressed WAD
    const uint8_t *data;    // in the OWZ image
    uint32_t stored;        // == size when stored uncompressed
} owz_lump_t;

typedef struct {
    wad_file_t wad;
    owz_lump_t *lumps;
    uint32_t count;
    uint32_t dir_offset;    // virtual offset of the WAD directory
    char ident[4];
    uint8_t *scratch;       // one lump, for reads that do not cover a whole lump
    uint32_t scratch_size;
} owz_wad_file_t;

extern wad_file_class_t owz_wad_file;

static uint32_t rd32(const uint8_t *p) {
    return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void wr32(uint8_t *p, uint32_t v) {
    p[0] = v;
    p[1] = v >> 8;
    p[2] = v >> 16;
    p[3] = v >> 24;
}

static wad_file_t *W_OWZ_OpenFile(char *path) {
    (void)path;
    const uint8_t *d = oreo_owz_data;
    size_t n = oreo_owz_size;
    if (!d || n < OWZ_HEADER || memcmp(d, "OWZ1", 4) != 0) {
        return NULL;
    }
    uint32_t count = rd32(d + 8);
    uint32_t dir = rd32(d + 12);
    if (dir > n || count > (n - dir) / OWZ_ENTRY) {
        return NULL;
    }

    owz_wad_file_t *f = Z_Malloc(sizeof(*f), PU_STATIC, 0);
    memset(f, 0, sizeof(*f));
    f->lumps = Z_Malloc(count * sizeof(owz_lump_t), PU_STATIC, 0);
    f->count = count;
    memcpy(f->ident, d + 4, 4);

    uint32_t virt = WAD_HEADER;
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *e = d + dir + i * OWZ_ENTRY;
        owz_lump_t *l = &f->lumps[i];
        memcpy(l->name, e, 8);
        l->size = rd32(e + 8);
        uint32_t off = rd32(e + 12);
        l->stored = rd32(e + 16);
        if (off > dir || l->stored > dir - off || (l->stored != l->size && l->size == 0)) {
            Z_Free(f->lumps);
            Z_Free(f);
            return NULL;
        }
        l->data = d + off;
        l->offset = virt;
        virt += l->size;
        if (l->size > f->scratch_size) {
            f->scratch_size = l->size;
        }
    }
    f->dir_offset = virt;
    f->wad.file_class = &owz_wad_file;
    f->wad.mapped = NULL;
    f->wad.length = virt + count * WAD_ENTRY;
    return &f->wad;
}

static void W_OWZ_CloseFile(wad_file_t *wad) {
    owz_wad_file_t *f = (owz_wad_file_t *)wad;
    if (f->scratch) {
        Z_Free(f->scratch);
    }
    Z_Free(f->lumps);
    Z_Free(f);
}

// Index of the lump containing virtual offset `pos` (lumps are in order).
static uint32_t find_lump(owz_wad_file_t *f, uint32_t pos) {
    uint32_t lo = 0, hi = f->count;
    while (hi - lo > 1) {
        uint32_t mid = (lo + hi) / 2;
        if (f->lumps[mid].offset <= pos) {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    return lo;
}

static int lump_into(owz_lump_t *l, uint8_t *dst) {
    if (l->stored == l->size) {
        memcpy(dst, l->data, l->size);
        return 0;
    }
    return oreo_platform_inflate(dst, l->size, l->data, l->stored);
}

static size_t W_OWZ_Read(wad_file_t *wad, unsigned int offset, void *buffer, size_t len) {
    owz_wad_file_t *f = (owz_wad_file_t *)wad;
    uint8_t *out = buffer;
    size_t done = 0;

    while (done < len && offset < f->wad.length) {
        if (offset < WAD_HEADER) {
            uint8_t h[WAD_HEADER];
            memcpy(h, f->ident, 4);
            wr32(h + 4, f->count);
            wr32(h + 8, f->dir_offset);
            size_t n = WAD_HEADER - offset;
            if (n > len - done) {
                n = len - done;
            }
            memcpy(out + done, h + offset, n);
            done += n;
            offset += n;
        } else if (offset >= f->dir_offset) {
            uint32_t i = (offset - f->dir_offset) / WAD_ENTRY;
            uint32_t within = (offset - f->dir_offset) % WAD_ENTRY;
            uint8_t e[WAD_ENTRY];
            wr32(e, f->lumps[i].offset);
            wr32(e + 4, f->lumps[i].size);
            memcpy(e + 8, f->lumps[i].name, 8);
            size_t n = WAD_ENTRY - within;
            if (n > len - done) {
                n = len - done;
            }
            memcpy(out + done, e + within, n);
            done += n;
            offset += n;
        } else {
            owz_lump_t *l = &f->lumps[find_lump(f, offset)];
            uint32_t within = offset - l->offset;
            size_t n = l->size - within;
            if (n > len - done) {
                n = len - done;
            }
            if (n == 0) {
                break;          // zero-size lump at this offset: skip forward
            }
            if (within == 0 && n == l->size) {
                if (lump_into(l, out + done) != 0) {
                    break;
                }
            } else {
                if (!f->scratch) {
                    f->scratch = Z_Malloc(f->scratch_size, PU_STATIC, 0);
                }
                if (lump_into(l, f->scratch) != 0) {
                    break;
                }
                memcpy(out + done, f->scratch + within, n);
            }
            done += n;
            offset += n;
        }
    }
    return done;
}

wad_file_class_t owz_wad_file = {
    W_OWZ_OpenFile,
    W_OWZ_CloseFile,
    W_OWZ_Read,
};
