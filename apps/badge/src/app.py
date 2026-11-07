"""Badge — GitHub identity card.

Reads GITHUB_USER from secrets.py and draws the profile cached on flash the
moment the app opens, Wi-Fi or not. When the cache is older than
oreoOS.github.PROFILE_TTL_S (or A is pressed) and Wi-Fi is up, a fresh copy
is fetched in the background (oreoOS.cache.Refresh) while the cached card
stays on screen and buttons keep working.

  ┌──────────────────────────────┐
  │ (avatar)  Display Name       │
  │           @login             │
  │           * location         │
  │ ──────────────────────────── │
  │ bio, two lines               │
  │ ┌──────┐ ┌──────┐ ┌──────┐   │
  │ │  42  │ │ 120  │ │  35  │   │
  │ │repos │ │fans  │ │follow│   │
  └──────────────────────────────┘

The avatar is stamped at deploy time by tools/fetch_avatar.py (committed as
apps/badge/assets/optimized/avatar.py) so it renders without Wi-Fi.

Controls:
  A      refresh now
  HOME   apps drawer
"""

import time

import oreoOS
from oreoOS import api, cache, github, pixelfont
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

CX = 10
CY = widgets.HEADER_H + 6
CW = SW - 20
CH = SH - widgets.HEADER_H - widgets.HINT_H - 12
AV_X = CX + 14            # avatar box top-left
AV_Y = CY + 14
TEXT_X = CX + 92          # right-hand identity column


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
        return []
    out, cur = [], ""
    for w in text.split():
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                out.append(cur)
                cur = ""
            while len(w) > max_chars:
                out.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        out.append(cur)
    return out


def _fit(text, max_chars):
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "~"


