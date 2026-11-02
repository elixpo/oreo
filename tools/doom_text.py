#!/usr/bin/env python3
"""Make Doom's text readable on the badge's 2" screen.

Freedoom draws its text with heavy dark outlines and drop shadows, which run
together at the badge's native 320x200. This restyles the text graphics in a
WAD's lumps (as read by tools/pack_wad.py), used by tools/fetch_freedoom.py:

  * the small font (pickup messages, prompts, level names; STCFN033-095) is
    replaced with a 5x7 font with one-pixel strokes, drawn here, with a
    one-pixel dark shadow so it stays readable over bright walls;
  * large text (status bar and intermission numbers, intermission labels,
    menu words) loses its dark outline: edge pixels much darker than the
    glyph's brightest colour are made transparent. Sizes and offsets stay
    the same, so nothing on screen moves.

Doom patch format: width, height, left and top offset (int16), one u32
offset per column, then per column a list of posts (top, length, pad,
pixels..., pad) ended by 0xFF; palette-indexed, unlisted pixels transparent.
"""

import re
import struct

# The small font: Doom's heads-up font covers '!' to '_' (upper case only).
# Each glyph is 7 rows; the patch adds a column and a row for the shadow, which
# also spaces letters and lines (the engine spaces lines by the glyph height).
FONT = {
    "!": "# # # # # . #",
    '"': "#.# #.# ... ... ... ... ...",
    "#": ".#.#. .#.#. ##### .#.#. ##### .#.#. .#.#.",
    "$": "..#.. .#### #.#.. .###. ..#.# ####. ..#..",
    "%": "##..# ##..# ...#. ..#.. .#... #..## #..##",
    "&": ".##.. #..#. #.#.. .#... #.#.# #..#. .##.#",
    "'": "# # . . . . .",
    "(": ".# #. #. #. #. #. .#",
    ")": "#. .# .# .# .# .# #.",
    "*": "..... #.#.# .###. ##### .###. #.#.# .....",
    "+": "..... ..#.. ..#.. ##### ..#.. ..#.. .....",
    ",": ".. .. .. .. .. .# #.",
    "-": ".... .... .... #### .... .... ....",
    ".": ". . . . . . #",
    "/": "....# ....# ...#. ..#.. .#... #.... #....",
    "0": ".###. #...# #..## #.#.# ##..# #...# .###.",
    "1": "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
    "2": ".###. #...# ....# ...#. ..#.. .#... #####",
    "3": "####. ....# ....# .###. ....# ....# ####.",
    "4": "...#. ..##. .#.#. #..#. ##### ...#. ...#.",
    "5": "##### #.... ####. ....# ....# #...# .###.",
    "6": ".###. #.... #.... ####. #...# #...# .###.",
    "7": "##### ....# ...#. ..#.. .#... .#... .#...",
    "8": ".###. #...# #...# .###. #...# #...# .###.",
    "9": ".###. #...# #...# .#### ....# ....# .###.",
    ":": ". # . . . # .",
    ";": ".. .# .. .. .. .# #.",
    "<": "...# ..#. .#.. #... .#.. ..#. ...#",
    "=": ".... .... #### .... #### .... ....",
    ">": "#... .#.. ..#. ...# ..#. .#.. #...",
    "?": ".###. #...# ....# ...#. ..#.. ..... ..#..",
    "@": ".###. #...# #.### #.#.# #.### #.... .###.",
    "A": ".###. #...# #...# ##### #...# #...# #...#",
    "B": "####. #...# #...# ####. #...# #...# ####.",
    "C": ".###. #...# #.... #.... #.... #...# .###.",
    "D": "####. #...# #...# #...# #...# #...# ####.",
    "E": "##### #.... #.... ####. #.... #.... #####",
    "F": "##### #.... #.... ####. #.... #.... #....",
    "G": ".###. #...# #.... #.### #...# #...# .###.",
    "H": "#...# #...# #...# ##### #...# #...# #...#",
    "I": ".###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.",
    "J": "..### ...#. ...#. ...#. #..#. #..#. .##..",
    "K": "#...# #..#. #.#.. ##... #.#.. #..#. #...#",
    "L": "#.... #.... #.... #.... #.... #.... #####",
    "M": "#...# ##.## #.#.# #.#.# #...# #...# #...#",
    "N": "#...# #...# ##..# #.#.# #..## #...# #...#",
    "O": ".###. #...# #...# #...# #...# #...# .###.",
    "P": "####. #...# #...# ####. #.... #.... #....",
    "Q": ".###. #...# #...# #...# #.#.# #..#. .##.#",
    "R": "####. #...# #...# ####. #.#.. #..#. #...#",
    "S": ".###. #...# #.... .###. ....# #...# .###.",
    "T": "##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "U": "#...# #...# #...# #...# #...# #...# .###.",
    "V": "#...# #...# #...# #...# #...# .#.#. ..#..",
    "W": "#...# #...# #...# #.#.# #.#.# #.#.# .#.#.",
    "X": "#...# #...# .#.#. ..#.. .#.#. #...# #...#",
    "Y": "#...# #...# .#.#. ..#.. ..#.. ..#.. ..#..",
    "Z": "##### ....# ...#. ..#.. .#... #.... #####",
    "[": "## #. #. #. #. #. ##",
    "\\": "#.... #.... .#... ..#.. ...#. ....# ....#",
    "]": "## .# .# .# .# .# ##",
    "^": "..#.. .#.#. #...# ..... ..... ..... .....",
    "_": "..... ..... ..... ..... ..... ..... #####",
}
FONT_COLOUR = (255, 72, 72)     # nearest palette entries are used
SHADOW_COLOUR = (0, 0, 0)

