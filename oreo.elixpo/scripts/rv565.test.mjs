// Checks src/lib/rv565.ts against the RV565 format version 7 conformance
// vectors from github.com/elixpo/rv565 (tests/data/v7, a subset copied to
// scripts/fixtures/rv565-v7) and the version 6 reference vector.
//
//   npm run test:rv565            (node --test, no dependencies needed)
//
// With the reference Python package available, files written here are also
// decoded by it: set RV565_PYTHON_SRC to the package's source directory
// (rv565/python/src in the library repository), or install rv565 >= 2.0.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  CODECS, PIXEL_FORMATS, Rv565Encoder, Rv565Error, checkSchedule, convertPixels, decodeFrame,
  encodeClip, frameSize, frameTypeCounts, parseContainer, rgb565beToRgba, rgbaToRgb565be,
  testPatternFrame, toCArray, toRgba, verify,
} from "../src/lib/rv565.ts";

const FIXTURES = new URL("./fixtures/rv565-v7/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("manifest.json", FIXTURES), "utf8"));
const load = (file) => new Uint8Array(readFileSync(new URL(file, FIXTURES)));
const sha = (data) => createHash("sha256").update(data).digest("hex");
const TYPES = ["key", "delta", "repeat"];

/** tools/make_conformance.py rgb_frames(): a gradient with a moving square;
 * frame 5 repeats frame 4. */
function conformanceRgb() {
  const { width: W, height: H } = manifest;
  return Array.from({ length: 10 }, (_, f) => {
    const t = f <= 5 ? Math.min(f, 4) : f - 1;
    const out = new Uint8Array(3 * W * H);
    let o = 0;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const px = t * 2 <= x && x < t * 2 + 6 && 3 <= y && y < 9
          ? ((x + y) % 2 ? [255, 255, 255] : [255, 32, 0])
          : [Math.floor((x * 255) / (W - 1)), Math.floor((y * 255) / (H - 1)), 96];
        out.set(px, o);
        o += 3;
      }
    }
    return out;
  });
}

const rgbToRgba = (rgb) => {
  const out = new Uint8ClampedArray((rgb.length / 3) * 4);
  for (let i = 0, o = 0; i < rgb.length; i += 3, o += 4) out.set([rgb[i], rgb[i + 1], rgb[i + 2], 255], o);
  return out;
};

test("manifest covers every pixel format, both codecs, deltas, repeats and version 6", () => {
  const valid = manifest.valid;
  assert.deepEqual(new Set(valid.map((v) => v.pixel_format)), new Set(PIXEL_FORMATS));
  assert.deepEqual(new Set(valid.map((v) => v.codec)), new Set(CODECS));
  assert.ok(valid.some((v) => v.version === 6));
  assert.ok(valid.some((v) => v.codec === "stored" && v.frame_types.includes("delta")));
  assert.ok(valid.some((v) => v.frame_types.includes("repeat")));
});

for (const v of manifest.valid) {
  test(`decodes ${v.file}`, async () => {
    const clip = parseContainer(load(v.file));
    const h = clip.header;
    assert.deepEqual(
      [h.version, h.width, h.height, h.fps, h.frames, h.pixelFormat, h.codec, h.keyframeInterval, h.frameBytes],
      [v.version, v.width, v.height, v.fps, v.frames, v.pixel_format, v.codec, v.keyframe_interval, v.frame_bytes],
    );
    assert.deepEqual(clip.index.map((r) => TYPES[r.type]), v.frame_types);
    for (let i = 0; i < v.frames; i++) assert.equal(sha(await decodeFrame(clip, i)), v.frame_sha256[i], `frame ${i} in order`);
    // Random access: a fresh clip, frames in reverse, each a seek from a keyframe.
    const seek = parseContainer(load(v.file));
    for (let i = v.frames - 1; i >= 0; i--) {
      seek.last = undefined;
      assert.equal(sha(await decodeFrame(seek, i)), v.frame_sha256[i], `frame ${i} by seeking`);
    }
    // The preview path accepts every frame.
    assert.equal(toRgba(await decodeFrame(seek, 0), h.width, h.height, h.pixelFormat).length, 4 * h.width * h.height);
  });
}

for (const v of manifest.invalid) {
  test(`rejects ${v.file} (${v.reason}, at ${v.stage})`, async () => {
    const data = load(v.file);
    if (v.stage === "open") {
      assert.throws(() => parseContainer(data), Rv565Error);
    } else {
      const clip = parseContainer(data);
      await assert.rejects(verify(clip), Rv565Error);
    }
  });
}

