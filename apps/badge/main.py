"""Badge — GitHub identity card.

Reads GITHUB_USER from secrets.py (configurable on the device). Live-fetches
the public profile JSON over WiFi and renders:

  • rounded-corner "avatar" panel (the API avatar URL fetch needs JPEG/PNG
    decode which MicroPython doesn't have — we render the user's initial in
    a coloured circle as a stand-in until we add a PNG decoder)
  • display name + @login
  • bio
  • repos / followers / following / starred counts

If WiFi isn't up or the API fails, a centred error card explains what to do.

Controls:
  A      manual refresh
  HOME   apps drawer
"""

import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


def _fetch_profile(username):
    """GitHub /users/<u> → dict, or None on any failure."""
    try:
        import urequests
        r = urequests.get("https://api.github.com/users/" + username,
                          headers={"User-Agent": "ElixpoBadge"})
        if r.status_code != 200:
            r.close()
            return None
        data = r.json()
        r.close()
        return {
            "name":      data.get("name") or data.get("login") or username,
            "login":     data.get("login", username),
            "bio":       (data.get("bio") or "")[:60],
            "company":   (data.get("company") or "")[:18],
            "location":  (data.get("location") or "")[:18],
            "followers": data.get("followers", 0),
            "following": data.get("following", 0),
            "repos":     data.get("public_repos", 0),
        }
    except Exception:
        return None


def _rounded_card(d, x, y, w, h, fill, accent=None, r=4):
    """Filled card with chamfered corners + optional top accent stripe."""
    # Shadow
    d.rect(x + 2, y + 2, w, h, theme.MUTED2, fill=True)
    # Body — paint top/bottom strips inset for the chamfered corners
    d.rect(x + r, y,         w - 2 * r, h,         fill, fill=True)
    d.rect(x,     y + r,     r,         h - 2 * r, fill, fill=True)
    d.rect(x + w - r, y + r, r,         h - 2 * r, fill, fill=True)
    # 4-px stair corners
    for s in range(r):
        for col_x in range(s + 1, r):
            d.rect(x + col_x,           y + s,           1, 1, fill, fill=True)
            d.rect(x + w - 1 - col_x,   y + s,           1, 1, fill, fill=True)
            d.rect(x + col_x,           y + h - 1 - s,   1, 1, fill, fill=True)
            d.rect(x + w - 1 - col_x,   y + h - 1 - s,   1, 1, fill, fill=True)
    if accent:
        d.rect(x + r, y, w - 2 * r, 2, accent, fill=True)


def _rounded_circle(d, cx, cy, r, color):
    """Approximate filled circle by horizontal scan-lines (Bresenham-style)."""
    for dy in range(-r, r + 1):
        # half-width at this y (sqrt(r² - dy²))
        dx = int((r * r - dy * dy) ** 0.5)
        d.rect(cx - dx, cy + dy, dx * 2 + 1, 1, color, fill=True)


class App(lix.App):
    name         = "Badge"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os = os
        try:
            from secrets import GITHUB_USER
            self._user = GITHUB_USER
        except Exception:
            self._user = "octocat"
        self._profile = _fetch_profile(self._user)
        self._dirty = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            new = _fetch_profile(self._user)
            if new:
                self._profile = new
            else:
                # keep old data if we had any; else stay in offline state
                pass
            self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "BADGE")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        if self._profile is None:
            self._draw_offline(d)
            self._dirty = False
            return

        p = self._profile

        # ── avatar card (left column) ───────────────────────────────────
        av_x, av_y, av_sz = 16, widgets.HEADER_H + 12, 88
        _rounded_card(d, av_x, av_y, av_sz, av_sz, theme.PRIMARY, accent=theme.GOLD)
        # circular initial overlay
        _rounded_circle(d, av_x + av_sz // 2, av_y + av_sz // 2,
                        av_sz // 2 - 8, theme.CARD)
        letter = (p["login"] or "?")[:1].upper()
        # centre the 4× letter inside the circle
        d.text(letter, av_x + (av_sz - 32) // 2,
                       av_y + (av_sz - 32) // 2, theme.PRIMARY, scale=4)

        # ── info column (right) ─────────────────────────────────────────
        col_x = av_x + av_sz + 14
        y     = widgets.HEADER_H + 10
        d.text(p["name"][:14], col_x, y, theme.PRIMARY,     scale=2); y += 22
        d.text("@" + p["login"][:14], col_x, y, theme.TEAL);          y += 14
        if p["bio"]:
            d.text(p["bio"][:24], col_x, y, theme.TEXT_BRIGHT);       y += 12
        if p.get("location"):
            d.text("[ " + p["location"] + " ]", col_x, y, theme.MUTED); y += 12

        # ── stats row at the bottom ─────────────────────────────────────
        stats_y = SH - widgets.HINT_H - 38
        labels  = [("repos",     p["repos"]),
                   ("followers", p["followers"]),
                   ("following", p.get("following", 0))]
        col_w   = SW // 3
        for i, (lbl, val) in enumerate(labels):
            cx = col_w * i + col_w // 2
            # big number
            num = str(val)
            d.text(num, cx - len(num) * 8, stats_y, theme.PRIMARY, scale=2)
            d.text(lbl, cx - len(lbl) * 4, stats_y + 22, theme.MUTED)

        self._dirty = False

    def _draw_offline(self, d):
        """Graceful offline card explaining where to set credentials."""
        card_w = SW - 40
        card_h = SH - widgets.HEADER_H - widgets.HINT_H - 36
        cx     = (SW - card_w) // 2
        cy     = widgets.HEADER_H + 18
        _rounded_card(d, cx, cy, card_w, card_h, theme.CARD, accent=theme.PRIMARY)

        d.text("offline.", (SW - 8 * 16) // 2, cy + 14, theme.PRIMARY, scale=2)
        lines = [
            ("",                                  None,              1),
            ("Couldn't reach GitHub.",            theme.TEXT_BRIGHT, 1),
            ("",                                  None,              1),
            ("Set credentials by editing",        theme.MUTED,       1),
            ("config (.env) on your laptop:",     theme.MUTED,       1),
            ("",                                  None,              1),
            ("  WIFI_SSID=...",                   theme.GOLD,        1),
            ("  WIFI_PASSWORD=...",               theme.GOLD,        1),
            ("  GITHUB_USER=" + self._user[:14],  theme.GOLD,        1),
            ("",                                  None,              1),
            ("Then re-deploy and press A.",       theme.TEAL,        1),
        ]
        ly = cy + 42
        for ln, col, sc in lines:
            if ln:
                lw = len(ln) * 8 * sc
                d.text(ln, (SW - lw) // 2, ly, col, scale=sc)
            ly += 10 * sc + 2
