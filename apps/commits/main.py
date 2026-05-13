"""Commits — recent GitHub commits for the user's repo.

Fetches via the GitHub API when WiFi is up; falls back to a baked-in demo
list when offline (so the app still works during dev / on the floor).
Scroll with UP/DOWN, A re-fetches.
"""

import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


# Demo data used until the live fetch is wired up.
_DEMO = [
    ("a1b2c3d", "Add commit-breaker physics"),
    ("e4f5a6b", "Pin the panda sprite alpha"),
    ("d7e8f90", "Bump SPI 26 -> 40 MHz"),
    ("11ab22c", "Snake hi-score persistence"),
    ("987feed", "Loading slide-in for slow apps"),
    ("abcd123", "Tame GC + chunked SPI write"),
    ("dead571", "Flip top obstacles 180 deg"),
    ("fa11ed1", "Settings: brightness slider"),
    ("c0ffee0", "Refactor lix.font to 5x7"),
    ("beef420", "Add IR Quest stub"),
]


def _fetch_commits():
    """Try to fetch via GitHub API; return [] on failure (no Wi-Fi etc.)."""
    try:
        import urequests, ujson  # type: ignore
        from secrets import GITHUB_USER, GITHUB_REPO  # type: ignore
        url = "https://api.github.com/repos/%s/%s/commits?per_page=10" % (
            GITHUB_USER, GITHUB_REPO)
        r = urequests.get(url, headers={"User-Agent": "ElixpoBadge"})
        data = r.json(); r.close()
        return [(c["sha"][:7], c["commit"]["message"].splitlines()[0])
                for c in data]
    except Exception:
        return []


class App(lix.App):
    name = "Commits"

    def on_enter(self, os):
        self._os    = os
        self._top   = 0
        self._dirty = True
        # Try a live fetch; fall back to demo data.
        live = _fetch_commits()
        self._items = live if live else _DEMO

    def on_button_press(self, btn):
        if btn == api.BTN_UP:
            self._top = max(0, self._top - 1); self._dirty = True
        elif btn == api.BTN_DOWN:
            self._top = min(max(0, len(self._items) - 5), self._top + 1)
            self._dirty = True
        elif btn == api.BTN_A:
            live = _fetch_commits()
            if live:
                self._items = live
                self._top   = 0
                self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "COMMITS")
        widgets.draw_hint  (d, "UP/DOWN=scroll  A=refresh")

        y       = widgets.HEADER_H + 8
        row_h   = 32
        visible = (SH - widgets.HEADER_H - widgets.HINT_H - 8) // row_h
        end     = min(len(self._items), self._top + visible)

        for i in range(self._top, end):
            sha, msg = self._items[i]
            ry = y + (i - self._top) * row_h
            # Card
            d.rect(8, ry, SW - 16, row_h - 4, theme.CARD, fill=True)
            d.rect(8, ry, 4,        row_h - 4, theme.PRIMARY, fill=True)
            # sha + message
            d.text(sha, 18, ry + 4, theme.PRIMARY, scale=2)
            d.text(msg[:30], 18, ry + 18, theme.TEXT_BRIGHT)

        # scrollbar
        if len(self._items) > visible:
            bar_h = max(8, (SH - widgets.HEADER_H - widgets.HINT_H) * visible // len(self._items))
            bar_y = widgets.HEADER_H + (
                (SH - widgets.HEADER_H - widgets.HINT_H - bar_h) * self._top
                // max(1, len(self._items) - visible)
            )
            d.rect(SW - 4, bar_y, 3, bar_h, theme.PRIMARY, fill=True)

        self._dirty = False