test("pixel conversion is bit-identical to the reference rules", () => {
  const rgb = conformanceRgb();
  const { width: W, height: H } = manifest;
  for (const fmt of PIXEL_FORMATS) {
    const v = manifest.valid.find((e) => e.pixel_format === fmt && e.version === 7);
    rgb.forEach((frame, i) => {
      const out = convertPixels(frame, W, H, fmt, 3);
      assert.equal(out.length, frameSize(fmt, W, H));
      assert.equal(sha(out), v.frame_sha256[i], `${fmt} frame ${i}`);
      assert.deepEqual(convertPixels(rgbToRgba(frame), W, H, fmt, 4), out, `${fmt} frame ${i} from RGBA`);
    });
  }
});

test("RGB565 helpers keep their behaviour", () => {
  const be = Uint8Array.of(0xf8, 0x00, 0x07, 0xe0, 0x00, 0x1f, 0xff, 0xff, 0x00, 0x00);
  const rgba = rgb565beToRgba(be);
  assert.deepEqual(Array.from(rgba.subarray(0, 4)), [255, 0, 0, 255]);
  assert.deepEqual(Array.from(rgba.subarray(12, 16)), [255, 255, 255, 255]);
  assert.deepEqual(rgbaToRgb565be(rgba), be);
});

test("encoder chooses frames like the reference and round-trips every format and codec", async () => {
  const { width: W, height: H, fps } = manifest;
  const rgb = conformanceRgb();
  for (const pixelFormat of PIXEL_FORMATS) {
    const frames = rgb.map((f) => convertPixels(f, W, H, pixelFormat, 3));
    for (const codec of CODECS) {
      for (const keyframeInterval of [1, 3, 4, 255]) {
        const clip = parseContainer(await encodeClip(W, H, fps, frames, { pixelFormat, codec, keyframeInterval }));
        assert.equal(clip.header.version, 7);
        clip.index.forEach((r, i) => {
          if (i % keyframeInterval === 0) assert.equal(TYPES[r.type], "key", `${pixelFormat} ${codec} K${keyframeInterval} frame ${i}`);
          else if (i === 5) assert.equal(TYPES[r.type], "repeat", "frame 5 repeats frame 4");
          else if (codec === "stored") assert.equal(TYPES[r.type], "key", "a stored delta is never smaller");
        });
        if (codec === "zlib" && keyframeInterval === 255) {
          assert.ok(frameTypeCounts(clip).delta > 0, `${pixelFormat}: small motion makes deltas`);
        }
        for (let i = 0; i < frames.length; i++) assert.deepEqual(await decodeFrame(clip, i), frames[i]);
      }
    }
  }
});

test("writes version 6 for older players, and only what version 6 allows", async () => {
  const frames = Array.from({ length: 6 }, (_, i) => testPatternFrame(i, 6, 32, 16));
  const data = await encodeClip(32, 16, 12, frames, { version: 6 });
  assert.deepEqual(Array.from(data.subarray(0, 4)), [0x52, 0x56, 0x35, 6]);
  const clip = parseContainer(data);
  assert.equal(clip.header.headerSize, 12);
  for (let i = 0; i < 6; i++) assert.deepEqual(await decodeFrame(clip, i), frames[i]);
  for (const bad of [{ pixelFormat: "gray8" }, { codec: "stored" }, { keyframeInterval: 2 }]) {
    assert.throws(() => new Rv565Encoder(32, 16, 12, { version: 6, ...bad }), Rv565Error);
  }
  assert.throws(() => new Rv565Encoder(32, 16, 31, { version: 6 }), Rv565Error);
  assert.throws(() => new Rv565Encoder(32, 16, 61), Rv565Error);
  assert.throws(() => new Rv565Encoder(32, 16, 24, { keyframeInterval: 256 }), Rv565Error);
  assert.throws(() => new Rv565Encoder(0, 16, 24), Rv565Error);
});

