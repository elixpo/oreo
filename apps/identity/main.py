"""Identity — minimalist conference badge card.

Shows just the things a stranger needs to read across the room:

  ┌──────── header (pink) ──────────┐
  │            IDENTITY             │
  ├─────────────────────────────────┤
  │                                 │
  │           ╭───────╮             │
  │           │ AVTR  │  ← circular │
  │           ╰───────╯             │
  │       Ayushman Bhattacharya     │  ← display name, scale=2 pink
  │       ─────────────────         │  ← gold underline
  │         @Circuit-Overtime       │  ← teal handle
  │                                 │
  │       Founder, Elixpo           │  ← designation, gold
  └─────────────────────────────────┘

All three text fields come from config.py: DISPLAY_NAME, GITHUB_USER,
DESIGNATION. The avatar is baked at deploy time by tools/fetch_avatar.py
(re-uses apps/badge's source if you copy it across).

Controls:
  HOME   apps drawer
"""

import oreoOS
from oreoOS import api, theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


def _filled_circle(d, cx, cy, r, color):
    for dy in range(-r, r + 1):
        dx = int((r * r - dy * dy) ** 0.5)
        d.rect(cx - dx, cy + dy, dx * 2 + 1, 1, color, fill=True)


def _wrap(text, max_chars):
    """Greedy word-wrap so long display names ('Ayushman Bhattacharya') break
    cleanly onto multiple centred lines instead of trailing off the screen."""
    if not text:
        return [""]
    out, cur = [], ""
    for w in text.split():
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                out.append(cur)
            while len(w) > max_chars:
                out.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        out.append(cur)
    return out


def _try_avatar():
    try:
        m = __import__("apps.identity.assets.optimized.avatar", None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _load_identity():
    try:
        from secrets import GITHUB_USER, DISPLAY_NAME, DESIGNATION
    except Exception:
        GITHUB_USER, DISPLAY_NAME, DESIGNATION = "octocat", "Octo Cat", ""
    return {
        "name":        DISPLAY_NAME or GITHUB_USER,
        "login":       GITHUB_USER,
        "designation": DESIGNATION or "",
    }


class App(oreoOS.App):
    name         = "Identity"
    SHOW_LOADING = False

    def on_enter(self, os):
        self._os       = os
        self._avatar   = _try_avatar()
        self._identity = _load_identity()
        self._dirty    = True

    def on_button_press(self, btn):
        pass

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "IDENTITY")
        widgets.draw_hint  (d, "HOME=back")

        p = self._identity

        # Full-play-area card with the same pink top accent as the rest of
        # the OS, so the identity reads as part of the badge's visual brand.
        cx, cy = 12, widgets.HEADER_H + 6
        cw     = SW - 24
        ch     = SH - widgets.HEADER_H - widgets.HINT_H - 12
        d.rect(cx + 2, cy + 2, cw, ch, theme.MUTED2, fill=True)
        d.rect(cx,     cy,     cw, ch, theme.CARD,   fill=True)
        d.rect(cx,     cy,     cw, 3,  theme.PRIMARY, fill=True)

        # ── circular avatar at top-centre, framed in pink ───────────────
        av_sz = self._avatar[1] if self._avatar else 96
        av_cx = SW // 2
        av_cy = cy + 14 + av_sz // 2
        _filled_circle(d, av_cx, av_cy, av_sz // 2 + 4, theme.PRIMARY)
        if self._avatar:
            data, aw, ah = self._avatar
            d.blit(data, av_cx - aw // 2, av_cy - ah // 2, aw, ah)
        else:
            _filled_circle(d, av_cx, av_cy, av_sz // 2, theme.CARD)
            letter = (p["login"] or "?")[:1].upper()
            d.text(letter, av_cx - 16, av_cy - 16, theme.PRIMARY, scale=4)

        # ── display name — word-wrap to fit, centred per line, pink scale=2.
        #   max_chars derived from card width (scale=2 → 16 px per glyph).
        max_chars = max(6, (cw - 16) // 16)
        name_lines = _wrap(p["name"], max_chars)[:2]   # cap at 2 lines
        name_top   = av_cy + av_sz // 2 + 14
        for i, line in enumerate(name_lines):
            lw = len(line) * 16
            d.text(line, (SW - lw) // 2, name_top + i * 22,
                   theme.PRIMARY, scale=2)

        # Gold underline beneath the LAST name line (visual anchor).
        last_lw = len(name_lines[-1]) * 16 if name_lines else 0
        d.rect((SW - last_lw) // 2, name_top + (len(name_lines) - 1) * 22 + 20,
               last_lw, 2, theme.GOLD, fill=True)

        # ── designation, gold, bigger so it reads from a distance ──────
        desig = p["designation"][:28]
        if desig:
            dw = len(desig) * 16
            dy = name_top + len(name_lines) * 22 + 10
            # if it'd run off the card, fall back to scale=1
            if dw > cw - 16:
                dw = len(desig) * 8
                d.text(desig, (SW - dw) // 2, dy + 4, theme.GOLD)
            else:
                d.text(desig, (SW - dw) // 2, dy, theme.GOLD, scale=2)

        self._dirty = False
