/* RV565 container (format version 7, reads version 6) in the browser:
 * convert, encode, parse, decode.
 *
 * Mirrors the reference package in github.com/elixpo/rv565
 * (python/src/rv565, specified in docs/FORMAT.md):
 *
 *   header   "RV5", version, u16 width, u16 height, u8 fps, u8 flags,
 *            u16 frame count; version 7 adds u8 header size (16), u8 pixel
 *            format, u8 codec, u8 keyframe interval K
 *   records  u32 length, u8 frame type (key / XOR delta / repeat), body;
 *            version 6 records have no type byte and are all zlib keyframes
 *            of big-endian RGB565
 *
 * Colour conversion follows the reference rules exactly, so a frame
 * converted here is byte-identical to `rv565.convert` in Python; the
 * conformance vectors in scripts/fixtures/rv565-v7 check that.
 *
 * zlib framing comes from CompressionStream("deflate"), which is RFC 1950
 * zlib despite the name, so no compression library ships with the page. Its
 * compression level differs from the reference encoder's (level 1), so the
 * files are not byte-identical, but every decoded frame is.
 */

export const RV565_VERSION = 7;
export const RV565_VERSION_6 = 6;
export const RV565_HEADER_SIZE = 16;
export const RV565_HEADER_SIZE_V6 = 12;
export const RV565_MAX_FPS = 60;
export const RV565_MAX_FPS_V6 = 30;
export const RV565_MAX_FRAMES = 0xffff;
export const RV565_MAX_KEYFRAME_INTERVAL = 255;

/** Pixel formats by header value (docs/FORMAT.md, Pixel formats). */
export const PIXEL_FORMATS = [
  "rgb565be", "rgb565le", "rgb444", "rgb666", "rgb888", "gray8", "gray4", "mono", "mono_vpage",
] as const;
export type PixelFormat = (typeof PIXEL_FORMATS)[number];

export const CODECS = ["stored", "zlib"] as const;
export type Codec = (typeof CODECS)[number];

export const KEYFRAME = 0, DELTA = 1, REPEAT = 2;
export type FrameType = typeof KEYFRAME | typeof DELTA | typeof REPEAT;
export const FRAME_TYPE_NAMES = ["key", "delta", "repeat"] as const;

export type Rv565Header = {
  version: number;
  width: number;
  height: number;
  fps: number;
  flags: number;
  frames: number;
  headerSize: number;
  pixelFormat: PixelFormat;
  codec: Codec;
  keyframeInterval: number;
  /** Decoded size of one frame in bytes. */
  frameBytes: number;
};

export type Rv565Record = { type: FrameType; offset: number; length: number };

export type Rv565Clip = {
  header: Rv565Header;
  data: Uint8Array;
  /** Every frame's type and the [offset, length] of its body (0 for a repeat). */
  index: Rv565Record[];
  /** Last decoded frame, so playing in order costs one record per frame. */
  last?: { i: number; frame: Uint8Array };
};

export class Rv565Error extends Error {}

/* Pixel formats ----------------------------------------------------------- */

/** Bytes in one row of a frame (not defined for mono_vpage). */
export function rowBytes(format: PixelFormat, width: number): number {
  switch (format) {
    case "rgb565be": case "rgb565le": return 2 * width;
    case "rgb444": return (3 * width + 1) >> 1;
    case "rgb666": case "rgb888": return 3 * width;
    case "gray8": return width;
    case "gray4": return (width + 1) >> 1;
    case "mono": return (width + 7) >> 3;
    case "mono_vpage": throw new Rv565Error("mono_vpage has no rows");
  }
}

/** Decoded size in bytes of one frame. */
export function frameSize(format: PixelFormat, width: number, height: number): number {
  return format === "mono_vpage" ? width * ((height + 7) >> 3) : rowBytes(format, width) * height;
}

const luma = (r: number, g: number, b: number) => Math.floor((299 * r + 587 * g + 114 * b + 500) / 1000);

/** Packed pixels (RGB888 with `channels` 3, or canvas RGBA with 4) to one
 * frame in `format`, with the conversions in docs/FORMAT.md, Writing. */
