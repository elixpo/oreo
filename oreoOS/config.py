def _load_env():
    env = {}
    for fname in (".env", ".env.local"):
        try:
            with open(fname) as f:
                text = f.read()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

_env = _load_env()

# OS version. tools/deploy.py auto-bumps the PATCH number on every push.
# The literal MUST stay on its own line as `VERSION = "vN.N.N"` — the
# deploy regex relies on that exact format to rewrite in place.
VERSION           = "v1.3.1"

GITHUB_USER       = "Circuit-Overtime"
DISPLAY_NAME      = "Ayushman Bhattacharya"
DESIGNATION       = "Developer @Myceli.ai"
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

WIFI_AUTO_CONNECT = True
WIFI_TX_DBM       = 11
WIFI_POWERSAVE    = True
BT_ADV_INTERVAL_MS = 500
APP_CATEGORIES = (
    ("Games",  "cat_games",  ("flappy", "snake", "racer", "pet")),
    ("GitHub", "cat_github", ("badge",  "identity", "commits")),
    ("Utils",  "cat_utils",  ("weather",)),
    ("Tools",  "cat_tools",  ("gallery", "color_picker", "gamepad", "quest")),
    ("System", "cat_system", ("settings", "about")),
)
