"""Badge — GitHub identity card.

Reads GITHUB_USER from secrets.py. Live-fetches the public profile JSON over
WiFi and renders a centred identity card:

  ╔════════════════════╗
  ║       (avatar)     ║
  ║  Display Name      ║
  ║  @login            ║
  ║  ──────────────    ║
  ║ repos  fol  fol    ║
  ║   42  120  35      ║
  ╚════════════════════╝

The avatar is stamped at deploy time by tools/fetch_avatar.py (committed as
apps/badge/assets/optimized/avatar.py) so it renders on-device without WiFi.

Controls:
  A      refresh stats
  HOME   apps drawer
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
        if r.status_code != 200:
            r.close()
            return None
        data = r.json(); r.close()
        return {
            "name":      data.get("name") or data.get("login") or username,
            "login":     data.get("login", username),
            "bio":       (data.get("bio") or "")[:60],
            "location":  (data.get("location") or "")[:24],
            "followers": data.get("followers", 0),
            "following": data.get("following", 0),
            "repos":     data.get("public_repos", 0),
        }
    except Exception:
        return None


def _try_avatar():
    """Load the pre-fetched avatar baked at deploy time, or None."""
    try:
        m = __import__("apps.badge.assets.optimized.avatar", None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _filled_circle(d, cx, cy, r, color):
    """Approximate filled circle by horizontal scan-lines."""
    for dy in range(-r, r + 1):
        dx = int((r * r - dy * dy) ** 0.5)
        d.rect(cx - dx, cy + dy, dx * 2 + 1, 1, color, fill=True)


def _wrap(text, max_chars):
    """Word-wrap helper — splits at spaces, hard-breaks oversized words."""
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
                cur = ""
            if len(w) > max_chars:
                while len(w) > max_chars:
                    out.append(w[:max_chars])
                    w = w[max_chars:]
            cur = w
    if cur:
        out.append(cur)
    return out


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
        self._avatar  = _try_avatar()
        self._profile = _fetch_profile(self._user)
        self._dirty   = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            new = _fetch_profile(self._user)
            if new:
                self._profile = new
            self._dirty = True

    def update(self, dt):
        pass

    # ── render ───────────────────────────────────────────────────────────
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

        # Card centred in the play area.
        play_top = widgets.HEADER_H
        play_h   = SH - widgets.HEADER_H - widgets.HINT_H
        cw, ch   = SW - 24, play_h - 16
        cx, cy   = (SW - cw) // 2, play_top + 8
        # Soft shadow + body + top accent
        d.rect(cx + 2, cy + 2, cw, ch, theme.MUTED2, fill=True)
        d.rect(cx,     cy,     cw, ch, theme.CARD,   fill=True)
        d.rect(cx,     cy,     cw,  3, theme.PRIMARY, fill=True)

        # ── avatar (top-centred, 64×64 rounded clipped to circle) ────
        av_sz  = 64
        av_cx  = SW // 2
        av_cy  = cy + 12 + av_sz // 2
        # Circle base — placed on the card so it reads as a "framed photo"
        _filled_circle(d, av_cx, av_cy, av_sz // 2 + 3, theme.PRIMARY)
        if self._avatar:
            data, aw, ah = self._avatar
            d.blit(data, av_cx - aw // 2, av_cy - ah // 2, aw, ah)
        else:
            # initial letter inside a paler inner circle
            _filled_circle(d, av_cx, av_cy, av_sz // 2, theme.CARD)
            letter = (p["login"] or "?")[:1].upper()
            d.text(letter, av_cx - 16, av_cy - 16, theme.PRIMARY, scale=4)

        # ── name + @login centred under avatar (wrapping if needed) ──
        name_y = av_cy + av_sz // 2 + 12
        for line in _wrap(p["name"][:32], 18)[:1]:
            lw = len(line) * 16
            d.text(line, (SW - lw) // 2, name_y, theme.PRIMARY, scale=2)
        name_y += 22

        # @login — wrap aggressively so Circuit-Overtime (16) fits one line
        login_lines = _wrap("@" + p["login"], 24)[:2]
        for ln in login_lines:
            lw = len(ln) * 8
            d.text(ln, (SW - lw) // 2, name_y, theme.TEAL)
            name_y += 10

        if p.get("location"):
            loc = "[ " + p["location"] + " ]"
            lw  = len(loc) * 8
            d.text(loc, (SW - lw) // 2, name_y, theme.MUTED)
            name_y += 12

        # ── stats row at the bottom of the card ──────────────────────
        stats_y = cy + ch - 30
        col_w   = cw // 3
        for i, (lbl, val) in enumerate([
                ("repos",     p["repos"]),
                ("followers", p["followers"]),
                ("following", p.get("following", 0))]):
            mx = cx + col_w * i + col_w // 2
            num = str(val)
            d.text(num, mx - len(num) * 8, stats_y, theme.PRIMARY, scale=2)
            d.text(lbl, mx - len(lbl) * 4, stats_y + 22, theme.MUTED)

        self._dirty = False

    def _draw_offline(self, d):
        cw, ch = SW - 32, SH - widgets.HEADER_H - widgets.HINT_H - 32
        cx, cy = 16, widgets.HEADER_H + 16
        d.rect(cx + 2, cy + 2, cw, ch, theme.MUTED2, fill=True)
        d.rect(cx,     cy,     cw, ch, theme.CARD,   fill=True)
        d.rect(cx,     cy,     cw,  2, theme.PRIMARY, fill=True)
        d.text("offline", (SW - 7 * 16) // 2, cy + 14, theme.PRIMARY, scale=2)
        for i, line in enumerate([
                "Couldn't reach GitHub.",
                "",
                "set on your laptop:",
                "",
                "  WIFI_SSID=...",
                "  WIFI_PASSWORD=...",
                "  GITHUB_USER=" + self._user[:16],
                "",
                "redeploy + press A."]):
            d.text(line, cx + 16, cy + 42 + i * 12, theme.TEXT_BRIGHT)
