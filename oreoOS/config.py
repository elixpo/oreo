def _load_env():
    """Read .env / .env.local from cwd. Returns {} on MicroPython (no `.env`
    on the device — secrets.py is generated at deploy time instead).

    Done with plain `open()` rather than `pathlib` because MicroPython
    doesn't ship `pathlib`; a top-level `from pathlib import Path` here
    would crash the entire boot chain when launcher.py does
    `from oreoOS.config import VERSION`.
    """
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
VERSION           = "v1.2.40"

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

# ── radio power budget ──────────────────────────────────────────────────────
# Cap the peak current drawn by WiFi+BT so big bursts don't trip the supply
# even with the dead-LDO + 2000 µF bulk-cap setup. These translate roughly
# to peak TX current:
#   WIFI_TX_DBM = 19.5 → ~240 mA peak (default, "shout the loudest")
#   WIFI_TX_DBM = 11   → ~140 mA peak (still ~30 m range indoors)
#   WIFI_TX_DBM = 8    → ~110 mA peak (~15 m range)
#   WIFI_TX_DBM = 2    → ~80 mA peak  (next-room range, ~5 m)
#
# Power-save mode lets the radio nap between AP beacons; drops idle current
# from ~100 mA to ~15 mA while still maintaining the connection. Trade-off:
# +30–100 ms wake-up latency for the first packet of a burst.
WIFI_TX_DBM       = 11
WIFI_POWERSAVE    = True

# BLE TX power is controlled indirectly via the advertising interval. Longer
# interval = less average RF activity. 500 ms is a balance between fast
# discovery and low current draw.
BT_ADV_INTERVAL_MS = 500
