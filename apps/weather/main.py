"""Weather — live conditions via OpenWeather, panda mascot per condition.

Reads OWM_API_KEY + WEATHER_LAT/LON/NAME from secrets.py. Layout:

  ┌──── header ────────────────────────────────────┐
  │ WEATHER                                        │
  ├────────────────────────────────────────────────┤
  │                                                │
  │ [PANDA]          26°               ☀ Clear    │
  │                  Bengaluru                     │
  │                  💧 64%   🌬 4 m/s  🌡 28°    │
  │                                                │
  └────────────────────────────────────────────────┘

The bg is a SINGLE pre-rendered image (no tiling) dimmed to ~26 % brightness
so the white temperature reads crisply on top.

Controls:
  A      force refresh
  HOME   apps drawer
"""

import time
import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

REFRESH_SEC = 600        # 10 min auto-refresh
DIM_FACTOR  = 0.26       # ~26 % brightness on the bg


def _bucket(code):
    """OpenWeather condition code → (sprite_name, friendly_label)."""
    if code is None:        return ("cloud", "Unknown")
    if 200 <= code < 300:   return ("storm", "Thunder")
    if 300 <= code < 600:   return ("rain",  "Rain")
    if 600 <= code < 700:   return ("snow",  "Snow")
    if 700 <= code < 800:   return ("cloud", "Misty")
    if code == 800:         return ("sun",   "Clear")
    if 801 <= code < 900:   return ("cloud", "Cloudy")
    return ("cloud", "Unknown")


