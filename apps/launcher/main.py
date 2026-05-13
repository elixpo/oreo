"""Apps — first-class app launcher (modern look).

4-column grid of 64-px icons with smooth vertical scrolling. Multi-line app
names below each icon with margin from a small rounded selection rectangle.
Selected icon plays a Y-axis rotation animation (horizontal compression →
edge-on → expand back) for tactile feedback.

Controls:
  LEFT/RIGHT  linear traversal across all apps (wraps)
  UP/DOWN     jump by one row, auto-scrolls grid to keep cursor in view
  A           launch the selected app
  HOME        back to home screen
"""

import math
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

# ── grid geometry ─────────────────────────────────────────────────────────────
COLS         = 4
VISIBLE_ROWS = 2

ICON_SZ      = 64        # display size — icons are pre-upscaled 32→64 at on_enter
SEL_PAD      = 2         # smaller hugs the icon tightly
LABEL_GAP    = 6         # margin between selection rect bottom and label top
LABEL_LINE_H = 9
MAX_LBL_LNS  = 2
MAX_LBL_CHARS = 9        # chars per label line (8-px font @ ~72 px cell width)

PAD_X        = 14
PAD_TOP      = widgets.HEADER_H + 4
PAD_BOT      = widgets.HINT_H   + 4

CELL_W       = (SW - 2 * PAD_X) // COLS
CELL_H       = (SH - PAD_TOP - PAD_BOT) // VISIBLE_ROWS

# ── animation ────────────────────────────────────────────────────────────────
ANIM_DUR     = 0.28
SCROLL_TWEEN = 0.32      # fraction of remaining distance covered per frame

CORNER_R     = 4

ELLIPSIS     = "..."


# ─────────────────────────────────────────────────────────────────────────────
def _wrap_label(text, max_chars=MAX_LBL_CHARS):
    """Wrap text into ≤MAX_LBL_LNS lines. Append '...' if it doesn't fit."""
    if not text:
        return [""]
    words = text.split()
    lines = []
    cur   = ""

    def _push(s):
        lines.append(s)

    rest_words = list(words)
    while rest_words:
        w = rest_words[0]
        candidate = (cur + " " + w).strip()
        if len(candidate) <= max_chars:
            cur = candidate
            rest_words.pop(0)
            continue
        # The candidate would overflow this line
        if cur:
            _push(cur)
            cur = ""
            if len(lines) == MAX_LBL_LNS:
                # We've already filled all lines → indicate truncation
                lines[-1] = lines[-1][:max_chars - len(ELLIPSIS)] + ELLIPSIS
                return lines
            continue
        # cur is empty and the word itself is too long → hard-truncate it
        if len(w) > max_chars:
            if len(lines) == MAX_LBL_LNS - 1:
                # last available line: truncate + ellipsis
                _push(w[:max_chars - len(ELLIPSIS)] + ELLIPSIS)
                return lines
            else:
                _push(w[:max_chars])
                rest_words[0] = w[max_chars:]
                continue
        cur = w
        rest_words.pop(0)

    if cur:
        _push(cur)
    # Pad to max lines if needed (returns up to MAX_LBL_LNS)
    return lines[:MAX_LBL_LNS] or [""]


def _upscale_xy(data, w, h, sx, sy):
    """Nearest-neighbour upscale → new bytearray (w*sx, h*sy). RGB565 BE."""
    sw      = w * sx
    out     = bytearray(sw * h * sy * 2)
    row_buf = bytearray(sw * 2)
    for src_row in range(h):
        for col in range(w):
            base_src = (src_row * w + col) * 2
            b1 = data[base_src]
            b0 = data[base_src + 1]
            base = col * sx * 2
            for dx in range(sx):
                row_buf[base + dx * 2]     = b1
                row_buf[base + dx * 2 + 1] = b0
        row_start = src_row * sy * sw * 2
        for dy in range(sy):
            s = row_start + dy * sw * 2
            out[s: s + sw * 2] = row_buf
    return out, sw, h * sy


