"""Host tests for the Commits app grid: a whole year must reach the screen.

The app is loaded from its file against stub oreoOS modules (only
oreoOS/github.py and oreoOS/cache.py are real), and draw() runs against a
fake display that records every rect, so the test sees exactly which week
columns get painted and where.

The bug these guard against: GitHub's contributions page lists the calendar
one weekday row at a time, so a body cut short by the read deadline still
parses into dates spanning the whole year, only with whole weekdays missing.
The app used to place cells by list position, which packed those ~100 days
into the newest ~15 weeks: a quarter of the graph, under a date strip that
claimed the full year.
"""

import datetime
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_commits():
    cache = _load("oreoOS/cache.py", "oreo_cache_commits_test")
    api = types.ModuleType("oreoOS.api")
    api.SCREEN_W, api.SCREEN_H = 320, 240
    api.BTN_A = 1
    api.WHITE = (255, 255, 255)
    api.rgb = lambda r, g, b: (r, g, b)
    theme = types.ModuleType("oreoOS.theme")
    for name in ("BG", "CARD", "PRIMARY", "GOLD", "MUTED", "MUTED2", "TEXT_BRIGHT",
                 "DOCK_SEL", "GREEN", "ORANGE", "TEAL"):
        setattr(theme, name, name)
    widgets = types.ModuleType("oreoOS.widgets")
    widgets.HEADER_H, widgets.HINT_H = 28, 16
    widgets.draw_header = widgets.draw_hint = lambda *a: None
    package = types.ModuleType("oreoOS")
    package.App = object
    package.cache, package.api, package.theme, package.widgets = cache, api, theme, widgets
    saved = {k: sys.modules.get(k) for k in ("oreoOS", "oreoOS.cache")}
    sys.modules["oreoOS"] = package
    sys.modules["oreoOS.cache"] = cache
    try:
        package.github = _load("oreoOS/github.py", "oreo_github_commits_test")
        app = _load("apps/commits/src/app.py", "commits_app_under_test")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return app, package.github


class FakeDisplay:
    def __init__(self):
        self.rects = []
        self.texts = []

    def clear(self, color):
        self.rects = []
        self.texts = []

    def rect(self, x, y, w, h, color, fill=False):
        self.rects.append((x, y, w, h, color))

    def text(self, s, x, y, color, scale=1):
        self.texts.append((s, x, y))


TODAY = datetime.date(2026, 11, 8)        # a Sunday: the newest week has one day


def year(end=TODAY, n=371):
    days = []
    for i in range(n - 1, -1, -1):
        date = end - datetime.timedelta(days=i)
        days.append((date.isoformat(), 1 + i % 4, 1 + i % 3))
    return days


def truncated(days, weekdays=(0, 1)):
    """What a contributions page cut after its first weekday rows parses to."""
    keep = []
    for date, level, count in days:
        wd = (datetime.date.fromisoformat(date).weekday() + 1) % 7   # 0 = Sunday
        if wd in weekdays:
            keep.append((date, level, count))
    return keep


