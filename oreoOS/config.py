from pathlib import Path


def _load_env():
    env = {}
    for fname in (".env", ".env.local"):
        p = Path(fname)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

_env = _load_env()

# OS version. tools/deploy.py auto-bumps the PATCH number on every push.
# The literal MUST stay on its own line as `VERSION = "vN.N.N"` — the
# deploy regex relies on that exact format to rewrite in place.
VERSION           = "v1.2.21"

GITHUB_USER       = "Circuit-Overtime"
DISPLAY_NAME      = "Ayushman Bhattacharya"
DESIGNATION       = "Founder, Elixpo"
WEATHER_LAT       = 22.57
WEATHER_LON       = 88.36
WEATHER_NAME      = ""
BT_AUTO_ENABLE    = False

# Local timezone offset from UTC, in hours. India = +5.5, GMT = 0, EST = -5.
# Applied after NTP sync so the home-screen clock reads correctly.
TIMEZONE_OFFSET   = 5.5

WIFI_SSID         = _env.get("WIFI_SSID", "")
WIFI_PASSWORD     = _env.get("WIFI_PASSWORD", "")
OWM_API_KEY       = _env.get("OWM_API_KEY", "")

WIFI_AUTO_CONNECT = bool(WIFI_SSID)
