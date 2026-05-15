"""Reader — view text / markdown files landed in documents/.

Two screens:
  picker  list of files (.md / .txt), UP/DOWN selects, A opens, HOME exits
  view    renders the file, UP/DOWN scrolls a line at a time, B returns

Markdown features:
  # / ## / ###   headings (scaled, accent colour)
  **bold**       primary-coloured run
  *italic*       muted-coloured run
  `code`         teal run with a subtle bg rect
  - / *          bullet, two-space indent
  1.             numbered list (renders with the literal number)
  ```            fenced code block (whole block rendered teal on cream)
  ---            horizontal rule
  blank          paragraph break

No nested constructs, no link rendering — small enough to ship to flash,
big enough to read README-style notes someone sideloaded over BT.
"""

import os
import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

DOCS_DIR = "documents"

PAD_X      = 10
LINE_GAP   = 2
BODY_LINE_H = 10        # 8 px glyph + 2 px gap

# Block styles — heading scales bump the line height.
_HEADING_H = {1: 24, 2: 20, 3: 16}
_HEADING_SCALE = {1: 2, 2: 2, 3: 1}


# ── picker ──────────────────────────────────────────────────────────────

def _list_docs():
    """Return sorted (basename, full_path) for every .md/.txt under
    documents/. Returns [] if the dir doesn't exist yet."""
    out = []
    try:
        for name in os.listdir(DOCS_DIR):
            low = name.lower()
            if low.endswith(".md") or low.endswith(".txt"):
                out.append((name, DOCS_DIR + "/" + name))
    except OSError:
        return []
    out.sort()
    return out


# ── markdown lexer ──────────────────────────────────────────────────────

def _read_lines(path):
    try:
        with open(path) as f:
            return f.read().splitlines()
    except OSError:
        return []


def _classify_block(line, in_code):
    """Single-line block classifier. Returns (kind, payload).

      heading_N  payload = stripped text
      code       payload = raw line (inside a fenced block)
      code_fence payload = None  (the ``` line itself — not rendered)
      bullet     payload = (depth, text)
      hr         payload = None
      blank      payload = None
      para       payload = line
    """
    if line.strip().startswith("```"):
        return ("code_fence", None)
    if in_code:
        return ("code", line)
    stripped = line.strip()
    if stripped == "":
        return ("blank", None)
    if stripped in ("---", "***", "___"):
        return ("hr", None)
    if stripped.startswith("### "):
        return ("heading_3", stripped[4:])
    if stripped.startswith("## "):
        return ("heading_2", stripped[3:])
    if stripped.startswith("# "):
        return ("heading_1", stripped[2:])
    if stripped[:2] in ("- ", "* "):
        return ("bullet", (0, stripped[2:]))
    # crude numbered-list: "<n>. " prefix
    dot = stripped.find(". ")
    if 1 <= dot <= 3 and stripped[:dot].isdigit():
        return ("bullet", (0, stripped[dot + 2:]))
    return ("para", line)


# ── inline parser ───────────────────────────────────────────────────────
# Splits a single line into a list of (text, style) spans.
# style ∈ {"plain","bold","italic","code"}

def _inline_spans(line):
    spans = []
    cur = []
    style = "plain"

    def flush(target_style):
        if cur:
            spans.append(("".join(cur), target_style))
            del cur[:]

    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        # bold (**…**) — must come before italic since '*' is a prefix
        if c == "*" and i + 1 < n and line[i + 1] == "*":
            if style == "bold":
                flush("bold")
                style = "plain"
            else:
                flush(style)
                style = "bold"
            i += 2
            continue
        if c == "*":
            if style == "italic":
                flush("italic")
                style = "plain"
            else:
                flush(style)
                style = "italic"
            i += 1
            continue
        if c == "`":
            if style == "code":
                flush("code")
                style = "plain"
            else:
                flush(style)
                style = "code"
            i += 1
            continue
        cur.append(c)
        i += 1
    flush(style)
    return spans