class GridTest(unittest.TestCase):
    def setUp(self):
        self.app_mod, self.github = load_commits()

    def render(self, days):
        app = self.app_mod.App()
        app._user = "Circuit-Overtime"
        app._levels = bytearray(self.app_mod.SLOTS)
        app._set_days(days)
        app._live = False
        app._sync = 0
        app._dirty = True
        d = FakeDisplay()
        app.draw(d)
        m = self.app_mod
        colors = set(m._COLORS)
        cells = [r for r in d.rects
                 if r[2] == m.CELL_PX and r[3] == m.CELL_PX and r[4] in colors
                 and m.GY0 <= r[1] < m.GY0 + m.GRID_H]
        return app, d, cells

    def test_grid_fits_inside_the_card(self):
        m = self.app_mod
        self.assertLessEqual(m.WEEKS * m.PITCH - m.GAP_PX, m.GRID_W)
        self.assertGreaterEqual(m.GX0 - m.GRID_PAD, m.CARD_X + 4)
        self.assertLessEqual(m.GX0 + m.GRID_W + m.GRID_PAD, m.CARD_X + m.CARD_W - 4)
        self.assertLess(m.GY0 + m.GRID_H + m.GRID_PAD, m.STRIP_TOP + 4)
        self.assertGreaterEqual(m.WEEKS, 53)

    def test_full_year_draws_every_week_across_the_width(self):
        _, _, cells = self.render(year())
        m = self.app_mod
        xs = sorted(set(x for x, _, _, _, _ in cells))
        self.assertEqual(len(xs), 53)
        self.assertEqual(xs[0], m.GX0)
        self.assertEqual(xs[-1], m.GX0 + 52 * m.PITCH)
        self.assertEqual(len(cells), 365)     # 52 full weeks + Sunday 8 Nov
        # Newest day: last column, Sunday row.
        self.assertIn((m.GX0 + 52 * m.PITCH, m.GY0), [(x, y) for x, y, _, _, _ in cells])

    def test_cells_sit_at_their_real_weekday(self):
        days = year()
        m = self.app_mod
        _, _, cells = self.render(days)
        pos = {(x, y): c for x, y, _, _, c in cells}
        start = TODAY - datetime.timedelta(days=52 * 7)     # Sunday 9 Nov 2025
        for date, level, _ in days:
            dt = datetime.date.fromisoformat(date)
            if dt < start:
                continue
            k = (dt - start).days
            xy = (m.GX0 + (k // 7) * m.PITCH, m.GY0 + (k % 7) * m.PITCH)
            self.assertEqual(pos[xy], m._COLORS[level], date)

    def test_truncated_page_is_not_packed_into_a_quarter(self):
        # Regression: with list-position placement, Sunday and Monday rows
        # only (106 days) landed in the newest 16 columns.
        _, _, cells = self.render(truncated(year()))
        m = self.app_mod
        xs = sorted(set(x for x, _, _, _, _ in cells))
        self.assertEqual(len(xs), 53)
        self.assertEqual(xs[0], m.GX0)
        ys = set(y for _, y, _, _, _ in cells)
        self.assertEqual(ys, {m.GY0, m.GY0 + m.PITCH})   # only their own rows

    def test_stats_cover_exactly_the_days_on_the_grid(self):
        days = year()
        app, d, cells = self.render(days)
        shown = days[-365:]
        texts = [t for t, _, _ in d.texts]
        self.assertIn("365 active days  ~  365-day streak", texts)
        self.assertIn("9 Nov 2025  -  8 Nov 2026", texts)
        total = sum(c for _, _, c in shown)
        self.assertIn(self.app_mod._fmt_count(total), texts)

    def test_stats_honour_gaps_and_weeks(self):
        m = self.app_mod
        days = [("2026-11-01", 1, 2), ("2026-11-02", 1, 3), ("2026-11-04", 2, 10),
                ("2026-11-07", 0, 0), ("2026-11-08", 1, 4)]
        active, best, cur, busiest, total = m.stats(days)
        self.assertEqual((active, best, cur, total), (4, 2, 1, 19))
        self.assertEqual(busiest, 15)       # Sun 1 .. Sat 7 Nov


class GraphValidationTest(unittest.TestCase):
    def setUp(self):
        _, self.github = load_commits()

    def test_day_number_and_weekday(self):
        g = self.github
        self.assertEqual(g.day_number("1970-01-01"), 0)
        self.assertEqual(g.day_number("2026-11-08"),
                         (datetime.date(2026, 11, 8) - datetime.date(1970, 1, 1)).days)
        self.assertEqual(g.day_number("2024-03-01") - g.day_number("2024-02-28"), 2)
        self.assertEqual(g.weekday(g.day_number("2026-11-08")), 0)   # Sunday
        self.assertEqual(g.weekday(g.day_number("2026-11-14")), 6)   # Saturday

    def test_complete_year_accepted_truncated_page_rejected(self):
        self.assertTrue(self.github.complete(year()))
        self.assertFalse(self.github.complete(truncated(year())))
        self.assertFalse(self.github.complete(year()[:200]))
        self.assertFalse(self.github.complete([]))
        self.assertFalse(self.github.complete(None))


def row_major_page(days):
    """A contributions page laid out like GitHub's: one row per weekday."""
    first = datetime.date.fromisoformat(days[0][0])
    lead = (first.weekday() + 1) % 7
    rows = [[] for _ in range(7)]
    for i, (date, level, count) in enumerate(days):
        k = lead + i
        rows[k % 7].append('<td data-date="%s" id="c-%d" data-level="%d"></td>'
                           '<tool-tip for="c-%d">%d contributions on %s.</tool-tip>'
                           % (date, k, level, k, count, date))
    return ("<table>" + "".join("<tr>" + "".join(r) + "</tr>" for r in rows)
            + "</table>").encode()


class FetchGraphTest(unittest.TestCase):
    def setUp(self):
        _, self.github = load_commits()
        self.dir = tempfile.TemporaryDirectory()
        self.github.GRAPH_PATH = os.path.join(self.dir.name, "cache.txt")
        self.github.online = lambda: True
        self.days = year()
        self.body = row_major_page(self.days)
        self.calls = []

    def tearDown(self):
        self.dir.cleanup()

    def serve(self, body):
        def fake_get(url, accept=None, timeout_s=None, on_progress=None):
            self.calls.append((timeout_s, on_progress))
            if on_progress:
                on_progress("read", len(body))
            return body
        self.github._get = fake_get

    def test_cut_short_page_is_rejected_and_not_cached(self):
        self.serve(self.body[:len(self.body) * 3 // 10])
        self.assertIsNone(self.github.fetch_graph("u"))
        self.assertFalse(os.path.exists(self.github.GRAPH_PATH))

    def test_whole_page_is_parsed_cached_and_reported(self):
        seen = []
        self.serve(self.body)
        days = self.github.fetch_graph("u", lambda phase, n: seen.append(phase))
        self.assertEqual(days, self.days)
        self.assertEqual(seen, ["read", "parse"])
        self.assertEqual(self.calls[0][0], self.github.GRAPH_TIMEOUT_S)
        cached, age = self.github.cached_graph("u")
        self.assertEqual(cached, self.days)
        self.assertIsNotNone(age)

    def test_truncated_cache_is_shown_but_stale(self):
        with open(self.github.GRAPH_PATH, "w") as f:
            f.write("u|%d\n" % 2000000000)
            for date, level, count in truncated(self.days):
                f.write("%s,%d,%d\n" % (date, level, count))
        cached, age = self.github.cached_graph("u")
        self.assertEqual(len(cached), 106)
        self.assertIsNone(age)
        self.assertTrue(self.github.stale(age, self.github.GRAPH_TTL_S))


if __name__ == "__main__":
    unittest.main()
