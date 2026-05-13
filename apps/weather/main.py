"""Weather — live conditions via OpenWeather.

Reads OWM_API_KEY, WEATHER_LAT, WEATHER_LON, WEATHER_NAME from secrets.py
on the badge. Edit those to point at YOUR location; nothing else changes.

Each condition picks a different panda expression sprite, on top of a tiled
background image (apps/weather/assets/optimized/{background,panda_*}.py —
generate via tools/generate_assets.py --app weather).

Controls:
  A      force refresh
  HOME   apps drawer
"""

import time
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

REFRESH_SEC = 600       # 10 min between auto-refreshes

# Map OpenWeather condition codes (https://openweathermap.org/weather-conditions)
# to a panda-expression sprite name + a friendly label.
def _bucket(code):
    if code is None:
        return ("cloud", "Unknown")
    if 200 <= code < 300:  return ("storm", "Thunderstorm")
    if 300 <= code < 600:  return ("rain",  "Rain")
    if 600 <= code < 700:  return ("snow",  "Snow")
    if 700 <= code < 800:  return ("cloud", "Misty")
    if code == 800:        return ("sun",   "Clear")
    if 801 <= code < 900:  return ("cloud", "Cloudy")
    return ("cloud", "Unknown")


def _try_sprite(name):
    try:
        m = __import__("apps.weather.assets.optimized." + name, None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _fetch_owm(lat, lon, api_key):
    """Return parsed dict or None. Uses /weather (current conditions)."""
    try:
        import urequests
        url = ("https://api.openweathermap.org/data/2.5/weather"
               "?lat=%.3f&lon=%.3f&units=metric&appid=%s" % (lat, lon, api_key))
        r = urequests.get(url, headers={"User-Agent": "ElixpoBadge"})
        if r.status_code != 200:
            r.close()
            return None
        j = r.json(); r.close()
        return {
            "temp":     float(j.get("main", {}).get("temp", 0)),
            "feels":    float(j.get("main", {}).get("feels_like", 0)),
            "hum":      int(j.get("main", {}).get("humidity", 0)),
            "wind":     float(j.get("wind", {}).get("speed", 0)),
            "code":     int((j.get("weather") or [{"id": 0}])[0].get("id", 0)),
            "desc":     (j.get("weather") or [{"description": ""}])[0]
                          .get("description", "")[:18],
            "city":     j.get("name") or "—",
        }
    except Exception:
        return None


class App(lix.App):
    name         = "Weather"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os         = os
        try:
            import secrets
            self._lat = float(getattr(secrets, "WEATHER_LAT", 12.97))
            self._lon = float(getattr(secrets, "WEATHER_LON", 77.59))
            self._key = getattr(secrets, "OWM_API_KEY", "")
        except Exception:
            self._lat = 12.97
            self._lon = 77.59
            self._key = ""

        self._bg  = _try_sprite("background")
        # Pre-load all 5 condition sprites once
        self._pandas = {
            k: _try_sprite("panda_" + k)
            for k in ("sun", "cloud", "rain", "snow", "storm")
        }

        self._data     = None
        self._last     = 0
        self._refresh()
        self._dirty    = True

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

        # Tile the bg image across the play area (or a flat fallback).
        d.clear(theme.BG)
        if self._bg:
            data, bw, bh = self._bg
            y = widgets.HEADER_H
            while y < SH - widgets.HINT_H:
                x = 0
                while x < SW:
                    d.blit(data, x, y, bw, bh)
                    x += bw
                y += bh

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

        # ── condition panda sprite on the LEFT ────────────────────────
        if sprite:
            data, mw, mh = sprite
            d.blit(data, 16, widgets.HEADER_H + 18, mw, mh)
        else:
            d.rect(16, widgets.HEADER_H + 18, 80, 80, theme.PRIMARY, fill=True)

        # ── condition pill ABOVE the panda ─────────────────────────────
        pill   = lbl[:14]
        pw     = len(pill) * 8 + 10
        d.rect(16, widgets.HEADER_H + 6, pw, 12, theme.PRIMARY, fill=True)
        d.text(pill, 21, widgets.HEADER_H + 8, api.WHITE)

        # ── temperature + city ────────────────────────────────────────
        col_x = 110
        y     = widgets.HEADER_H + 14
        t_str = "%d C" % round(p["temp"])
        d.text(t_str, col_x, y, theme.PRIMARY, scale=4); y += 38
        d.text(p["city"][:14], col_x, y, theme.TEXT_BRIGHT, scale=2); y += 22
        d.text("feels %d C" % round(p["feels"]),  col_x, y, theme.MUTED); y += 12
        d.text("humidity %d%%" % p["hum"],        col_x, y, theme.MUTED); y += 12
        d.text("wind %.0f m/s" % p["wind"],       col_x, y, theme.MUTED)

        self._dirty = False

    # ── error cards ──────────────────────────────────────────────────────
    def _draw_setup_card(self, d):
        """Shown when OWM_API_KEY isn't set. Explains where to set it."""
        cx, cy, cw, ch = 16, widgets.HEADER_H + 18, SW - 32, SH - widgets.HEADER_H - widgets.HINT_H - 36
        d.rect(cx, cy, cw, ch, theme.CARD, fill=True)
        d.rect(cx, cy, cw, 2,  theme.PRIMARY, fill=True)
        d.text("setup needed", (SW - 12 * 16) // 2, cy + 14, theme.PRIMARY, scale=2)
        lines = [
            ("",                                  None,              1),
            ("Edit on your laptop:",              theme.TEXT_BRIGHT, 1),
            ("",                                  None,              1),
            ("  OWM_API_KEY=...",                 theme.GOLD,        1),
            ("  WEATHER_LAT=...",                 theme.GOLD,        1),
            ("  WEATHER_LON=...",                 theme.GOLD,        1),
            ("",                                  None,              1),
            ("Path:",                             theme.MUTED,       1),
            ("  .env (laptop) or",                theme.TEAL,        1),
            ("  /secrets.py (device)",            theme.TEAL,        1),
            ("",                                  None,              1),
            ("Re-deploy + press A.",              theme.TEXT_BRIGHT, 1),
        ]
        ly = cy + 38
        for ln, col, sc in lines:
            if ln:
                lw = len(ln) * 8 * sc
                d.text(ln, (SW - lw) // 2, ly, col, scale=sc)
            ly += 10 * sc + 2

    def _draw_offline(self, d):
        msg = "offline — press A to retry"
        d.rect(20, 100, SW - 40, 40, theme.CARD, fill=True)
        d.rect(20, 100, SW - 40, 2,  theme.PRIMARY, fill=True)
        d.text("offline", (SW - 7 * 16) // 2, 108, theme.PRIMARY, scale=2)
        d.text(msg,       (SW - len(msg) * 8) // 2, 128, theme.TEXT_BRIGHT)
