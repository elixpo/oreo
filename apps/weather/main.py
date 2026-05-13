"""Weather — fetch live conditions over WiFi from Open-Meteo (no API key).

Defaults to a "demo" placeholder when WiFi isn't up. Updates every 10 min
while the app is open. Press A to force refresh.
"""

import time
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

# Latitude/longitude default — Bengaluru. User can override via secrets.py:
#   WEATHER_LAT = 12.97
#   WEATHER_LON = 77.59
DEFAULT_LAT = 12.97
DEFAULT_LON = 77.59
REFRESH_SEC = 600

# Open-Meteo weather code → ascii icon + label (we draw procedurally; no asset).
_CODE_MAP = {
    0:  ("sun",       "Clear"),
    1:  ("sun",       "Mainly clear"),
    2:  ("partly",    "Partly cloudy"),
    3:  ("cloud",     "Overcast"),
    45: ("fog",       "Fog"),
    48: ("fog",       "Fog"),
    51: ("drizzle",   "Drizzle"),
    61: ("rain",      "Rain"),
    63: ("rain",      "Rain"),
    65: ("rain",      "Heavy rain"),
    71: ("snow",      "Snow"),
    80: ("rain",      "Showers"),
    95: ("storm",     "Thunder"),
}


def _fetch_weather(lat, lon):
    try:
        import urequests
        url = ("https://api.open-meteo.com/v1/forecast"
               "?latitude=%.3f&longitude=%.3f"
               "&current=temperature_2m,weather_code,wind_speed_10m" % (lat, lon))
        r   = urequests.get(url, headers={"User-Agent": "ElixpoBadge"})
        j   = r.json(); r.close()
        cur = j.get("current", {})
        return {
            "temp":  float(cur.get("temperature_2m", 0)),
            "code":  int(cur.get("weather_code", 0)),
            "wind":  float(cur.get("wind_speed_10m", 0)),
        }
    except Exception:
        return None


def _draw_icon(d, x, y, key, anim_t):
    """Procedural condition icon (~96×96) drawn with rects. Cheap + animated."""
    if key == "sun":
        cx, cy, r = x + 48, y + 48, 22
        d.rect(cx - r, cy - r, r * 2, r * 2, theme.GOLD, fill=True)
        # rays
        for i, (dx, dy) in enumerate([(-40, 0), (40, 0), (0, -40), (0, 40),
                                      (-30, -30), (30, -30), (-30, 30), (30, 30)]):
            d.rect(cx + dx - 4, cy + dy - 4, 8, 8, theme.GOLD, fill=True)
    elif key == "partly":
        d.rect(x + 12, y + 36, 40, 40, theme.GOLD, fill=True)
        d.rect(x + 20, y + 32, 64, 32, theme.CARD, fill=True)
    elif key in ("cloud", "fog"):
        d.rect(x + 8,  y + 36, 80, 32, theme.CARD, fill=True)
        d.rect(x + 20, y + 20, 56, 32, theme.CARD, fill=True)
    elif key == "drizzle" or key == "rain":
        d.rect(x + 8,  y + 28, 80, 28, theme.CARD, fill=True)
        offset = int((anim_t * 60) % 12)
        for dx in (10, 28, 46, 64):
            d.rect(x + dx, y + 60 + offset, 4, 12, theme.TEAL, fill=True)
    elif key == "snow":
        d.rect(x + 8, y + 28, 80, 28, theme.CARD, fill=True)
        for dx in (16, 36, 56, 76):
            d.rect(x + dx, y + 64, 4, 4, api.WHITE, fill=True)
    elif key == "storm":
        d.rect(x + 8, y + 24, 80, 28, theme.MUTED, fill=True)
        # lightning
        if int(anim_t * 3) % 2 == 0:
            d.rect(x + 44, y + 56, 6, 18, theme.GOLD, fill=True)
            d.rect(x + 38, y + 70, 6, 12, theme.GOLD, fill=True)


class App(lix.App):
    name = "Weather"
    SHOW_LOADING = True

    def on_enter(self, os):
        self._os         = os
        self._anim_t     = 0.0
        self._last_fetch = 0
        self._data       = None
        self._error      = None
        try:
            from secrets import WEATHER_LAT, WEATHER_LON
            self._lat, self._lon = WEATHER_LAT, WEATHER_LON
        except Exception:
            self._lat, self._lon = DEFAULT_LAT, DEFAULT_LON
        self._refresh()
        self._dirty = True

    def _refresh(self):
        self._data  = _fetch_weather(self._lat, self._lon)
        self._error = None if self._data else "offline"
        self._last_fetch = time.ticks_ms()
        self._dirty = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            self._refresh()

    def update(self, dt):
        self._anim_t += dt
        # Periodic refresh
        if time.ticks_diff(time.ticks_ms(), self._last_fetch) > REFRESH_SEC * 1000:
            self._refresh()
        # Animate every ~150 ms
        if int(self._anim_t * 6) != int((self._anim_t - dt) * 6):
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "WEATHER")
        widgets.draw_hint  (d, "A=refresh  HOME=back")

        if self._data is None:
            d.text("offline", (SW - 7 * 16) // 2, 100, theme.MUTED,    scale=2)
            d.text("Press A to retry", (SW - 16 * 8) // 2, 140, theme.TEXT_BRIGHT)
            self._dirty = False
            return

        # Icon on the left
        key, label = _CODE_MAP.get(self._data["code"], ("partly", "Unknown"))
        _draw_icon(d, 24, widgets.HEADER_H + 30, key, self._anim_t)

        # Temperature + label on the right
        col_x = 150
        y     = widgets.HEADER_H + 30
        t_str = "%d C" % round(self._data["temp"])
        d.text(t_str, col_x, y, theme.PRIMARY, scale=4); y += 36
        d.text(label[:16], col_x, y, theme.TEXT_BRIGHT, scale=2); y += 22
        d.text("wind %.0f km/h" % self._data["wind"], col_x, y, theme.MUTED)

        self._dirty = False