def _try_sprite(name):
    try:
        m = __import__("apps.weather.assets.optimized." + name, None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _dim_bg(buf, factor=DIM_FACTOR):
    """Return a NEW bytearray with every RGB565 pixel × factor.

    One-time cost at app entry (~150 ms on hardware for a 320×something
    buffer); reused as the rendered bg every frame.
    """
    n   = len(buf) // 2
    out = bytearray(len(buf))
    fac = int(factor * 256)
    for i in range(n):
        v = (buf[i*2] << 8) | buf[i*2 + 1]
        r = ((v >> 11) & 0x1F) * fac >> 8
        g = ((v >>  5) & 0x3F) * fac >> 8
        b = ( v        & 0x1F) * fac >> 8
        v2 = (r << 11) | (g << 5) | b
        out[i*2]     = v2 >> 8
        out[i*2 + 1] = v2 & 0xFF
    return out


def _fetch_owm(lat, lon, api_key):
    """Return parsed dict or None."""
    try:
        import urequests
        url = ("https://api.openweathermap.org/data/2.5/weather"
               "?lat=%.3f&lon=%.3f&units=metric&appid=%s" % (lat, lon, api_key))
        r = urequests.get(url, headers={"User-Agent": "OreoBadge"})
        if r.status_code != 200:
            r.close()
            return None
        j = r.json(); r.close()
        return {
            "temp":  round(float(j.get("main", {}).get("temp", 0))),
            "feels": round(float(j.get("main", {}).get("feels_like", 0))),
            "hum":   int(j.get("main", {}).get("humidity", 0)),
            "wind":  float(j.get("wind", {}).get("speed", 0)),
            "code":  int((j.get("weather") or [{"id": 0}])[0].get("id", 0)),
            "city":  j.get("name") or "—",
        }
    except Exception:
        return None


class App(oreoOS.App):
    name         = "Weather"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os = os
        try:
            from secrets import WEATHER_LAT, WEATHER_LON, OWM_API_KEY
            self._lat = float(WEATHER_LAT)
            self._lon = float(WEATHER_LON)
            self._key = OWM_API_KEY
        except Exception:
            self._lat, self._lon, self._key = 12.97, 77.59, ""

        # Pre-build the dimmed background — used as a single full-screen blit
        # every frame, no tiling.
        bg = _try_sprite("background")
        if bg:
            data, bw, bh = bg
            self._bg_dim = (_dim_bg(data), bw, bh)
        else:
            self._bg_dim = None

        # Panda condition sprites (pre-cached so per-frame is one blit)
        self._pandas = {k: _try_sprite("panda_" + k)
                        for k in ("sun", "cloud", "rain", "snow", "storm")}

        self._data  = None
        self._last  = 0
        self._refresh()
        self._dirty = True

    def _refresh(self):
        self._data = _fetch_owm(self._lat, self._lon, self._key) if self._key else None
        self._last = time.ticks_ms()
        self._dirty = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            self._refresh()

    def update(self, dt):
        if time.ticks_diff(time.ticks_ms(), self._last) > REFRESH_SEC * 1000:
            self._refresh()

    # ── render ───────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        # ── single bg blit (dimmed, NOT tiled) ────────────────────────
        if self._bg_dim:
            data, bw, bh = self._bg_dim
            # Stretch-tile: blit at SW width if bg is wide enough, else stamp
            # once centred. Bg asset is 80×60 → ×4 it's 320×240 full screen.
            # For non-square ratios we just stamp once at (0, _MAIN_TOP).
            d.clear(api.rgb(20, 30, 45))   # navy fallback under any uncovered area
            d.blit(data, 0, widgets.HEADER_H, bw, bh)
            # Fill the rest with the avg dimmed tone if bg doesn't cover
            if bh < SH - widgets.HEADER_H - widgets.HINT_H:
                fill_h = SH - widgets.HEADER_H - widgets.HINT_H - bh
                d.rect(0, widgets.HEADER_H + bh, SW, fill_h,
                       api.rgb(20, 30, 45), fill=True)
        else:
            d.clear(api.rgb(20, 30, 45))

        widgets.draw_header(d, "WEATHER")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        if not self._key:
            self._draw_setup_card(d)
            self._dirty = False
            return
        if self._data is None:
            self._draw_offline(d)
            self._dirty = False
            return

        p             = self._data
        cond_key, lbl = _bucket(p["code"])
        sprite        = self._pandas.get(cond_key)

        # Vertically centre the whole content block in the play area.
        play_top  = widgets.HEADER_H
        play_h    = SH - widgets.HEADER_H - widgets.HINT_H

        # ── LEFT: panda sprite (bigger; 80×80) ────────────────────────
        panda_w = panda_h = 80
        if sprite:
            data, panda_w, panda_h = sprite
        panda_x = 16
        panda_y = play_top + (play_h - panda_h) // 2
        if sprite:
            d.blit(sprite[0], panda_x, panda_y, panda_w, panda_h)
        else:
            d.rect(panda_x, panda_y, panda_w, panda_h, theme.PRIMARY, fill=True)

        # ── RIGHT column: temp + city + emoji metric row ──────────────
        col_x   = panda_x + panda_w + 18
        col_top = play_top + 8

        # Big white temperature with little degree-mark
        t_str = "%d" % p["temp"]
        d.text(t_str, col_x, col_top, api.WHITE, scale=5);
        # degree-circle to the right of the digits
        deg_x = col_x + len(t_str) * 8 * 5 + 4
        d.rect(deg_x,     col_top + 4,  6, 6, api.WHITE, fill=False)
        d.rect(deg_x + 1, col_top + 5,  4, 4, api.rgb(20, 30, 45), fill=True)
        # condition label small under the degree
        d.text(lbl, deg_x, col_top + 18, theme.GOLD)

        # City name in a light tone (legible on dim bg)
        city_y = col_top + 48
        d.text(p["city"][:14], col_x, city_y, theme.DOCK_BG, scale=2)

        # Metric row using emoji-as-text — simple ASCII glyphs since framebuf
        # 8×8 doesn't have emoji. Three columns: feels / humidity / wind.
        m_y = city_y + 26
        metrics = [
            ("F",  "%d C" % p["feels"]),   # F for "Feels like"
            ("H",  "%d%%" % p["hum"]),
            ("W",  "%dm/s" % round(p["wind"])),
        ]
        col_w = (SW - col_x - 12) // len(metrics)
        for i, (icon, val) in enumerate(metrics):
            mx = col_x + i * col_w
            # icon badge
            d.rect(mx, m_y, 16, 12, theme.PRIMARY, fill=True)
            d.text(icon, mx + 4, m_y + 2, api.WHITE)
            d.text(val, mx + 20, m_y + 2, api.WHITE)

        self._dirty = False

    # ── error cards ──────────────────────────────────────────────────────
    def _draw_setup_card(self, d):
        cw, ch = SW - 32, SH - widgets.HEADER_H - widgets.HINT_H - 32
        cx, cy = 16, widgets.HEADER_H + 16
        d.rect(cx, cy, cw, ch, theme.CARD, fill=True)
        d.rect(cx, cy, cw, 2,  theme.PRIMARY, fill=True)
        d.text("setup needed", (SW - 12 * 16) // 2, cy + 14, theme.PRIMARY, scale=2)
        for i, ln in enumerate([
                "Set on your laptop:",
                "",
                "  OWM_API_KEY=...",
                "  WEATHER_LAT=...",
                "  WEATHER_LON=...",
                "",
                "edit .env then redeploy."]):
            d.text(ln, cx + 16, cy + 38 + i * 14, theme.TEXT_BRIGHT)

    def _draw_offline(self, d):
        msg = "offline — press A to retry"
        d.rect(20, 110, SW - 40, 36, theme.CARD, fill=True)
        d.rect(20, 110, SW - 40,  2, theme.PRIMARY, fill=True)
        d.text("offline", (SW - 7 * 16) // 2, 118, theme.PRIMARY, scale=2)
        d.text(msg, (SW - len(msg) * 8) // 2, 138, theme.TEXT_BRIGHT)