# ── pre-layout: lex once at open-time, drive scrolling off line offsets ─

def _layout(lines):
    """Walk lines once, produce a list of block descriptors with
    per-block (kind, payload, height_px). Heights are summed at render
    time to figure scroll bounds."""
    out = []
    in_code = False
    for raw in lines:
        kind, payload = _classify_block(raw, in_code)
        if kind == "code_fence":
            in_code = not in_code
            continue
        if kind in ("heading_1", "heading_2", "heading_3"):
            lvl = int(kind[-1])
            out.append((kind, payload, _HEADING_H[lvl]))
        elif kind == "code":
            out.append((kind, payload, BODY_LINE_H + 2))
        elif kind == "bullet":
            out.append((kind, payload, BODY_LINE_H + 2))
        elif kind == "hr":
            out.append((kind, payload, 12))
        elif kind == "blank":
            out.append((kind, payload, 6))
        else:
            out.append((kind, payload, BODY_LINE_H + 2))
    return out


# ── span renderer ───────────────────────────────────────────────────────

_STYLE_COLOR = {
    "plain":  None,
    "bold":   None,
    "italic": None,
    "code":   None,
}

def _style_color(style):
    # Resolved lazily so theme is loaded once.
    if _STYLE_COLOR["plain"] is None:
        _STYLE_COLOR["plain"]  = theme.TEXT_BRIGHT
        _STYLE_COLOR["bold"]   = theme.PRIMARY
        _STYLE_COLOR["italic"] = theme.TEXT_DIM
        _STYLE_COLOR["code"]   = theme.TEAL
    return _STYLE_COLOR[style]


def _draw_spans(d, spans, x, y, scale=1, code_bg=False):
    """Draw a list of (text, style) spans left-to-right. Wraps simply by
    truncating with an ellipsis when the line overflows the play area."""
    cw = 8 * scale
    max_x = SW - PAD_X
    cx = x
    for text, style in spans:
        if not text:
            continue
        color = _style_color(style)
        for ch in text:
            if cx + cw > max_x:
                d.text("…", cx, y, theme.MUTED, scale=scale)
                return
            if style == "code" and code_bg:
                d.rect(cx, y - 1, cw, 8 * scale + 2, theme.CARD, fill=True)
            d.text(ch, cx, y, color, scale=scale)
            cx += cw


# ── app ────────────────────────────────────────────────────────────────

