"""Badge — show the user's GitHub identity card.

Reads GITHUB_USER from secrets.py (or defaults to a placeholder). Fetches
public profile JSON over WiFi when available; falls back to cached static
data otherwise. Layout: mascot avatar placeholder + name + stats.
"""

import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


def _fetch_profile(username):
    try:
        import urequests
        r = urequests.get("https://api.github.com/users/" + username,
                          headers={"User-Agent": "ElixpoBadge"})
        data = r.json(); r.close()
        return {
            "name":      data.get("name") or data.get("login") or username,
            "login":     data.get("login", username),
            "bio":       (data.get("bio") or "")[:30],
            "followers": data.get("followers", 0),
            "repos":     data.get("public_repos", 0),
        }
    except Exception:
        return None


class App(lix.App):
    name = "Badge"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os = os
        try:
            from secrets import GITHUB_USER
            self._user = GITHUB_USER
        except Exception:
            self._user = "octocat"
        self._profile = _fetch_profile(self._user) or {
            "name":      self._user,
            "login":     self._user,
            "bio":       "offline — using cache",
            "followers": 0,
            "repos":     0,
        }
        self._dirty = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            new = _fetch_profile(self._user)
            if new:
                self._profile = new
                self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "BADGE")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        p = self._profile
        # Avatar placeholder — colored square with first letter
        ax, ay = 20, widgets.HEADER_H + 22
        d.rect(ax, ay, 80, 80, theme.PRIMARY, fill=True)
        d.text(p["login"][0].upper(), ax + (80 - 32) // 2, ay + (80 - 32) // 2,
               api.WHITE, scale=4)

        col_x = ax + 92
        y     = widgets.HEADER_H + 14
        d.text(p["name"][:14],     col_x, y, theme.PRIMARY,     scale=2); y += 22
        d.text("@" + p["login"][:13], col_x, y, theme.TEAL); y += 16
        if p["bio"]:
            d.text(p["bio"][:24],     col_x, y, theme.TEXT_BRIGHT); y += 16
        y += 6
        d.text("repos    %d" % p["repos"],     col_x, y, theme.TEXT_DIM); y += 12
        d.text("followers %d" % p["followers"],col_x, y, theme.TEXT_DIM)

        self._dirty = False
