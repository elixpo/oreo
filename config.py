from pathlib import Path

def _load_env():
    env = {}
    for f in (".env", ".env.local"):
        p = Path(f)
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env

_e = _load_env()

WIFI_SSID         = _e.get("WIFI_SSID", "")
WIFI_PASSWORD     = _e.get("WIFI_PASSWORD", "")
WIFI_AUTO_CONNECT = bool(WIFI_SSID)

BT_AUTO_ENABLE    = False