def _count(n):
    """Compact count: 999, 1.2k, 34k."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    if n < 1000:
        return str(n)
    if n < 10000:
        return "%d.%dk" % (n // 1000, (n % 1000) // 100)
    return "%dk" % (n // 1000)


def _age_label(age_s):
    if age_s is None:
        return ""
    if age_s >= cache.UNKNOWN_AGE:
        return "cached"
    if age_s < 60:
        return "just now"
    if age_s < 3600:
        return "%dm ago" % (age_s // 60)
    if age_s < 86400:
        return "%dh ago" % (age_s // 3600)
    return "%dd ago" % (age_s // 86400)


class App(oreoOS.App):
    name         = "Badge"
    SHOW_LOADING = False      # the cached card is drawn immediately

    def on_enter(self, os):
        self._os = os
        self._user = github.user("octocat")
        self._avatar = _try_avatar()
        try:
            self._pf = pixelfont.load("pixelify_16")
        except (ImportError, AttributeError):
            self._pf = None
        self._profile, self._age0 = github.cached_profile(self._user)
        self._opened_ms = time.ticks_ms()
        self._age_txt = ""
        self._note = None            # "offline" / "sync failed" footnote
        user = self._user
        self._job = cache.Refresh(lambda: github.fetch_profile(user))
        if github.stale(self._age0, github.PROFILE_TTL_S):
            self._refresh(quiet=True)
        self._update_age()
        self._dirty = True

    def on_exit(self):
        # A running fetch finishes on its own and writes the cache; the
        # next open picks the result up from flash.
        self._job = None

    def _refresh(self, quiet=False):
        if self._job is None or self._job.busy():
            return
        if not github.online():
            if not quiet:
                self._note = "no Wi-Fi"
            return
        self._note = None
        self._job.start()

    def _update_age(self):
        if self._age0 is None:
            txt = ""
        elif self._age0 >= cache.UNKNOWN_AGE:
            txt = _age_label(self._age0)
        else:
            el = time.ticks_diff(time.ticks_ms(), self._opened_ms) // 1000
            txt = _age_label(self._age0 + el)
        if txt != self._age_txt:
            self._age_txt = txt
            self._dirty = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            self._refresh()
            self._dirty = True

    def update(self, dt):
        job = self._job
        if job is not None and job.poll():
            if job.result:
                self._profile = job.result
                self._age0 = 0
                self._opened_ms = time.ticks_ms()
                self._note = None
            else:
                self._note = "sync failed"
            self._dirty = True
        self._update_age()

    # ── render ───────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "BADGE")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        d.rect(CX + 2, CY + 2, CW, CH, theme.MUTED2, fill=True)
        d.rect(CX,     CY,     CW, CH, theme.CARD,   fill=True)
        d.rect(CX,     CY,     CW,  3, theme.PRIMARY, fill=True)

        if self._profile is None:
            self._draw_empty(d)
        else:
            self._draw_card(d, self._profile)
        self._draw_status(d)

    def _draw_avatar(self, d, login):
        if self._avatar:
            data, aw, ah = self._avatar
        else:
            data, aw, ah = None, 56, 56
        cx = AV_X + 30
        cy = AV_Y + 30
        _filled_circle(d, cx, cy, 33, theme.PRIMARY)
        _filled_circle(d, cx, cy, 31, theme.CARD)
        if data:
            d.blit(data, cx - aw // 2, cy - ah // 2, aw, ah)
        else:
            _filled_circle(d, cx, cy, 28, theme.DOCK_SEL)
            letter = (login or "?")[:1].upper()
            d.text(letter, cx - 11, cy - 11, theme.PRIMARY, scale=3)

    def _draw_card(self, d, p):
        login = p.get("login") or self._user
        self._draw_avatar(d, login)

        # ── identity column ──
        y = CY + 22
        name = p.get("name") or login
        if self._pf:
            # Proportional font: trim until it fits the column.
            avail = CX + CW - 12 - TEXT_X
            while len(name) > 1 and self._pf.measure(name) > avail:
                name = name[:-1]
            self._pf.text(d, name, TEXT_X, y, theme.TEXT_BRIGHT)
            y += self._pf.h + 6
        else:
            d.text(_fit(name, 12), TEXT_X, y, theme.TEXT_BRIGHT, scale=2)
            y += 22
        d.text(_fit("@" + login, 24), TEXT_X, y, theme.PRIMARY)
        y += 14
        loc = p.get("location") or ""
        if loc:
            d.rect(TEXT_X + 1, y + 2, 4, 4, theme.TEAL, fill=True)
            d.text(_fit(loc, 22), TEXT_X + 10, y, theme.TEAL)

        # ── bio ──
        div_y = CY + 84
        d.rect(CX + 12, div_y, CW - 24, 1, theme.MUTED2, fill=True)
        bio = _wrap(p.get("bio") or "", (CW - 24) // 8)
        if bio:
            for i, line in enumerate(bio[:2]):
                d.text(line, CX + 12, div_y + 8 + i * 11, theme.TEXT_DIM)
        else:
            d.text("open source on GitHub", CX + 12, div_y + 8, theme.MUTED)

        # ── stat tiles ──
        gap = 8
        tw = (CW - 24 - gap * 2) // 3
        th = 46
        ty = CY + CH - th - 12
        for i, (lbl, val, col) in enumerate((
                ("repos",     p.get("repos", 0),     theme.PRIMARY),
                ("followers", p.get("followers", 0), theme.TEAL),
                ("following", p.get("following", 0), theme.GOLD))):
            tx = CX + 12 + i * (tw + gap)
            d.rect(tx, ty, tw, th, theme.DOCK_BG, fill=True)
            d.rect(tx, ty, tw, 2, col, fill=True)
            num = _count(val)
            d.text(num, tx + (tw - len(num) * 16) // 2, ty + 9, col, scale=2)
            d.text(lbl, tx + (tw - len(lbl) * 8) // 2, ty + 31, theme.MUTED)

    def _draw_status(self, d):
        """Sync pill / age label in the card's top-right corner."""
        job = self._job
        if job is not None and job.busy():
            label, bg, fg = "SYNCING", theme.PRIMARY, api.WHITE
        elif self._note:
            label, bg, fg = self._note, theme.ORANGE, api.WHITE
        elif self._age_txt:
            label, bg, fg = self._age_txt, None, theme.MUTED
        else:
            return
        w = len(label) * 8 + 10
        x = CX + CW - w - 6
        y = CY + 7
        if bg is not None:
            d.rect(x, y, w, 12, bg, fill=True)
        d.text(label, x + 5, y + 2, fg)

    def _draw_empty(self, d):
        self._draw_avatar(d, self._user)
        y = CY + 18
        d.text("No profile yet", TEXT_X, y, theme.PRIMARY, scale=1)
        d.text(_fit("@" + self._user, 24), TEXT_X, y + 14, theme.TEXT_BRIGHT)
        lines = (
            "Set these on your laptop,",
            "redeploy, then press A:",
            "",
            "  WIFI_SSID=...",
            "  WIFI_PASSWORD=...",
            "  GITHUB_USER=" + self._user[:16],
        )
        y = CY + 88
        for line in lines:
            d.text(line, CX + 14, y, theme.TEXT_BRIGHT)
            y += 12
