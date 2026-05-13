"""Commits — GitHub contribution graph (the green matrix from your profile).

Live-fetched from the rest of GitHub's API + a small SVG-grid scraper. When
WiFi isn't up, we render a demo grid so the visual is meaningful during dev.

Layout:
  ┌──────── header ────────┐
  │ COMMITS                │
  ├────────────────────────┤
  │ user contributions     │
  │                        │
  │ ░░▓▓██▓▓░░░▓▓  ← 52 weeks
  │ ░▓██▓▓░░▓▓████   (7 days each)
  │ ...                    │
  │ legend: less ▒ more █  │
  └────────────────────────┘

The contribution data comes from GitHub's `https://github.com/users/<user>/
contributions` SVG endpoint — a single HTTP fetch, no API token required.
We parse out the `data-level="N"` attributes to drive the colour bucket.

Controls:
  A      refresh
  HOME   apps drawer
"""

import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

# Grid: 52 weeks × 7 days, ~4 px cells fit comfortably on a 320-wide screen
WEEKS    = 52
DAYS     = 7
CELL_PX  = 4
GAP_PX   = 1

# Five GitHub-style buckets, light → dark
BUCKETS = [
    (235, 237, 240),    # 0 — no contributions (light grey)
    (155, 233, 168),    # 1 — light green
    ( 64, 196, 99),     # 2
    ( 48, 161, 78),     # 3
    ( 33,  110, 57),    # 4 — dark green
]


def _bucket_color(level):
    r, g, b = BUCKETS[max(0, min(4, level))]
    return api.rgb(r, g, b)


def _fetch_contributions(user):
    """Return a flat list of ints 0..4 in chronological order.
    On any failure → return None."""
    try:
        import urequests
        url = "https://github.com/users/%s/contributions" % user
        r = urequests.get(url, headers={"User-Agent": "ElixpoBadge"})
        body = r.text
        r.close()
        # Each cell is something like:
        #   <td class="ContributionCalendar-day" data-date="2025-..."
        #       data-level="2" ...>
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
        if not out:
            return None
        # GitHub returns up to 53 weeks × 7 days — trim/pad to fit our grid
        return out
    except Exception:
        return None


def _demo_grid():
    """Synthetic-but-plausible contribution levels used when offline."""
    # Deterministic PRNG fold so the grid stays visually consistent
    seed = 0xC0FFEE
    out  = []
    for i in range(WEEKS * DAYS):
        seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
        # Weekend dip, weekday hump
        wday = i % DAYS
        base = 2 if (1 <= wday <= 5) else 0
        out.append(min(4, max(0, base + ((seed >> 8) & 3) - 1)))
    return out


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
        live_levels = _fetch_contributions(self._user)
        self._live    = live_levels is not None
        self._levels  = live_levels if live_levels else _demo_grid()
        self._dirty   = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            new = _fetch_contributions(self._user)
            if new:
                self._levels = new
                self._live   = True
            else:
                self._live   = False
            self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "COMMITS")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        # Sub-header: who + status pill
        sub_y = widgets.HEADER_H + 6
        d.text("@" + self._user[:18], 10, sub_y, theme.PRIMARY, scale=2)
        pill   = "LIVE" if self._live else "OFFLINE"
        pill_c = theme.GREEN if self._live else theme.MUTED
        pw     = len(pill) * 8 + 12
        d.rect(SW - pw - 8, sub_y - 1, pw, 14, pill_c, fill=True)
        d.text(pill, SW - pw - 2, sub_y + 2, api.WHITE)

        # ── contribution grid ───────────────────────────────────────────
        grid_w = WEEKS * (CELL_PX + GAP_PX) - GAP_PX
        grid_h = DAYS  * (CELL_PX + GAP_PX) - GAP_PX
        gx0    = (SW - grid_w) // 2
        gy0    = sub_y + 28

        # background panel
        pad = 8
        d.rect(gx0 - pad, gy0 - pad,
               grid_w + pad * 2, grid_h + pad * 2,
               theme.CARD, fill=True)
        d.rect(gx0 - pad, gy0 - pad,
               grid_w + pad * 2, 2, theme.PRIMARY, fill=True)

        # cells (only show as many as we have)
        n = len(self._levels)
        for i in range(min(n, WEEKS * DAYS)):
            week = i // DAYS
            day  = i %  DAYS
            cx   = gx0 + week * (CELL_PX + GAP_PX)
            cy   = gy0 + day  * (CELL_PX + GAP_PX)
            d.rect(cx, cy, CELL_PX, CELL_PX,
                   _bucket_color(self._levels[i]), fill=True)

        # ── totals + legend ─────────────────────────────────────────────
        total = sum(1 for x in self._levels if x > 0)
        days  = "%d active days" % total
        d.text(days, gx0 - pad, gy0 + grid_h + pad + 4,
               theme.TEXT_BRIGHT, scale=2)

        lg_y  = SH - widgets.HINT_H - 20
        lg_x  = SW - pad - 8 - 5 * (CELL_PX + GAP_PX) - 36
        d.text("less", lg_x, lg_y + (CELL_PX - 8) // 2, theme.MUTED)
        for i in range(5):
            d.rect(lg_x + 32 + i * (CELL_PX + GAP_PX), lg_y,
                   CELL_PX, CELL_PX, _bucket_color(i), fill=True)
        d.text("more", lg_x + 32 + 5 * (CELL_PX + GAP_PX) + 2,
               lg_y + (CELL_PX - 8) // 2, theme.MUTED)

        self._dirty = False
