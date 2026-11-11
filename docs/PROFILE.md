# Your profile on the badge

Badge, Identity, Commits, Weather and the clock show the owner's details:
GitHub user, name, title, timezone and weather location. Nothing is set
by default, so a new badge shows a setup hint instead of someone else's
profile.

## The keys

| Key | Used by | Example |
|---|---|---|
| `GITHUB_USER` | Badge, Commits, Identity | `octocat` |
| `DISPLAY_NAME` | Identity | `Mona Lisa` |
| `DESIGNATION` | Identity (line under the name) | `Firmware @ Example` |
| `TIMEZONE_OFFSET` | the clock, after each time sync | `5.5`, `-4` |
| `WEATHER_LAT`, `WEATHER_LON` | Weather | `12.97`, `77.59` |
| `WEATHER_NAME` | Weather (optional label) | `Bengaluru` |
| `OWM_API_KEY` | Weather ([OpenWeatherMap](https://openweathermap.org/api) key) | |

## Where the badge looks

`oreoOS/profile.py` returns the first non-empty value from:

1. **`/profile.json` on the badge.** A flat JSON object with the keys
   above. This is the one to use if you did not build the OS yourself.
2. **`/secrets.py` on the badge**, written by `tools/deploy.py` from your
   `.env.local` (copy [`.env.example`](../.env.example)).
3. The app's own fallback (for example `octocat`).

### Set it over USB

Write the file on your computer and copy it to the badge:

```bash
cat > profile.json <<'EOF'
{"GITHUB_USER": "octocat", "DISPLAY_NAME": "Mona Lisa",
 "TIMEZONE_OFFSET": 5.5, "WEATHER_LAT": 12.97, "WEATHER_LON": 77.59}
EOF
mpremote cp profile.json :/profile.json
mpremote reset
```

Or from the badge's REPL:

```python
from oreoOS import profile
profile.save({"GITHUB_USER": "octocat", "TIMEZONE_OFFSET": 5.5})
profile.save({"DESIGNATION": ""})      # "" removes a key
```

`save()` rejects unknown keys and non-numeric values for the number
keys. Apps read the file when they open; the timezone applies at the
next time sync (boot, or **Sync Time** in Settings or the C panel).

### Set it at deploy time

```bash
cp .env.example .env.local     # git-ignored
$EDITOR .env.local             # GITHUB_USER=..., TIMEZONE_OFFSET=...
python tools/deploy.py /dev/ttyACM0
```

`/profile.json` still wins over these, so a value set on the badge is
not overwritten by a redeploy.

## For app developers

```python
from oreoOS import profile
profile.get("GITHUB_USER", "octocat")
profile.is_set_up()        # True once GITHUB_USER is set
```

Read the profile through this module, not `from secrets import ...`, so
both sources work.
