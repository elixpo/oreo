"""Commits — GitHub contribution graph + stat strip.

Opens instantly from the graph cached on flash; when it is older than
oreoOS.github.GRAPH_TTL_S and WiFi is connected, it refreshes after the first
frame under a SYNCING label. Press A to refresh now. Layout fills the play area as
one tall card so there's no dead cream space below the grid:

  ┌── card ───────────────────────────────────────────┐
  │           @Circuit-Overtime                       │
  │           ──────────────────                      │
  │       352 active days  ~  45-day streak           │
  │                                                   │
  │   ░░▓▓██▓▓░░░▓▓    ← 53×7 contribution grid      │
  │   ...                                             │
  │                                                   │
  │   current  3       busiest  18      total  1.2k   │
  │                                                   │
  │ less ▒▒▓▓██ more                          [LIVE]  │
  └───────────────────────────────────────────────────┘

Data: `https://github.com/users/<user>/contributions`, one HTTPS fetch, no
token, parsed by oreoOS.github into chronological (date, level, count) days.
Each day is placed on the grid by its date (week column, weekday row), newest
week on the right, as on GitHub; a missing date leaves its own cell empty
instead of shifting the rest of the year.

Controls:
  A      refresh
  HOME   apps drawer
"""

import oreoOS
from oreoOS import api, github
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

# GitHub's calendar is 53 week columns (371 slots, the newest week partly in
# the future). 53 x 5 px pitch = 264 px, which leaves margins inside the
# 300 px card; 5 px cells with a 1 px gap (317 px) would overflow it.
WEEKS    = 53
DAYS     = 7
CELL_PX  = 4
GAP_PX   = 1
PITCH    = CELL_PX + GAP_PX
SLOTS    = WEEKS * DAYS
NO_DAY   = 255                 # grid slot with no data (missing or future)

GRID_W = WEEKS * PITCH - GAP_PX
GRID_H = DAYS  * PITCH - GAP_PX

