"""Commits — GitHub contribution graph + stat strip.

Cached on entry; press A to force-refresh. Layout fills the play area as
one tall card so there's no dead cream space below the grid:

  ┌── card ───────────────────────────────────────────┐
  │           @Circuit-Overtime                       │
  │           ──────────────────                      │
  │       352 active days  ~  45-day streak           │
  │                                                   │
  │   ░░▓▓██▓▓░░░▓▓    ← 52×7 contribution grid      │
  │   ...                                             │
  │                                                   │
  │   current  3       busiest  18      total  1.2k   │
  │                                                   │
  │ less ▒▒▓▓██ more                          [LIVE]  │
  └───────────────────────────────────────────────────┘

Data: `https://github.com/users/<user>/contributions` — one HTTP fetch,
no token. We parse `data-level="N"` for bucket colour AND the surrounding
`<tool-tip>... N contributions ...</tool-tip>` text for the real count.

Controls:
  A      refresh
  HOME   apps drawer
"""

import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

WEEKS    = 52
DAYS     = 7
CELL_PX  = 5
GAP_PX   = 1

BUCKETS = [
    (235, 237, 240),
    (155, 233, 168),
    ( 64, 196,  99),
    ( 48, 161,  78),
    ( 33, 110,  57),
]


def _bucket_color(level):
    r, g, b = BUCKETS[max(0, min(4, level))]
    return api.rgb(r, g, b)


def _fetch_contributions(user):
    """Return (levels[], counts[]) or (None, None) on failure."""
    try:
        import urequests
        url = "https://github.com/users/%s/contributions" % user
        r = urequests.get(url, headers={"User-Agent": "OreoBadge"})
        body = r.text
        r.close()
        levels = []
        i = 0
        while True:
            i = body.find('data-level="', i)
            if i < 0:
                break
            i += 12
            j = body.find('"', i)
            if j < 0:
                break
            try:
                levels.append(int(body[i:j]))
            except ValueError:
                levels.append(0)
            i = j
        if not levels:
            return None, None

        # Best-effort tooltip parsing for true per-day counts.
        counts = []
        k = 0
        for _ in range(len(levels)):
            j = body.find("contribution", k)
            if j < 0:
                break
            seg = body[max(0, j - 12):j]
            digits = ""
            for ch in reversed(seg):
                if ch.isdigit():
                    digits = ch + digits
                elif digits:
                    break
            counts.append(int(digits) if digits else 0)
            k = j + 12
        while len(counts) < len(levels):
            counts.append(0)
        return levels, counts
    except Exception:
        return None, None


def _demo_grid():
    seed = 0xC0FFEE
    out  = []
    for i in range(WEEKS * DAYS):
        seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
        wday = i % DAYS
        base = 2 if (1 <= wday <= 5) else 0
        out.append(min(4, max(0, base + ((seed >> 8) & 3) - 1)))
    return out


def _max_streak(levels):
    best = cur = 0
    for v in levels:
        if v > 0:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


def _current_streak(levels):
    cur = 0
    for v in reversed(levels):
        if v > 0:
            cur += 1
        else:
            break
    return cur


def _busiest_week(levels):
    best = 0
    for w in range(0, len(levels) - DAYS + 1, DAYS):
        s = sum(levels[w:w + DAYS])
        if s > best:
            best = s
    return best


def _fmt_count(n):
    if n >= 1000:
        return "%.1fk" % (n / 1000.0)
    return str(n)


