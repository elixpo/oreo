"""Commits — GitHub contribution graph (the green matrix from your profile).

Cached on entry. Press A to force-refresh — otherwise we keep the in-memory
result so re-opening the app is instant. Layout:

  ┌────── header ──────┐
  │ COMMITS            │
  ├────────────────────┤
  │   @Circuit-Overtime    ← centred, scale=2 pink
  │   137 active days · 9-day streak
  │                    │
  │   ░░▓▓██▓▓░░░▓▓    ← 52×7 contribution grid
  │   ░▓██▓▓░░▓▓████   │
  │   ...              │
  │                    │
  │ less ▒▒▓▓██ more  [LIVE]
  └────────────────────┘

Data: `https://github.com/users/<user>/contributions` SVG endpoint — one
HTTP fetch, no token. We parse `data-level="N"` to drive bucket colours.

Controls:
  A      refresh
  HOME   apps drawer
"""

import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

WEEKS    = 52
DAYS     = 7
CELL_PX  = 5
GAP_PX   = 1

# Five GitHub-style buckets, light → dark
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
    """Return flat list of ints 0..4 in chronological order, or None."""
    try:
        import urequests
        url = "https://github.com/users/%s/contributions" % user
        r = urequests.get(url, headers={"User-Agent": "ElixpoBadge"})
        body = r.text
        r.close()
        out = []
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
                out.append(int(body[i:j]))
            except ValueError:
                out.append(0)
            i = j
        return out if out else None
    except Exception:
        return None


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


class App(lix.App):
    name         = "Commits"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os = os
        try:
            from secrets import GITHUB_USER
            self._user = GITHUB_USER
        except Exception:
            self._user = "Circuit-Overtime"
        live = _fetch_contributions(self._user)
        self._live   = live is not None
        self._levels = live if live else _demo_grid()
        self._dirty  = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            new = _fetch_contributions(self._user)
            if new:
                self._levels = new
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

        # ── fancy centred username (scale=2 pink) ──────────────────────
        user_str = "@" + self._user[:20]
        uw = len(user_str) * 16
        uy = widgets.HEADER_H + 8
        d.text(user_str, (SW - uw) // 2, uy, theme.PRIMARY, scale=2)

        # underline accent that matches text width
        d.rect((SW - uw) // 2, uy + 20, uw, 2, theme.GOLD, fill=True)

        # ── stats subtitle (active days · longest streak) ──────────────
        active = sum(1 for x in self._levels if x > 0)
        streak = _max_streak(self._levels)
        sub = "%d active days  ~  %d-day streak" % (active, streak)
        sw  = len(sub) * 8
        d.text(sub, (SW - sw) // 2, uy + 28, theme.TEXT_BRIGHT)

        # ── contribution grid (centred) ────────────────────────────────
        grid_w = WEEKS * (CELL_PX + GAP_PX) - GAP_PX
        grid_h = DAYS  * (CELL_PX + GAP_PX) - GAP_PX
        gx0    = (SW - grid_w) // 2
        gy0    = uy + 52

        pad = 6
        d.rect(gx0 - pad, gy0 - pad,
               grid_w + pad * 2, grid_h + pad * 2,
               theme.CARD, fill=True)
        d.rect(gx0 - pad, gy0 - pad,
               grid_w + pad * 2, 2, theme.PRIMARY, fill=True)

        n = len(self._levels)
        for i in range(min(n, WEEKS * DAYS)):
            week = i // DAYS
            day  = i %  DAYS
            cx   = gx0 + week * (CELL_PX + GAP_PX)
            cy   = gy0 + day  * (CELL_PX + GAP_PX)
            d.rect(cx, cy, CELL_PX, CELL_PX,
                   _bucket_color(self._levels[i]), fill=True)

        # ── legend + LIVE pill on a single bottom row ──────────────────
        lg_y = SH - widgets.HINT_H - 14
        # legend on the left
        lg_x = 12
        d.text("less", lg_x, lg_y + (CELL_PX - 8) // 2, theme.MUTED)
        for i in range(5):
            d.rect(lg_x + 36 + i * (CELL_PX + GAP_PX), lg_y,
                   CELL_PX, CELL_PX, _bucket_color(i), fill=True)
        d.text("more", lg_x + 36 + 5 * (CELL_PX + GAP_PX) + 4,
               lg_y + (CELL_PX - 8) // 2, theme.MUTED)

        # LIVE / OFFLINE pill on the right
        pill   = "LIVE" if self._live else "OFFLINE"
        pill_c = theme.GREEN if self._live else theme.MUTED
        pw     = len(pill) * 8 + 12
        d.rect(SW - pw - 10, lg_y - 2, pw, 12, pill_c, fill=True)
        d.text(pill, SW - pw - 4, lg_y, api.WHITE)

        self._dirty = False