class App(oreoOS.App):
    name = "Reader"

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os     = os_
        self._dirty  = True
        self._mode   = "picker"
        self._files  = _list_docs()
        self._sel    = 0
        # view-mode state
        self._title  = ""
        self._blocks = []
        self._scroll = 0          # in pixels
        self._total_h = 0

    def update(self, dt):
        pass

    def on_button_press(self, btn):
        if self._mode == "picker":
            return self._on_btn_picker(btn)
        return self._on_btn_view(btn)

    # ── picker input ────────────────────────────────────────────────────
    def _on_btn_picker(self, btn):
        n = len(self._files)
        if btn == api.BTN_HOME:
            self._os.quit()
            return
        if btn == api.BTN_A:
            if n:
                self._open(self._files[self._sel])
            return
        if not n:
            return
        if btn == api.BTN_UP:
            self._sel = (self._sel - 1) % n
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + 1) % n
        else:
            return
        self._dirty = True

    # ── view input ──────────────────────────────────────────────────────
    def _on_btn_view(self, btn):
        if btn == api.BTN_B or btn == api.BTN_HOME:
            self._mode  = "picker"
            self._files = _list_docs()
            self._dirty = True
            return
        if btn == api.BTN_UP:
            self._scroll = max(0, self._scroll - BODY_LINE_H * 2)
        elif btn == api.BTN_DOWN:
            play_h = SH - widgets.HEADER_H - widgets.HINT_H
            max_scroll = max(0, self._total_h - play_h + 8)
            self._scroll = min(max_scroll, self._scroll + BODY_LINE_H * 2)
        else:
            return
        self._dirty = True

    # ── open a file ─────────────────────────────────────────────────────
    def _open(self, entry):
        name, path = entry
        self._title  = name
        self._blocks = _layout(_read_lines(path))
        self._total_h = sum(b[2] for b in self._blocks)
        self._scroll  = 0
        self._mode    = "view"
        self._dirty   = True

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        if self._mode == "picker":
            self._draw_picker(d)
        else:
            self._draw_view(d)

    def _draw_picker(self, d):
        widgets.draw_header(d, "READER")
        widgets.draw_hint(d, "A=open  HOME=back")

        if not self._files:
            msg = "no documents yet"
            d.text(msg, (SW - len(msg) * 8) // 2,
                   SH // 2 - 8, theme.MUTED, scale=1)
            d.text("send .md / .txt over BT",
                   (SW - 23 * 8) // 2, SH // 2 + 6, theme.MUTED2, scale=1)
            return

        row_h = 20
        top_y = widgets.HEADER_H + 6
        for i, (name, _) in enumerate(self._files):
            y = top_y + i * row_h
            if y + row_h > SH - widgets.HINT_H:
                break
            sel = (i == self._sel)
            if sel:
                d.rect(6, y, SW - 12, row_h - 2,
                       theme.DOCK_SEL, fill=True)
            color = theme.TEXT_BRIGHT if sel else theme.TEXT_DIM
            d.text(name[:34], 12, y + 6, color, scale=1)

    def _draw_view(self, d):
        widgets.draw_header(d, self._title[:18])
        widgets.draw_hint(d, "UP/DOWN=scroll  B=back")

        play_top = widgets.HEADER_H + 4
        play_h   = SH - widgets.HEADER_H - widgets.HINT_H - 4
        # Vertical clip: walk blocks, skip those above scroll, draw those
        # inside the viewport, stop once we've gone past the bottom.
        y_cursor = -self._scroll
        for kind, payload, h in self._blocks:
            top = play_top + y_cursor
            bot = top + h
            if bot < play_top:
                y_cursor += h
                continue
            if top > play_top + play_h:
                break

            if kind == "blank":
                pass
            elif kind == "hr":
                d.rect(PAD_X, top + 5, SW - 2 * PAD_X, 1,
                       theme.MUTED, fill=True)
            elif kind in ("heading_1", "heading_2", "heading_3"):
                lvl = int(kind[-1])
                scale = _HEADING_SCALE[lvl]
                color = theme.PRIMARY if lvl == 1 else theme.TEXT_BRIGHT
                d.text(payload[: (SW - 2 * PAD_X) // (8 * scale)],
                       PAD_X, top + 2, color, scale=scale)
            elif kind == "code":
                # Whole-line code in a fenced block.
                d.rect(PAD_X - 2, top, SW - 2 * PAD_X + 4, h,
                       theme.CARD, fill=True)
                d.text(payload[: (SW - 2 * PAD_X) // 8],
                       PAD_X, top + 1, theme.TEAL, scale=1)
            elif kind == "bullet":
                depth, text = payload
                bx = PAD_X + depth * 8
                d.text("\xb7", bx, top + 1, theme.PRIMARY, scale=1)
                _draw_spans(d, _inline_spans(text), bx + 10, top + 1,
                            scale=1, code_bg=True)
            else:    # para
                _draw_spans(d, _inline_spans(payload), PAD_X, top + 1,
                            scale=1, code_bg=True)

            y_cursor += h

        # Right-edge scroll thumb when content overflows.
        if self._total_h > play_h:
            track_x = SW - 3
            track_y = play_top
            track_h = play_h
            thumb_h = max(12, int(track_h * play_h / self._total_h))
            max_scroll = max(1, self._total_h - play_h)
            thumb_y = track_y + (track_h - thumb_h) * self._scroll // max_scroll
            d.rect(track_x, thumb_y, 2, thumb_h, theme.PRIMARY, fill=True)