export function convertPixels(
  src: Uint8Array | Uint8ClampedArray, width: number, height: number, format: PixelFormat, channels: 3 | 4 = 4,
): Uint8Array {
  if (src.length !== channels * width * height) {
    throw new Rv565Error(`expected ${channels * width * height} bytes of pixels, got ${src.length}`);
  }
  const out = new Uint8Array(frameSize(format, width, height));
  const n = width * height;
  switch (format) {
    case "rgb565be":
    case "rgb565le": {
      const [h, l] = format === "rgb565be" ? [0, 1] : [1, 0];
      for (let p = 0, i = 0; p < n; p++, i += channels) {
        const r = src[i], g = src[i + 1], b = src[i + 2];
        out[2 * p + h] = (r & 0xf8) | (g >> 5);
        out[2 * p + l] = ((g & 0x1c) << 3) | (b >> 3);
      }
      return out;
    }
    case "rgb888":
    case "rgb666": {
      const mask = format === "rgb666" ? 0xfc : 0xff;
      for (let p = 0, i = 0; p < n; p++, i += channels) {
        out[3 * p] = src[i] & mask;
        out[3 * p + 1] = src[i + 1] & mask;
        out[3 * p + 2] = src[i + 2] & mask;
      }
      return out;
    }
    case "rgb444": {
      const stride = rowBytes(format, width);
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const i = channels * (y * width + x);
          for (let k = 0; k < 3; k++) {
            const nib = 3 * x + k;
            out[y * stride + (nib >> 1)] |= (src[i + k] >> 4) << (nib & 1 ? 0 : 4);
          }
        }
      }
      return out;
    }
    default: {
      const stride = format === "mono_vpage" ? 0 : rowBytes(format, width);
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const i = channels * (y * width + x);
          const v = luma(src[i], src[i + 1], src[i + 2]);
          if (format === "gray8") out[y * width + x] = v;
          else if (format === "gray4") out[y * stride + (x >> 1)] |= (v >> 4) << (x & 1 ? 0 : 4);
          else if (v >= 128) {
            if (format === "mono") out[y * stride + (x >> 3)] |= 0x80 >> (x & 7);
            else out[(y >> 3) * width + x] |= 1 << (y & 7);
          }
        }
      }
      return out;
    }
  }
}

const expand = (bits: number) => {
  const top = (1 << bits) - 1;
  return Uint8Array.from({ length: 1 << bits }, (_, v) => Math.floor((v * 255 + (top >> 1)) / top));
};
const E5 = expand(5), E6 = expand(6);

/** One frame in `format` to RGBA pixels, for previews; the same values as the
 * reference `rv565.to_rgb888` (channels with fewer bits scaled to 0-255). */
export function toRgba(
  frame: Uint8Array, width: number, height: number, format: PixelFormat, out?: Uint8ClampedArray,
): Uint8ClampedArray {
  if (frame.length !== frameSize(format, width, height)) {
    throw new Rv565Error(`expected ${frameSize(format, width, height)} bytes, got ${frame.length}`);
  }
  const rgba = out ?? new Uint8ClampedArray(4 * width * height);
  const stride = format === "mono_vpage" ? 0 : rowBytes(format, width);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const p = y * width + x, o = 4 * p;
      let r: number, g: number, b: number;
      switch (format) {
        case "rgb565be":
        case "rgb565le": {
          const hi = frame[2 * p + (format === "rgb565be" ? 0 : 1)];
          const lo = frame[2 * p + (format === "rgb565be" ? 1 : 0)];
          r = E5[hi >> 3]; g = E6[((hi & 7) << 3) | (lo >> 5)]; b = E5[lo & 0x1f];
          break;
        }
        case "rgb888": r = frame[3 * p]; g = frame[3 * p + 1]; b = frame[3 * p + 2]; break;
        case "rgb666": r = E6[frame[3 * p] >> 2]; g = E6[frame[3 * p + 1] >> 2]; b = E6[frame[3 * p + 2] >> 2]; break;
        case "rgb444": {
          const nib = (k: number) => {
            const n = 3 * x + k;
            return ((frame[y * stride + (n >> 1)] >> (n & 1 ? 0 : 4)) & 0xf) * 17;
          };
          r = nib(0); g = nib(1); b = nib(2);
          break;
        }
        case "gray8": r = g = b = frame[p]; break;
        case "gray4": {
          const byte = frame[y * stride + (x >> 1)];
          r = g = b = (x & 1 ? byte & 0xf : byte >> 4) * 17;
          break;
        }
        case "mono": r = g = b = frame[y * stride + (x >> 3)] & (0x80 >> (x & 7)) ? 255 : 0; break;
        default: r = g = b = frame[(y >> 3) * width + x] & (1 << (y & 7)) ? 255 : 0;
      }
      rgba[o] = r; rgba[o + 1] = g; rgba[o + 2] = b; rgba[o + 3] = 255;
    }
  }
  return rgba;
}