class App(oreoOS.App):
    name         = "Commits"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os = os
        try:
            from secrets import GITHUB_USER
            self._user = GITHUB_USER
        except Exception:
            self._user = "Circuit-Overtime"
        lv, ct = _fetch_contributions(self._user)
        self._live   = lv is not None
        self._levels = lv if lv else _demo_grid()
        self._counts = ct if ct else [0] * len(self._levels)
        self._dirty  = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            lv, ct = _fetch_contributions(self._user)
            if lv:
                self._levels = lv
                self._counts = ct or [0] * len(lv)
                self._live   = True
            else:
                self._live = False
            self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "COMMITS")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        # Full-height card filling the play area.
        card_x = 10
        card_y = widgets.HEADER_H + 4
        card_w = SW - 20
        card_h = SH - widgets.HEADER_H - widgets.HINT_H - 8
        d.rect(card_x + 2, card_y + 2, card_w, card_h, theme.MUTED2, fill=True)
        d.rect(card_x,     card_y,     card_w, card_h, theme.CARD,   fill=True)
        d.rect(card_x,     card_y,     card_w, 3,      theme.PRIMARY, fill=True)

        # Username (scale=2 pink) + gold underline.
        user_str = "@" + self._user[:20]
        uw = len(user_str) * 16
        uy = card_y + 8
        d.text(user_str, (SW - uw) // 2, uy, theme.PRIMARY, scale=2)
        d.rect((SW - uw) // 2, uy + 20, uw, 2, theme.GOLD, fill=True)

        # Headline subtitle (active days · longest streak).
        active = sum(1 for x in self._levels if x > 0)
        streak = _max_streak(self._levels)
        sub = "%d active days  ~  %d-day streak" % (active, streak)
        sw  = len(sub) * 8
        d.text(sub, (SW - sw) // 2, uy + 28, theme.TEXT_BRIGHT)

        # Grid — centred horizontally and vertically between subtitle and
        # stat strip so it fills the cream void.
        grid_w = WEEKS * (CELL_PX + GAP_PX) - GAP_PX
        grid_h = DAYS  * (CELL_PX + GAP_PX) - GAP_PX
        gx0    = (SW - grid_w) // 2

        sub_bot   = uy + 40
        strip_top = card_y + card_h - 60     # reserve for stat strip + legend
        gy0       = sub_bot + max(0, (strip_top - sub_bot - grid_h) // 2)

        gp = 4
        d.rect(gx0 - gp, gy0 - gp,
               grid_w + gp * 2, grid_h + gp * 2,
               theme.DOCK_SEL, fill=True)
        for i in range(min(len(self._levels), WEEKS * DAYS)):
            week = i // DAYS
            day  = i %  DAYS
            cx   = gx0 + week * (CELL_PX + GAP_PX)
            cy   = gy0 + day  * (CELL_PX + GAP_PX)
            d.rect(cx, cy, CELL_PX, CELL_PX,
                   _bucket_color(self._levels[i]), fill=True)

        # Stat strip — current streak / busiest week / total commits.
        strip_y = strip_top + 4
        total   = sum(self._counts) if any(self._counts) else active
        cur_str = _current_streak(self._levels)
        busy    = _busiest_week(self._levels)
        cols = [
            ("current", "%dd" % cur_str),
            ("busiest", "%d"  % busy),
            ("total",   _fmt_count(total)),
        ]
        col_w = card_w // len(cols)
        for i, (lbl, val) in enumerate(cols):
            mx = card_x + col_w * i + col_w // 2
            d.text(val, mx - len(val) * 8, strip_y, theme.PRIMARY, scale=2)
            d.text(lbl, mx - len(lbl) * 4, strip_y + 22, theme.MUTED)

        # Legend (bottom-left) + LIVE pill (bottom-right), inside the card.
        lg_y = card_y + card_h - 14
        lg_x = card_x + 10
        d.text("less", lg_x, lg_y + (CELL_PX - 8) // 2, theme.MUTED)
        for i in range(5):
            d.rect(lg_x + 36 + i * (CELL_PX + GAP_PX), lg_y,
                   CELL_PX, CELL_PX, _bucket_color(i), fill=True)
        d.text("more", lg_x + 36 + 5 * (CELL_PX + GAP_PX) + 4,
               lg_y + (CELL_PX - 8) // 2, theme.MUTED)

        pill   = "LIVE" if self._live else "OFFLINE"
        pill_c = theme.GREEN if self._live else theme.MUTED
        pw     = len(pill) * 8 + 12
        d.rect(card_x + card_w - pw - 10, lg_y - 2, pw, 12, pill_c, fill=True)
        d.text(pill, card_x + card_w - pw - 4, lg_y, api.WHITE)

        self._dirty = False