test("v6 reference vector decodes to the test pattern", async () => {
  const clip = parseContainer(new Uint8Array(readFileSync(new URL("./fixtures/testpattern.rv565", import.meta.url))));
  for (let i = 0; i < 24; i++) assert.deepEqual(await decodeFrame(clip, i), testPatternFrame(i, 24, 180, 135), `frame ${i}`);
  const report = checkSchedule(clip, true);
  assert.equal(report.lateFrames, 0);
  assert.equal(report.worstFrameUs, 31312);
  const text = toCArray(clip, "testpattern.rv565");
  assert.match(text, /^\/\* Generated by tools\/rv565\.py from testpattern\.rv565: 180x135, 24 FPS, 24 frames\. \*\//);
  assert.match(text, /static const size_t rv565_clip_size = sizeof\(rv565_clip\);\n$/);
});

/* Cross-check with the reference Python package. */

const PY_CHECK = String.raw`
import json, sys
src = sys.argv[1]
if src:
    sys.path.insert(0, src)
import rv565
assert rv565.VERSION == 7, "rv565 %s reads only version 6" % rv565.__version__
d = sys.argv[2]
cases = json.load(open(d + "/cases.json"))
for c in cases:
    clip = rv565.open(d + "/" + c["file"])
    h = clip.header
    assert (h.version, h.width, h.height, h.fps, h.pixel_format, h.codec, h.keyframe_interval) == (
        c["version"], c["width"], c["height"], c["fps"], c["pixel_format"], c["codec"], c["keyframe_interval"]), c["file"]
    assert [clip.frame_type(i) for i in range(len(clip))] == c["types"], c["file"]
    rgb = open(d + "/" + c["rgb"], "rb").read()
    preview = open(d + "/" + c["preview"], "rb").read()
    n = 3 * h.width * h.height
    clip.verify()
    for i in range(len(clip)):
        src_rgb = rgb[i * n:(i + 1) * n]
        frame = clip.frame(i)
        assert frame == rv565.convert(src_rgb, h.width, h.height, h.pixel_format), (c["file"], i)
        assert rv565.to_rgb888(frame, h.width, h.height, h.pixel_format) == preview[i * n:(i + 1) * n], (c["file"], i)
print(len(cases))
`;

function findPython() {
  const src = process.env.RV565_PYTHON_SRC ?? "";
  const probe = spawnSync("python3", ["-I", "-c", "import sys\nif sys.argv[1]: sys.path.insert(0, sys.argv[1])\nimport rv565\nassert rv565.VERSION == 7", src]);
  return probe.status === 0 ? src : null;
}

const pySrc = findPython();

test("files written here decode identically with the reference Python package",
  { skip: pySrc === null && "reference rv565 >= 2.0 not found (set RV565_PYTHON_SRC)" }, async () => {
    const dir = mkdtempSync(join(tmpdir(), "rv565-js-"));
    try {
      // Odd sizes pad rows and pages; random noise exercises every value.
      let seed = 12345;
      const rand = () => (seed = (seed * 1103515245 + 12345) >>> 0) >>> 24;
      const W = 19, H = 11;
      const base = Uint8Array.from({ length: 3 * W * H }, rand);
      const rgb = Array.from({ length: 8 }, (_, f) => {
        if (f === 3) return null; // repeat of frame 2
        const frame = base.slice();
        for (let k = 0; k < 20 * f; k++) frame[rand() % frame.length] = rand();
        return frame;
      });
      rgb[3] = rgb[2];
      const cases = [];
      const writeCase = async (name, pixelFormat, codec, keyframeInterval, version = 7) => {
        const frames = rgb.map((f) => convertPixels(f, W, H, pixelFormat, 3));
        const data = await encodeClip(W, H, 30, frames, { pixelFormat, codec, keyframeInterval, version });
        const clip = parseContainer(data);
        const preview = [];
        for (let i = 0; i < frames.length; i++) {
          const rgba = toRgba(await decodeFrame(clip, i), W, H, pixelFormat);
          preview.push(Uint8Array.from({ length: 3 * W * H }, (_, j) => rgba[4 * Math.floor(j / 3) + (j % 3)]));
        }
        writeFileSync(join(dir, `${name}.rv565`), data);
        writeFileSync(join(dir, `${name}.preview`), Buffer.concat(preview));
        cases.push({
          file: `${name}.rv565`, rgb: "source.rgb", preview: `${name}.preview`, version, width: W, height: H, fps: 30,
          pixel_format: pixelFormat, codec, keyframe_interval: keyframeInterval,
          types: clip.index.map((r) => TYPES[r.type]),
        });
      };
      writeFileSync(join(dir, "source.rgb"), Buffer.concat(rgb));
      for (const fmt of PIXEL_FORMATS) {
        for (const codec of CODECS) await writeCase(`${fmt}_${codec}`, fmt, codec, 4);
      }
      await writeCase("rgb565be_v6", "rgb565be", "zlib", 1, 6);
      writeFileSync(join(dir, "cases.json"), JSON.stringify(cases));
      const run = spawnSync("python3", ["-I", "-c", PY_CHECK, pySrc, dir], { encoding: "utf8" });
      assert.equal(run.status, 0, run.stderr);
      assert.equal(run.stdout.trim(), String(cases.length));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