# Fixed layout: one card filling the play area.
CARD_X = 10
CARD_Y = widgets.HEADER_H + 4
CARD_W = SW - 20
CARD_H = SH - widgets.HEADER_H - widgets.HINT_H - 8
USER_Y = CARD_Y + 8
GX0    = (SW - GRID_W) // 2
_SUB_BOT   = USER_Y + 52                      # subtitle + date range
STRIP_TOP  = CARD_Y + CARD_H - 60             # stat strip + legend
GY0    = _SUB_BOT + max(0, (STRIP_TOP - _SUB_BOT - GRID_H) // 2)
GRID_PAD = 4
LEG_Y  = CARD_Y + CARD_H - 14

BUCKETS = [
    (235, 237, 240),
    (155, 233, 168),
    ( 64, 196,  99),
    ( 48, 161,  78),
    ( 33, 110,  57),
]
_COLORS = [api.rgb(r, g, b) for r, g, b in BUCKETS]


def _bucket_color(level):
    return _COLORS[max(0, min(4, level))]


_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fmt_date(iso):
    """yyyy-mm-dd → 'D Mon YYYY' for the date-range strip."""
    if not iso or len(iso) < 10:
        return ""
    try:
        y, m, d = iso[:4], int(iso[5:7]), int(iso[8:10])
        return "%d %s %s" % (d, _MONTHS[m], y)
    except (ValueError, IndexError):
        return iso


def place(days, levels):
    """Lay `days` out on the WEEKS x DAYS grid by their dates.

    `levels` (a bytearray of SLOTS) gets one level per slot, column-major
    from the oldest Sunday: slot = week * 7 + weekday. The newest day sits in
    the last column at its weekday row, as on GitHub; slots after it, and
    any date missing from `days`, stay NO_DAY. Cells are placed by date and
    never by list position, so a gap in the data cannot slide the rest of
    the year sideways.

    Returns (first, last_slot): days[first:] are the days on the grid, and
    last_slot is the newest day's slot (-1 when there are no days).
    """
    for i in range(SLOTS):
        levels[i] = NO_DAY
    if not days:
        return 0, -1
    last = github.day_number(days[-1][0])
    last_slot = SLOTS - 1 - (6 - github.weekday(last))
    start = last - last_slot                  # day number of slot 0, a Sunday
    first = len(days)
    for i in range(len(days) - 1, -1, -1):
        k = github.day_number(days[i][0]) - start
        if k < 0:
            break
        if k <= last_slot:
            levels[k] = max(0, min(4, days[i][1]))
        first = i
    return first, last_slot


def stats(days):
    """(active, longest streak, current streak, busiest week, total).

    Streaks only count calendar-consecutive days, so a missing date breaks
    them instead of being skipped over.
    """
    active = total = best = run = busiest = week = 0
    prev = wk = None
    for date, level, count in days:
        n = github.day_number(date)
        if prev is None or n != prev + 1:
            run = 0
        w = (n + 4) // 7            # Sunday-to-Saturday week index
        if w != wk:
            week = 0
            wk = w
        prev = n
        total += count
        week += count
        if week > busiest:
            busiest = week
        if level > 0:
            active += 1
            run += 1
            if run > best:
                best = run
        else:
            run = 0
    # Current streak: days in a row up to the newest; it may have none yet.
    cur = 0
    prev = None
    for k in range(len(days) - 1, -1, -1):
        n = github.day_number(days[k][0])
        if prev is not None and n != prev - 1:
            break
        prev = n
        if days[k][1] > 0:
            cur += 1
        elif k < len(days) - 1:
            break
    return active, best, cur, busiest, total


def _fmt_count(n):
    if n >= 1000:
        return "%.1fk" % (n / 1000.0)
    return str(n)


class App(oreoOS.App):
    name         = "Commits"
    SHOW_LOADING = False      # the cached graph is drawn immediately

    def on_enter(self, os):
        self._os = os
        self._user = github.user("Circuit-Overtime")
        self._levels = bytearray(SLOTS)
        days, age = github.cached_graph(self._user)
        self._set_days(days)
        self._live = False
        # 0 idle, 1 SYNCING label requested, 2 label drawn: fetch now.
        self._sync = 1 if (github.stale(age, github.GRAPH_TTL_S)
                           and github.online()) else 0
        self._dirty = True

    def _set_days(self, days):
        """Adopt a new day list; everything derived from it is built here,
        once, so draw() only paints."""
        self._days = days or None
        first, self._last_slot = place(days, self._levels)
        shown = days[first:] if days else []
        if not shown:
            return
        active, best, cur, busy, total = stats(shown)
        self._sub = "%d active days  ~  %d-day streak" % (active, best)
        a, b = _fmt_date(shown[0][0]), _fmt_date(shown[-1][0])
        self._range = "%s  -  %s" % (a, b) if a and b else ""
        self._cols = (("current", "%dd" % cur),
                      ("busiest", "%d" % busy),
                      ("total",   _fmt_count(total)))

    def on_button_press(self, btn):
        if btn == api.BTN_A and self._sync == 0:
            self._sync = 1
            self._dirty = True

    def update(self, dt):
        if self._sync == 1:
            self._sync = 2          # let draw() paint the SYNCING label first
        elif self._sync == 2:
            days = github.fetch_graph(self._user)
            if days:
                self._set_days(days)
                self._live = True
            self._sync = 0
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "COMMITS")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        d.rect(CARD_X + 2, CARD_Y + 2, CARD_W, CARD_H, theme.MUTED2, fill=True)
        d.rect(CARD_X,     CARD_Y,     CARD_W, CARD_H, theme.CARD,   fill=True)
        d.rect(CARD_X,     CARD_Y,     CARD_W, 3,      theme.PRIMARY, fill=True)

        # Username (scale=2 pink) + gold underline.
        user_str = "@" + self._user[:17]
        uw = len(user_str) * 16
        d.text(user_str, (SW - uw) // 2, USER_Y, theme.PRIMARY, scale=2)
        d.rect((SW - uw) // 2, USER_Y + 20, uw, 2, theme.GOLD, fill=True)

        if not self._days:
            self._draw_empty(d)
            self._draw_sync(d)
            return

        # Headline (active days, longest streak) and the window it covers.
        d.text(self._sub, (SW - len(self._sub) * 8) // 2, USER_Y + 28,
               theme.TEXT_BRIGHT)
        if self._range:
            d.text(self._range, (SW - len(self._range) * 8) // 2,
                   USER_Y + 40, theme.MUTED)

        self._draw_grid(d)

        # Stat strip: current streak / busiest week / total contributions.
        strip_y = STRIP_TOP + 4
        col_w = CARD_W // len(self._cols)
        for i, (lbl, val) in enumerate(self._cols):
            mx = CARD_X + col_w * i + col_w // 2
            d.text(val, mx - len(val) * 8, strip_y, theme.PRIMARY, scale=2)
            d.text(lbl, mx - len(lbl) * 4, strip_y + 22, theme.MUTED)

        self._draw_legend(d)
        self._draw_sync(d)

    def _draw_grid(self, d):
        """Every week of the year, oldest on the left, newest on the right."""
        d.rect(GX0 - GRID_PAD, GY0 - GRID_PAD,
               GRID_W + GRID_PAD * 2, GRID_H + GRID_PAD * 2,
               theme.DOCK_SEL, fill=True)
        levels = self._levels
        colors = _COLORS
        for k in range(self._last_slot + 1):
            lv = levels[k]
            if lv != NO_DAY:
                d.rect(GX0 + (k // DAYS) * PITCH, GY0 + (k % DAYS) * PITCH,
                       CELL_PX, CELL_PX, colors[lv], fill=True)

    def _draw_legend(self, d):
        """Legend (bottom-left) and LIVE / OFFLINE pill (bottom-right)."""
        lg_x = CARD_X + 10
        d.text("less", lg_x, LEG_Y + (CELL_PX - 8) // 2, theme.MUTED)
        for i in range(5):
            d.rect(lg_x + 36 + i * PITCH, LEG_Y, CELL_PX, CELL_PX,
                   _COLORS[i], fill=True)
        d.text("more", lg_x + 36 + 5 * PITCH + 4,
               LEG_Y + (CELL_PX - 8) // 2, theme.MUTED)

        pill   = "LIVE" if self._live else "OFFLINE"
        pill_c = theme.GREEN if self._live else theme.MUTED
        pw     = len(pill) * 8 + 12
        d.rect(CARD_X + CARD_W - pw - 10, LEG_Y - 2, pw, 12, pill_c, fill=True)
        d.text(pill, CARD_X + CARD_W - pw - 4, LEG_Y, api.WHITE)

    def _draw_sync(self, d):
        if not self._sync:
            return
        label = "SYNCING"
        w = len(label) * 8 + 12
        x = SW - w - 8
        y = widgets.HEADER_H + 4
        d.rect(x, y, w, 12, theme.PRIMARY, fill=True)
        d.text(label, x + 6, y + 2, api.WHITE)

    def _draw_empty(self, d):
        lines = ("No contribution data yet.",
                 "Connect WiFi, then press A." if not self._sync
                 else "Fetching from GitHub...")
        for i, line in enumerate(lines):
            d.text(line, (SW - len(line) * 8) // 2, USER_Y + 50 + i * 14,
                   theme.TEXT_BRIGHT)