/** RGBA pixels (canvas ImageData) to big-endian RGB565. */
export const rgbaToRgb565be = (rgba: Uint8ClampedArray | Uint8Array) =>
  convertPixels(rgba, rgba.length / 4, 1, "rgb565be");

/** Big-endian RGB565 to RGBA pixels. */
export const rgb565beToRgba = (src: Uint8Array, out?: Uint8ClampedArray) =>
  toRgba(src, src.length / 2, 1, "rgb565be", out);

/* zlib -------------------------------------------------------------------- */

async function pipe(data: Uint8Array, stream: CompressionStream | DecompressionStream): Promise<Uint8Array> {
  const piped = new Blob([data as BlobPart]).stream().pipeThrough(stream);
  return new Uint8Array(await new Response(piped).arrayBuffer());
}

export const zlibCompress = (data: Uint8Array) => pipe(data, new CompressionStream("deflate"));
export const zlibInflate = (data: Uint8Array) => pipe(data, new DecompressionStream("deflate"));

/** Inflate a body that must give exactly `size` bytes; stops reading as soon
 * as it gives more, so a hostile file cannot fill the tab's memory. */
async function inflateExact(body: Uint8Array, size: number, i: number): Promise<Uint8Array> {
  const reader = new Blob([body as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate")).getReader();
  const out = new Uint8Array(size);
  let n = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (n + value.length > size) {
        reader.cancel().catch(() => {});
        throw new Rv565Error(`frame ${i} inflates to more than ${size} bytes`);
      }
      out.set(value, n);
      n += value.length;
    }
  } catch (e) {
    if (e instanceof Rv565Error) throw e;
    throw new Rv565Error(`frame ${i} does not inflate: ${e instanceof Error ? e.message : e}`);
  }
  if (n !== size) throw new Rv565Error(`frame ${i} inflates to ${n} bytes, expected ${size}`);
  return out;
}

const xor = (a: Uint8Array, b: Uint8Array) => {
  const out = new Uint8Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] ^ b[i];
  return out;
};

const equal = (a: Uint8Array, b: Uint8Array) => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
};

/* Encoding ---------------------------------------------------------------- */

export type EncodeOptions = {
  /** 7 (default) or 6, for players older than RV565 2.0 (rgb565be, zlib, K = 1 only). */
  version?: 6 | 7;
  pixelFormat?: PixelFormat;
  codec?: Codec;
  /** A keyframe at least every K frames (1-255). */
  keyframeInterval?: number;
};

/** Writes a clip one frame at a time, holding only the previous frame and the
 * encoded records. Frame choice is the reference encoder's: frames at
 * multiples of K are keyframes; any other frame is a repeat when it equals
 * the previous one, else the smaller of a delta and a keyframe (a stored delta
 * is never smaller, so stored clips use only keyframes and repeats). */
export class Rv565Encoder {
  readonly width: number;
  readonly height: number;
  readonly fps: number;
  readonly version: 6 | 7;
  readonly pixelFormat: PixelFormat;
  readonly codec: Codec;
  readonly keyframeInterval: number;
  readonly frameBytes: number;
  private prev: Uint8Array | null = null;
  private records: Array<{ type: FrameType; body: Uint8Array }> = [];