# Large text to strip of its outline. Menu graphics are all M_* except the
# pictures among them; intermission graphics are the WI* labels and digits,
# not the maps, animations or player graphics.
OUTLINED = re.compile(
    r"^(STTNUM\d|STTPRCNT|STTMINUS|WINUM\d|WIPCNT|WIMINUS|WICOLON|WIOST[KIS]|"
    r"WISCRT2|WITIME|WIPAR|WISUCKS|WIF|WIENTER|WIKILRS|WIVCTMS|WIFRGS|"
    r"WIMSTT|WIMSTAR|WILV\d\d|M_\w+)$")
NOT_TEXT = {"M_DOOM", "M_SKULL1", "M_SKULL2", "M_THERML", "M_THERMM", "M_THERMR",
            "M_THERMO", "M_LSLEFT", "M_LSCNTR", "M_LSRGHT", "M_CELL1", "M_CELL2"}
OUTLINE_FRACTION = 0.75         # edge pixels darker than this x the brightest go


def decode_patch(data):
    """Return (left, top, rows) for a patch; rows[y][x] is an index or None."""
    width, height, left, top = struct.unpack_from("<hhhh", data, 0)
    rows = [[None] * width for _ in range(height)]
    for x in range(width):
        offset = struct.unpack_from("<I", data, 8 + 4 * x)[0]
        while data[offset] != 0xFF:
            start, length = data[offset], data[offset + 1]
            for i in range(length):
                if start + i < height:
                    rows[start + i][x] = data[offset + 3 + i]
            offset += length + 4
    return left, top, rows


def encode_patch(left, top, rows):
    """Encode rows (as from decode_patch) as a patch."""
    height = len(rows)
    width = len(rows[0]) if rows else 0
    columns = []
    for x in range(width):
        column = bytearray()
        y = 0
        while y < height:
            if rows[y][x] is None:
                y += 1
                continue
            run = y
            while run < height and rows[run][x] is not None and run - y < 128:
                run += 1
            column += bytes((y, run - y, 0)) + bytes(rows[i][x] for i in range(y, run)) + b"\0"
            y = run
        columns.append(bytes(column) + b"\xff")
    header = struct.pack("<hhhh", width, height, left, top)
    offset = len(header) + 4 * width
    table = bytearray()
    for column in columns:
        table += struct.pack("<I", offset)
        offset += len(column)
    return header + bytes(table) + b"".join(columns)


def luminance(palette, index):
    r, g, b = palette[3 * index:3 * index + 3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def nearest(palette, rgb):
    return min(range(256), key=lambda i: sum((palette[3 * i + c] - rgb[c]) ** 2 for c in range(3)))


def strip_outline(rows, palette, fraction=OUTLINE_FRACTION):
    """Drop edge pixels that are much darker than the glyph's brightest."""
    lit = [luminance(palette, v) for row in rows for v in row if v is not None]
    if not lit:
        return rows
    limit = fraction * max(lit)
    height, width = len(rows), len(rows[0])

    def edge(y, x):
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if not (0 <= ny < height and 0 <= nx < width) or rows[ny][nx] is None:
                return True
        return False

    return [[None if v is not None and edge(y, x) and luminance(palette, v) < limit else v
             for x, v in enumerate(row)] for y, row in enumerate(rows)]


def font_patch(glyph, colour, shadow):
    """A patch for one FONT glyph, shadowed one pixel down and right."""
    lines = glyph.split()
    width, height = len(lines[0]) + 1, len(lines) + 1
    rows = [[None] * width for _ in range(height)]
    for y, line in enumerate(lines):
        for x, c in enumerate(line):
            if c == "#":
                rows[y + 1][x + 1] = shadow
    for y, line in enumerate(lines):
        for x, c in enumerate(line):
            if c == "#":
                rows[y][x] = colour
    return encode_patch(0, 0, rows)


def restyle(lumps):
    """Return lumps with the font replaced and large text outlines removed."""
    palette = dict(lumps)["PLAYPAL"][:768]
    colour = nearest(palette, FONT_COLOUR)
    shadow = nearest(palette, SHADOW_COLOUR)
    font = {"STCFN%03d" % ord(ch): font_patch(glyph, colour, shadow) for ch, glyph in FONT.items()}
    out = []
    for name, data in lumps:
        if name in font:
            data = font[name]
        elif data and OUTLINED.match(name) and name not in NOT_TEXT:
            left, top, rows = decode_patch(data)
            data = encode_patch(left, top, strip_outline(rows, palette))
        out.append((name, data))
    return out
