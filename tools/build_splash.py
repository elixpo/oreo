"""Render the boot splash's artwork into oreoOS/splash.bin.

The badge has no font engine for anti-aliased type or complex scripts, so
the greetings ("hello" in many languages, each in its own script), the
small "OreoOS" line and the logo are rendered here, on the host, already
blended onto the splash background. oreoOS/splash.py only copies rows.

    python3 tools/build_splash.py               # writes oreoOS/splash.bin
    python3 tools/build_splash.py --preview out.png

Fonts (SIL Open Font License 1.1, rendered to bitmaps): Inter SemiBold for
Latin and Cyrillic, Noto Sans Bold for Indic scripts and Arabic, Noto Sans
CJK Bold for Japanese, Chinese and Korean. Pillow must be built with libraqm
so Devanagari, Bengali, Tamil and Arabic are shaped correctly.

splash.bin layout (little-endian header, pixels are big-endian RGB565, the
panel's byte order):

    "OSP1" | u8 count | u8 0 | u16 band_h | u16 bg565
    u16 logo_w | u16 logo_h | logo pixels
    u16 tag_w  | u16 tag_h  | tag pixels
    count x ( u16 w | w * band_h pixels )
"""

import argparse
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "oreoOS" / "splash.bin"
LOGO_SRC = ROOT / "oreo.elixpo" / "public" / "favicon.ico"

BG = (255, 248, 235)      # theme.BG
INK = (38, 38, 48)        # theme.DARK
TAG = (255, 93, 104)      # theme.PRIMARY

BAND_H = 64
MAX_W = 300
SIZE = 44
LOGO = 36
TAG_SIZE = 15

INTER = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
INTER_TAG = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
NOTO = "/usr/share/fonts/truetype/noto/NotoSans%s-Bold.ttf"
CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

# (text, font path, ttc index, language tag for shaping)
GREETINGS = [
    ("hello", INTER, 0, "en"),
    ("नमस्ते", NOTO % "Devanagari", 0, "hi"),
    ("hola", INTER, 0, "es"),
    ("নমস্কার", NOTO % "Bengali", 0, "bn"),
    ("bonjour", INTER, 0, "fr"),
    ("こんにちは", CJK, 0, "ja"),
    ("வணக்கம்", NOTO % "Tamil", 0, "ta"),
    ("ciao", INTER, 0, "it"),
    ("你好", CJK, 2, "zh"),
    ("olá", INTER, 0, "pt"),
    ("안녕하세요", CJK, 1, "ko"),
    ("hallo", INTER, 0, "de"),
    ("مرحبا", NOTO % "Arabic", 0, "ar"),
    ("привет", INTER, 0, "ru"),
    ("ನಮಸ್ಕಾರ", NOTO % "Kannada", 0, "kn"),
    ("merhaba", INTER, 0, "tr"),
]


def rgb565_be(img):
    out = bytearray()
    pixels = img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()
    for r, g, b in pixels:
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out += struct.pack(">H", v)
    return bytes(out)


def render_text(text, path, index, lang, size, colour, height=None):
    """Text shaped and anti-aliased onto BG, tightly cropped in width and
    centred on its ink in a band of `height` rows (or cropped if None)."""
    while True:
        font = ImageFont.truetype(path, size, index=index,
                                  layout_engine=ImageFont.Layout.RAQM)
        kw = {"language": lang} if lang else {}
        x0, y0, x1, y1 = font.getbbox(text, **kw)
        if x1 - x0 <= MAX_W or size <= 20:
            break
        size -= 2
    w = x1 - x0 + 4
    h = (y1 - y0 + 4) if height is None else height
    img = Image.new("RGB", (w, h), BG)
    ImageDraw.Draw(img).text((2 - x0, (h - (y1 - y0)) // 2 - y0), text,
                             font=font, fill=colour, **kw)
    return img


def render_logo():
    src = Image.open(LOGO_SRC)
    sizes = getattr(src, "info", {}).get("sizes")
    if sizes:
        src.size = max(sizes)
    src = src.convert("RGBA")
    src.thumbnail((LOGO, LOGO), Image.LANCZOS)
    img = Image.new("RGB", (LOGO, LOGO), BG)
    img.paste(src, ((LOGO - src.width) // 2, (LOGO - src.height) // 2), src)
    return img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--preview", type=Path)
    args = p.parse_args()
    if not features.check("raqm"):
        raise SystemExit("Pillow needs libraqm to shape Indic and Arabic text")

    logo = render_logo()
    tag = render_text("OreoOS", INTER_TAG, 0, "en", TAG_SIZE, TAG)
    words = [render_text(t, f, i, lang, SIZE, INK, BAND_H)
             for t, f, i, lang in GREETINGS]

    bg565 = ((BG[0] & 0xF8) << 8) | ((BG[1] & 0xFC) << 3) | (BG[2] >> 3)
    blob = bytearray(b"OSP1" + struct.pack("<BBHH", len(words), 0, BAND_H, bg565))
    blob += struct.pack("<HH", logo.width, logo.height) + rgb565_be(logo)
    blob += struct.pack("<HH", tag.width, tag.height) + rgb565_be(tag)
    for img in words:
        blob += struct.pack("<H", img.width) + rgb565_be(img)
    args.out.write_bytes(blob)
    print("wrote %s: %d greetings, %.1f KB" % (args.out, len(words), len(blob) / 1024))

    if args.preview:
        sheet = Image.new("RGB", (320, 240 + BAND_H * len(words)), BG)
        sheet.paste(logo, (12, 12))
        y_band = (240 - BAND_H) // 2 - 6
        sheet.paste(words[0], ((320 - words[0].width) // 2, y_band))
        sheet.paste(tag, ((320 - tag.width) // 2, y_band + BAND_H + 2))
        ImageDraw.Draw(sheet).line((0, 240, 320, 240), fill=(200, 160, 140))
        for k, img in enumerate(words):
            sheet.paste(img, ((320 - img.width) // 2, 240 + k * BAND_H))
        sheet.save(args.preview)


if __name__ == "__main__":
    main()