  constructor(width: number, height: number, fps: number, options: EncodeOptions = {}) {
    this.width = width;
    this.height = height;
    this.fps = fps;
    this.version = options.version ?? RV565_VERSION;
    this.pixelFormat = options.pixelFormat ?? "rgb565be";
    this.codec = options.codec ?? "zlib";
    this.keyframeInterval = options.keyframeInterval ?? 1;
    if (!(Number.isInteger(width) && width > 0 && width <= 0xffff && Number.isInteger(height) && height > 0 && height <= 0xffff)) {
      throw new Rv565Error(`size ${width}x${height} out of range`);
    }
    if (!PIXEL_FORMATS.includes(this.pixelFormat)) throw new Rv565Error(`unknown pixel format ${this.pixelFormat}`);
    if (!CODECS.includes(this.codec)) throw new Rv565Error(`unknown codec ${this.codec}`);
    const k = this.keyframeInterval;
    if (!(Number.isInteger(k) && k >= 1 && k <= RV565_MAX_KEYFRAME_INTERVAL)) throw new Rv565Error("keyframe interval must be 1-255");
    if (this.version === RV565_VERSION_6) {
      if (this.pixelFormat !== "rgb565be" || this.codec !== "zlib" || k !== 1) {
        throw new Rv565Error("version 6 supports only rgb565be, zlib, keyframe interval 1");
      }
      if (!(fps >= 1 && fps <= RV565_MAX_FPS_V6)) throw new Rv565Error(`fps must be 1-${RV565_MAX_FPS_V6}`);
    } else if (this.version === RV565_VERSION) {
      if (!(fps >= 1 && fps <= RV565_MAX_FPS)) throw new Rv565Error(`fps must be 1-${RV565_MAX_FPS}`);
    } else {
      throw new Rv565Error(`can write version 6 or 7, not ${this.version}`);
    }
    this.frameBytes = frameSize(this.pixelFormat, width, height);
  }

  get frames() { return this.records.length; }

  private encode(data: Uint8Array) {
    return this.codec === "stored" ? data.slice() : zlibCompress(data);
  }

  /** Add one frame, already in the clip's pixel format; returns its type. */
  async add(frame: Uint8Array): Promise<FrameType> {
    const i = this.records.length;
    if (i >= RV565_MAX_FRAMES) throw new Rv565Error(`more than ${RV565_MAX_FRAMES} frames`);
    if (frame.length !== this.frameBytes) throw new Rv565Error(`frame ${i} has ${frame.length} bytes, expected ${this.frameBytes}`);
    const prev = this.prev;
    let record: { type: FrameType; body: Uint8Array };
    if (i % this.keyframeInterval === 0 || !prev) {
      record = { type: KEYFRAME, body: await this.encode(frame) };
    } else if (equal(frame, prev)) {
      record = { type: REPEAT, body: new Uint8Array(0) };
    } else {
      const key = await this.encode(frame);
      const delta = this.codec === "stored" ? key : await this.encode(xor(frame, prev));
      record = delta.length < key.length ? { type: DELTA, body: delta } : { type: KEYFRAME, body: key };
    }
    this.records.push(record);
    this.prev = frame.slice();
    return record.type;
  }

  /** The finished file. */
  finish(): Uint8Array {
    const n = this.records.length;
    if (n === 0) throw new Rv565Error("no frames");
    const v6 = this.version === RV565_VERSION_6;
    const headerSize = v6 ? RV565_HEADER_SIZE_V6 : RV565_HEADER_SIZE;
    const perRecord = v6 ? 4 : 5;
    const out = new Uint8Array(this.records.reduce((t, r) => t + perRecord + r.body.length, headerSize));
    const view = new DataView(out.buffer);
    out.set([0x52, 0x56, 0x35, this.version], 0);
    view.setUint16(4, this.width, true);
    view.setUint16(6, this.height, true);
    out[8] = this.fps;
    out[9] = 0;
    view.setUint16(10, n, true);
    if (!v6) {
      out[12] = RV565_HEADER_SIZE;
      out[13] = PIXEL_FORMATS.indexOf(this.pixelFormat);
      out[14] = CODECS.indexOf(this.codec);
      out[15] = this.keyframeInterval;
    }
    let offset = headerSize;
    for (const { type, body } of this.records) {
      view.setUint32(offset, body.length + (v6 ? 0 : 1), true);
      offset += 4;
      if (!v6) out[offset++] = type;
      out.set(body, offset);
      offset += body.length;
    }
    return out;
  }
}

/** Encode frames (already in the pixel format) into a whole file. */
export async function encodeClip(
  width: number, height: number, fps: number, frames: Iterable<Uint8Array>, options: EncodeOptions = {},
): Promise<Uint8Array> {
  const encoder = new Rv565Encoder(width, height, fps, options);
  for (const frame of frames) await encoder.add(frame);
  return encoder.finish();
}

/* Decoding ---------------------------------------------------------------- */