def _compress_x(data, sw, sh, dst_w):
    """Horizontally compress a (sw,sh) sprite to width dst_w (1..sw).

    Used for the Y-axis rotation animation on the selected icon. Each output
    column is a nearest-neighbour sample of one source column. Returns
    (bytearray, dst_w, sh).
    """
    if dst_w >= sw:
        return (data, sw, sh)
    if dst_w <= 0:
        return (None, 0, sh)
    src_stride = sw * 2
    out_stride = dst_w * 2
    out = bytearray(out_stride * sh)
    # Pre-compute the column mapping so the inner loop is fast.
    col_map = [c * sw // dst_w for c in range(dst_w)]
    for ry in range(sh):
        src_base = ry * src_stride
        out_base = ry * out_stride
        for ox in range(dst_w):
            so = src_base + col_map[ox] * 2
            do = out_base + ox * 2
            out[do]     = data[so]
            out[do + 1] = data[so + 1]
    return (out, dst_w, sh)


def _rounded_outline(d, x, y, w, h, color, r=CORNER_R):
    """Outline-only rounded rect with a small chamfered corner."""
    if w < r * 2 or h < r * 2:
        d.rect(x, y, w, 1, color, fill=True)
        d.rect(x, y + h - 1, w, 1, color, fill=True)
        d.rect(x, y, 1, h, color, fill=True)
        d.rect(x + w - 1, y, 1, h, color, fill=True)
        return
    d.rect(x + r,         y,             w - 2 * r, 1,         color, fill=True)
    d.rect(x + r,         y + h - 1,     w - 2 * r, 1,         color, fill=True)
    d.rect(x,             y + r,         1,         h - 2 * r, color, fill=True)
    d.rect(x + w - 1,     y + r,         1,         h - 2 * r, color, fill=True)
    if r >= 3:
        stair = [(1, 0), (0, 1), (2, 0), (0, 2), (1, 1)]
        if r >= 4:
            stair += [(3, 0), (0, 3), (2, 1), (1, 2)]
        for dx, dy in stair:
            d.rect(x + dx,         y + dy,         1, 1, color, fill=True)
            d.rect(x + w - 1 - dx, y + dy,         1, 1, color, fill=True)
            d.rect(x + dx,         y + h - 1 - dy, 1, 1, color, fill=True)
            d.rect(x + w - 1 - dx, y + h - 1 - dy, 1, 1, color, fill=True)


# ─────────────────────────────────────────────────────────────────────────────
class App(lix.App):
    name         = "Apps"
    SHOW_LOADING = True      # ~80 ms upscaling 12 icons from 32→64 at on_enter

    def on_enter(self, os):
        self._os = os
        from lix_os.launcher import list_apps
        self._apps = [a for a in list_apps() if a["dir"] != "launcher"]

        # Pre-upscale every icon 32×32 → 64×64 ONCE; cache as bytearray for
        # fast per-frame blits AND as the source of the rotation animation.
        from lix_os import icons as _icons
        self._icons = {}
        for a in self._apps:
            res = _icons.load(a["dir"], a.get("icon"))
            if not res:
                continue
            data, iw, ih = res
            if iw == ICON_SZ and ih == ICON_SZ:
                self._icons[a["dir"]] = (bytearray(data), iw, ih)
            else:
                sx = max(1, ICON_SZ // iw)
                sy = max(1, ICON_SZ // ih)
                up, uw, uh = _upscale_xy(bytearray(data), iw, ih, sx, sy)
                self._icons[a["dir"]] = (up, uw, uh)

        # Pre-wrap labels (no per-frame allocation).
        self._labels = [_wrap_label(a["name"]) for a in self._apps]

        self._sel        = 0
        self._top_row    = 0          # which grid row is at top of viewport
        self._scroll_y   = 0.0        # tweened pixel offset (float for smooth tween)
        self._anim_t     = ANIM_DUR
        self._dirty      = True

    # ── input ────────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        n = len(self._apps)
        if not n: return
        prev = self._sel
        if btn == api.BTN_LEFT:
            self._sel = (self._sel - 1) % n
        elif btn == api.BTN_RIGHT:
            self._sel = (self._sel + 1) % n
        elif btn == api.BTN_UP:
            self._sel = (self._sel - COLS) % n
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + COLS) % n
        elif btn == api.BTN_A:
            self._os.launch(self._apps[self._sel]["dir"])
            return
        else:
            return

        # Auto-scroll: keep cursor inside the visible window.
        sel_row     = self._sel // COLS
        rows_total  = (n + COLS - 1) // COLS
        if sel_row < self._top_row:
            self._top_row = sel_row
        elif sel_row >= self._top_row + VISIBLE_ROWS:
            self._top_row = sel_row - VISIBLE_ROWS + 1
        if self._top_row > rows_total - VISIBLE_ROWS:
            self._top_row = max(0, rows_total - VISIBLE_ROWS)

        if self._sel != prev:
            self._anim_t = 0.0
        self._dirty = True

    def update(self, dt):
        # Tween scroll
        target = self._top_row * CELL_H
        if abs(self._scroll_y - target) > 0.5:
            self._scroll_y += (target - self._scroll_y) * SCROLL_TWEEN
            self._dirty = True
        else:
            self._scroll_y = float(target)

        if self._anim_t < ANIM_DUR:
            self._anim_t = min(ANIM_DUR, self._anim_t + dt)
            self._dirty = True

    # ── render ───────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "APPS")
        widgets.draw_hint  (d, "arrows=nav  A=launch  HOME=back")

        n = len(self._apps)
        if not n:
            d.text("no apps found", (SW - 13 * 16) // 2, SH // 2,
                   theme.MUTED, scale=2)
            self._dirty = False
            return

        rows_total = (n + COLS - 1) // COLS
        scroll_int = int(self._scroll_y)

        # Compute the slice of rows that are at least partially on-screen.
        viewport_top    = PAD_TOP
        viewport_bottom = PAD_TOP + VISIBLE_ROWS * CELL_H + PEEK_H

        for app_idx in range(n):
            row = app_idx // COLS
            col = app_idx %  COLS
            cell_y = PAD_TOP + row * CELL_H - scroll_int
            # cull if entirely off-screen
            if cell_y + CELL_H < viewport_top or cell_y > viewport_bottom:
                continue

            cx = PAD_X + col * CELL_W + CELL_W // 2
            ix = cx - ICON_SZ // 2
            iy = cell_y + 4

            sel = (app_idx == self._sel)

            # ── icon (selected one may be horizontally compressed for the Y-axis flip) ──
            icon = self._icons.get(self._apps[app_idx]["dir"])
            if icon:
                idata, iw, ih = icon
                if sel and self._anim_t < ANIM_DUR:
                    # Y-axis rotation: scale_x goes 0 → 1 over the anim
                    t = self._anim_t / ANIM_DUR
                    scale_x = math.sin(t * math.pi / 2)
                    cur_w = max(2, int(iw * scale_x))
                    if cur_w < iw:
                        cdata, cw, ch = _compress_x(idata, iw, ih, cur_w)
                        if cdata:
                            d.blit(cdata, cx - cw // 2, iy, cw, ch)
                    else:
                        d.blit(idata, ix, iy, iw, ih)
                else:
                    d.blit(idata, ix, iy, iw, ih)
            else:
                # letter placeholder
                d.text(self._apps[app_idx]["name"][0].upper(),
                       cx - 16, iy + (ICON_SZ - 32) // 2,
                       theme.PRIMARY, scale=4)

            # ── multi-line label (centred under the icon) ──
            label_top = iy + ICON_SZ + SEL_PAD + LABEL_GAP
            for li, line in enumerate(self._labels[app_idx]):
                lx = cx - len(line) * 4         # 8-px font ⇒ /2 for centre
                ly = label_top + li * LABEL_LINE_H
                color = theme.PRIMARY if sel else theme.TEXT_BRIGHT
                d.text(line, lx, ly, color)

            # ── selection rectangle (only on selected, rounded + animated) ──
            if sel:
                if self._anim_t < ANIM_DUR:
                    t = self._anim_t / ANIM_DUR
                    rect_scale = math.sin(t * math.pi / 2)
                else:
                    rect_scale = 1.0
                full_w = ICON_SZ + SEL_PAD * 2
                full_h = ICON_SZ + SEL_PAD * 2
                cur_w  = max(4, int(full_w * rect_scale))
                rect_x = cx - cur_w // 2
                rect_y = iy - SEL_PAD
                r = min(CORNER_R, max(1, cur_w // 8))
                _rounded_outline(d, rect_x, rect_y, cur_w, full_h,
                                 theme.SEL_BORDER, r=r)

        # ── viewport mask: hide rows scrolled above the top edge ─────────
        if scroll_int > 0:
            d.rect(0, 0, SW, PAD_TOP, theme.BG, fill=True)
            widgets.draw_header(d, "APPS")   # re-stamp the header on top

        # ── scrollbar on the right ───────────────────────────────────────
        if rows_total > VISIBLE_ROWS:
            track_x = SW - 4
            track_y = PAD_TOP
            track_h = SH - PAD_TOP - PAD_BOT
            d.rect(track_x, track_y, 2, track_h, theme.MUTED2, fill=True)
            thumb_h = max(12, track_h * VISIBLE_ROWS // rows_total)
            thumb_y = track_y + (track_h - thumb_h) * self._top_row \
                                 // max(1, rows_total - VISIBLE_ROWS)
            d.rect(track_x, thumb_y, 2, thumb_h, theme.PRIMARY, fill=True)

        # ── peek line at the bottom: visual cue there's more below ──────
        if self._top_row + VISIBLE_ROWS < rows_total:
            peek_y = SH - widgets.HINT_H - PEEK_H + 1
            for i in range(0, SW, 8):
                d.rect(i, peek_y, 4, 1, theme.PRIMARY, fill=True)

        # keep dirty while scrolling / animating
        if (abs(self._scroll_y - self._top_row * CELL_H) > 0.5 or
            self._anim_t < ANIM_DUR):
            return    # leave _dirty = True
        self._dirty = False