/** Parse and range-check a version 6 or 7 header. */
export function parseHeader(data: Uint8Array): Rv565Header {
  if (data.length < RV565_HEADER_SIZE_V6) throw new Rv565Error("file too short");
  if (data[0] !== 0x52 || data[1] !== 0x56 || data[2] !== 0x35) throw new Rv565Error("not an RV565 file");
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const version = data[3];
  const width = view.getUint16(4, true), height = view.getUint16(6, true);
  const fps = data[8], flags = data[9], frames = view.getUint16(10, true);
  if (version === RV565_VERSION_6) {
    if (!width || !height || fps < 1 || fps > RV565_MAX_FPS_V6 || !frames) throw new Rv565Error("invalid header");
    return {
      version, width, height, fps, flags, frames, headerSize: RV565_HEADER_SIZE_V6,
      pixelFormat: "rgb565be", codec: "zlib", keyframeInterval: 1, frameBytes: 2 * width * height,
    };
  }
  if (version !== RV565_VERSION) throw new Rv565Error(`unsupported RV565 version ${version}`);
  if (data.length < RV565_HEADER_SIZE) throw new Rv565Error("file too short");
  if (!width || !height || fps < 1 || fps > RV565_MAX_FPS || !frames) throw new Rv565Error("invalid header");
  const headerSize = data[12], format = data[13], codec = data[14], keyframeInterval = data[15];
  if (headerSize < RV565_HEADER_SIZE || data.length < headerSize) throw new Rv565Error(`invalid header size ${headerSize}`);
  if (format >= PIXEL_FORMATS.length) throw new Rv565Error(`unsupported pixel format ${format}`);
  if (codec >= CODECS.length) throw new Rv565Error(`unsupported codec ${codec}`);
  if (keyframeInterval === 0) throw new Rv565Error("invalid keyframe interval 0");
  const pixelFormat = PIXEL_FORMATS[format];
  return {
    version, width, height, fps, flags, frames, headerSize, pixelFormat, codec: CODECS[codec],
    keyframeInterval, frameBytes: frameSize(pixelFormat, width, height),
  };
}

/** Validate a whole container and index its frames (docs/FORMAT.md,
 * Validation): everything except whether each zlib body inflates to the
 * frame size, which decodeFrame and verify check. */
export function parseContainer(data: Uint8Array): Rv565Clip {
  const header = parseHeader(data);
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const v6 = header.version === RV565_VERSION_6;
  const index: Rv565Record[] = [];
  let offset = header.headerSize;
  for (let i = 0; i < header.frames; i++) {
    if (data.length - offset < 4) throw new Rv565Error(`truncated frame table at frame ${i}`);
    const length = view.getUint32(offset, true);
    offset += 4;
    if (length === 0 || data.length - offset < length) throw new Rv565Error(`invalid length for frame ${i}`);
    if (v6) {
      index.push({ type: KEYFRAME, offset, length });
    } else {
      const type = data[offset];
      if (type > REPEAT) throw new Rv565Error(`unsupported frame type ${type} at frame ${i}`);
      if (i % header.keyframeInterval === 0 && type !== KEYFRAME) throw new Rv565Error(`frame ${i} must be a keyframe`);
      if (type === REPEAT && length !== 1) throw new Rv565Error(`repeat frame ${i} has a body`);
      if (type !== REPEAT && header.codec === "stored" && length - 1 !== header.frameBytes) {
        throw new Rv565Error(`stored frame ${i} has ${length - 1} bytes, expected ${header.frameBytes}`);
      }
      index.push({ type: type as FrameType, offset: offset + 1, length: length - 1 });
    }
    offset += length;
  }
  if (offset !== data.length) throw new Rv565Error("trailing bytes after the last frame");
  return { header, data, index };
}

async function body(clip: Rv565Clip, i: number): Promise<Uint8Array> {
  const { offset, length } = clip.index[i];
  const raw = clip.data.subarray(offset, offset + length);
  return clip.header.codec === "stored" ? raw.slice() : inflateExact(raw, clip.header.frameBytes, i);
}

/** Frame i in the clip's pixel format (header.frameBytes bytes). Decoding in
 * order applies one record per frame; a seek starts at the keyframe at or
 * before i, at most K - 1 records back. Callers must not modify the result. */
export async function decodeFrame(clip: Rv565Clip, i: number): Promise<Uint8Array> {
  if (!(Number.isInteger(i) && i >= 0 && i < clip.header.frames)) throw new RangeError(`frame ${i} out of range`);
  if (clip.last?.i === i) return clip.last.frame;
  let start: number, frame: Uint8Array;
  if (clip.last?.i === i - 1) {
    start = i - 1;
    frame = clip.last.frame;
  } else {
    start = i;
    while (clip.index[start].type !== KEYFRAME) start--;
    frame = await body(clip, start);
  }
  for (let j = start + 1; j <= i; j++) {
    const type = clip.index[j].type;
    if (type === KEYFRAME) frame = await body(clip, j);
    else if (type === DELTA) frame = xor(frame, await body(clip, j));
  }
  clip.last = { i, frame };
  return frame;
}

/** Decode every frame; throws Rv565Error on the first bad one. */
export async function verify(clip: Rv565Clip): Promise<number> {
  clip.last = undefined;
  for (let i = 0; i < clip.header.frames; i++) await decodeFrame(clip, i);
  return clip.header.frames;
}

export function frameTypeCounts(clip: Rv565Clip) {
  const counts = { key: 0, delta: 0, repeat: 0 };
  for (const { type } of clip.index) counts[FRAME_TYPE_NAMES[type]]++;
  return counts;
}

/* Schedulability: the paper's pooled ESP32-S3 decode-cost model. ---------- */

export const COST_ESP32S3_180x135 = { interceptUs: 4858.0, slopeUsPerByte: 0.1515 };
/** Display transfer per frame for a 320x240 panel at 40 MHz SPI. */
export const TRANSFER_320x240_US = 31312.0;

export type ScheduleReport = { lateFrames: number; worstFrameUs: number; periodUs: number; maxPayload: number };

/** Predicted missed deadlines from the body sizes alone, as the reference
 * `Clip.check_schedule`. The model was fitted on rgb565be zlib keyframes;
 * repeats cost nothing to decode. */
export function checkSchedule(clip: Rv565Clip, overlap: boolean, transferUs = TRANSFER_320x240_US): ScheduleReport {
  const m = COST_ESP32S3_180x135;
  const periodUs = 1e6 / clip.header.fps;
  let lateFrames = 0, worstFrameUs = 0, maxPayload = 0;
  for (const { length } of clip.index) {
    const inflate = length ? m.interceptUs + m.slopeUsPerByte * length : 0;
    const work = overlap ? Math.max(transferUs, inflate) : transferUs + inflate;
    if (work > periodUs) lateFrames++;
    worstFrameUs = Math.max(worstFrameUs, work);
    maxPayload = Math.max(maxPayload, length);
  }
  return { lateFrames, worstFrameUs, periodUs, maxPayload };
}

/** The container as a C header, matching `rv565 c-array`. */
export function toCArray(clip: Rv565Clip, sourceName: string, name = "rv565_clip"): string {
  const { width, height, fps, frames } = clip.header;
  const lines = [
    `/* Generated by tools/rv565.py from ${sourceName}: ${width}x${height}, ${fps} FPS, ${frames} frames. */`,
    "#pragma once", "#include <stddef.h>", "#include <stdint.h>", "",
    `static const uint8_t ${name}[] __attribute__((aligned(4))) = {`,
  ];
  const hex = (b: number) => "0x" + b.toString(16).padStart(2, "0");
  for (let i = 0; i < clip.data.length; i += 16) {
    lines.push("    " + Array.from(clip.data.subarray(i, i + 16), hex).join(", ") + ",");
  }
  lines.push("};", `static const size_t ${name}_size = sizeof(${name});`, "");
  return lines.join("\n");
}

/** Scrolling colour bars, identical to `rv565 testpattern` frames (RGB565 BE). */
export function testPatternFrame(f: number, count: number, width: number, height: number): Uint8Array {
  const bars = [[255, 255, 255], [255, 255, 0], [0, 255, 255], [0, 255, 0],
                [255, 0, 255], [255, 0, 0], [0, 0, 255], [0, 0, 0]];
  const shift = Math.floor((f * width) / count);
  const row = new Uint8Array(width * 2);
  for (let x = 0; x < width; x++) {
    const [r, g, b] = bars[Math.floor((((x + shift) % width) * bars.length) / width)];
    const v = ((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3);
    row[2 * x] = v >> 8;
    row[2 * x + 1] = v & 0xff;
  }
  const out = new Uint8Array(width * height * 2);
  for (let y = 0; y < height; y++) out.set(row, y * row.length);
  return out;
}
