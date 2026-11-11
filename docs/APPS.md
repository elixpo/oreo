# Writing apps for OreoOS

This is the in-repo guide to building an app for the Oreo badge: the
folder layout, the lifecycle, input, drawing, saving state, the network,
and how to check and ship an app. The website page
(<https://oreo.elixpo.com/docs/apps/>) covers the same ground with more
pictures; when the two disagree, this file and the code win.

## The shortest path

```bash
cp -r app_templates apps_market/my_app        # or apps/my_app for a built-in
$EDITOR apps_market/my_app/manifest.json      # name, description, author
$EDITOR apps_market/my_app/src/app.py         # your code
python3 tools/app_icon.py apps_market/my_app  # icon.png -> the badge's icon module
python3 tools/validate_app.py apps_market/my_app
```

Then put it on a badge over USB (see [CLI.md](CLI.md) for the `oreo`
tool, or `python tools/deploy.py` for the whole OS) and open it from the
Apps drawer. For the App Store, also run `python3 tools/build_store_index.py`
(see [`apps_market/README.md`](../apps_market/README.md)).

## Folder layout

```
my_app/
├── __init__.py          empty; makes the folder a package
├── main.py              one line: from .src.app import App
├── manifest.json        name, version, description, icon, author
├── icon.png             any size; tools/app_icon.py converts it
├── README.md            what it does, the controls, a screenshot
├── src/
│   ├── __init__.py
│   └── app.py           class App(oreoOS.App)
└── assets/
    ├── raw/             source art (stays in the repo)
    └── optimized/       generated .py modules (go to the badge)
```

The launcher imports `apps.<id>.main` and reads `App` from it. The app
id is the manifest `"slug"` if there is one, else the folder name, and
it must be an importable name: lower-case ASCII letters, digits and `_`,
starting with a letter. A folder name with a space (like
`apps_market/Oreo Pet`) needs a `"slug"`.

Only these files go to the badge: `__init__.py`, `main.py`,
`manifest.json`, `src/**/*.py` (and `.mpy`), and `assets/optimized/*.py`.
PNGs and READMEs stay on your computer.

### manifest.json

```json
{
  "name":        "My App",
  "slug":        "my_app",
  "type":        "app",
  "version":     "0.1.0",
  "description": "One sentence: what it does and how to use it.",
  "icon":        "my_app_icon.png",
  "author":      "your-github-handle"
}
```

`name` and `version` are required. Bump `version` when you change an
App Store app: badges only offer the update when it goes up.

### Icons

The badge cannot decode PNG, so tiles use a 32x32 RGB565 Python module.
Put any `icon.png` in the app folder and run:

```bash
python3 tools/app_icon.py apps_market/my_app
```

It writes `assets/optimized/<icon stem>.py`, fitting the image into
32x32 on the theme background. Without it the tile shows the app's first
letter. Needs Pillow on your computer (`pip install pillow`).

## The lifecycle

```python
import oreoOS
from oreoOS import api, state, theme, widgets

class App(oreoOS.App):
    name = "My App"

    def on_enter(self, os):        # once, when the app opens
        self.os = os
        self._dirty = True

    def update(self, dt):          # every frame; dt = seconds since the last
        ...

    def draw(self, d):             # every frame, after update()
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "MY APP")
        self._dirty = False

    def on_button_press(self, btn):
        ...

    def on_exit(self):             # once, when the app closes (also after a crash)
        ...
```

The OS runs one loop: read buttons, call `on_button_press` /
`on_button_release`, then `update(dt)`, then `draw(d)`, then presents the
frame. Rules that keep the badge responsive:

- **Never call `d.present()`.** The OS presents once per frame.
- **Never block.** Anything slower than a few milliseconds in `update` or
  `draw` freezes input. Split long work across frames, or use the network
  helpers below, which already run off the UI thread.
- **Move by time, not frames.** Multiply speeds by `dt` so the app runs
  the same at 20 or 60 frames per second.
- **Redraw only when something changed.** Keep a `self._dirty` flag. A
  full-screen flush is the most expensive thing in a frame. To flush only
  part of the screen, set `self._present_region = (x, y, w, h)` in
  `draw()`; the OS calls `invalidate()` after an overlay (the
  notification panel) covered the app, so override it if you need a full
  repaint then.

### Class attributes the OS reads

| Attribute | Default | Meaning |
|---|---|---|
| `name` | `"unnamed"` | Shown in headers and crash screens. |
| `SHOW_LOADING` | `False` | Show the loading slide while `on_enter` runs. Set it when `on_enter` takes more than about 200 ms. |
| `CAPTURES_C` | `False` | Deliver C to the app instead of opening the notification panel. A double-tap of C still opens the panel. May be changed on the instance at runtime, for example only during play. |
| `BLOCK_IDLE` | `False` | Keep the badge from auto-sleeping while the app is open (video, a timer). |
| `realtime_mode()` | `False` | Return True only while playing media or capturing; the OS then defers its housekeeping for lower latency. |
| `on_home_press()` | not set | Return True to handle HOME yourself (for example to close a dialog). Otherwise HOME goes back to the Apps drawer. |

## Input

`btn` values are in `oreoOS.api`. The logical names say what a button
means across the OS; they are the same numbers as the physical names.

| Logical | Physical | Meaning |
|---|---|---|
| `BTN_SELECT` | `BTN_A` | confirm, open, fire, jump |
| `BTN_BACK` | `BTN_B` | cancel, up one level, close |
| `BTN_PANEL` | `BTN_C` | notification panel, unless `CAPTURES_C` |
| `BTN_HOME` | `BTN_HOME` | leaves the app; the OS handles it |
| `BTN_UP/DOWN/LEFT/RIGHT` | same | D-pad; the OS auto-repeats held D-pad presses |

For held buttons (steering, charging a jump) poll in `update()`:

```python
if self.os.buttons.is_pressed(api.BTN_LEFT):
    self.x -= SPEED * dt
```

`os.buttons` also has `just_pressed(btn)` and `just_released(btn)`.
Buttons are physical and fixed: the display does not rotate.

## Drawing

`d` is a 320x240 RGB565 framebuffer (`api.SCREEN_W`, `api.SCREEN_H`):

| Call | |
|---|---|
| `d.clear(color)` | fill the screen |
| `d.rect(x, y, w, h, color, fill=False)` | rectangle |
| `d.line(x0, y0, x1, y1, color)` / `d.pixel(x, y, color)` | |
| `d.text(s, x, y, color, scale=1)` | 8x8 font; scale 2 gives 16 px |
| `d.blit(data, x, y, w, h)` | RGB565 sprite; magenta `0xF81F` is transparent |
| `d.blit_2x(...)`, `d.blit_scale(...)` | scaled sprites |

Colours: `api.rgb(r, g, b)` packs 8-bit values; prefer the theme names
(`theme.BG`, `theme.PRIMARY`, `theme.TEXT_BRIGHT`, `theme.CARD`) so the
app matches the OS. `widgets.draw_header(d, title)` and
`widgets.draw_hint(d, "A=go  B=back")` give the standard top and bottom
bars; `widgets.play_area()` returns the space between them.
`oreoOS.pixelfont` draws the Pixelify Sans title font, and
`widgets.Scroller` gives eased, frame-rate independent scrolling.

Sprites: put PNGs in `assets/raw/` and run
`python tools/optimize_assets.py --app my_app` to make
`assets/optimized/*.py` modules, then load them with
`__import__("apps.my_app.assets.optimized.hero", None, None, ["DATA", "W", "H"])`.

## Saving state

Use `oreoOS.state` for scores, settings and progress:

```python
from oreoOS import state

APP_ID = state.app_id(__name__, "my_app")   # "apps.my_app.src.app" -> "my_app"

def on_enter(self, os):
    self.save = state.load(APP_ID, {"hi": 0, "level": 1})   # defaults on first run

def on_exit(self):
    state.save(APP_ID, self.save)
```

- Saves are JSON in `/state/<app id>.json`, outside the app folder, so
  they survive App Store updates and an uninstall and reinstall.
- Writes are atomic: a power cut during a save keeps the previous copy.
- `load()` never raises; a missing or corrupt file gives the defaults.
  `save()` returns False instead of raising (for example, flash full).
- Save on exit or at a checkpoint, not every frame: flash writes are slow.
- Values go through JSON, so tuples come back as lists.
- App Store apps: the Store serves the newest version to every badge and
  does not check the OS version, and badges on stable/v2.0.5 or older
  have no `oreoOS.state` or `oreoOS.profile`. Import them inside
  `try: ... except ImportError:` and keep a fallback (Racer, Snake and
  Weather show how), so an update cannot break the app on an older OS.

For small OS-wide preferences, `os.settings_get(key, default)` and
`os.settings_set(key, value)` persist too (in `/state/os.json`). Keys
starting with `ota_` are kept for the current boot only.

## The owner's profile

Apps that need to know who owns the badge read `oreoOS.profile`, never
`secrets.py` directly:

```python
from oreoOS import profile
login = profile.get("GITHUB_USER", "octocat")
tz = profile.get("TIMEZONE_OFFSET", 0)      # numbers come back as float
```

See [PROFILE.md](PROFILE.md) for the keys and how an owner sets them.

## The network

Wi-Fi is for the internet: the App Store, updates, GitHub data, weather
and the clock. The OS connects in the background (`oreoOS.netsvc`); an
app never connects or scans by itself.

- Check `oreoWare.wifi.is_connected()` (or `oreoOS.github.online()`)
  before a request, and show an offline state when it is False.
- Make requests with `oreoOS._http.get_url(url, timeout_s=...)`, which
  honours its timeout, rather than `urequests`.
- For anything that can take more than a moment, use
  `oreoOS.cache.Refresh` to run it on a worker thread and show cached data
  meanwhile; `oreoOS/github.py` is the reference.
- Set `SHOW_LOADING = True` if `on_enter` must wait for data.

## When it crashes

An exception in your app shows the crash screen and returns to the
drawer. During boot, the full traceback goes to the USB serial console
and to `/crash.log` on the badge, and the crash screen shows the
innermost `file:line`. Read the log with `mpremote cat /crash.log`.
`oreoOS.crashlog.record(err, "context")` does the same from your own
`except` blocks.

## Check it

```bash
python3 tools/validate_app.py apps_market/my_app        # or no argument for every app
```

Errors mean the app will not load (bad manifest, `main.py` without
`App`, an id that cannot be imported, a syntax error, a committed
secret). Warnings are worth fixing: no icon, no README, direct
`oreoWare` / `machine` imports (prefer the `os` object, #67), calling
`present()`. CI runs it on every pull request.

Host tests for pure logic go in `tests/` and run with
`python3 -m unittest discover -s tests`. Badge code runs on MicroPython
1.28: no `abc`, `typing`, f-string `=` debugging, `str.isalnum()`, or
large libraries. Compile-check with `mpy-cross` if you have it.

## Pull request checklist

- [ ] `python3 tools/validate_app.py <your app>` passes with no errors.
- [ ] `README.md` in the app folder: one sentence on what it does, the
      controls, and a screenshot or photo of the badge.
- [ ] Controls follow the table above (A selects, B goes back, HOME exits).
- [ ] Movement uses `dt`; `draw()` skips frames when nothing changed.
- [ ] State goes through `oreoOS.state`; no files written into the app folder.
- [ ] No secrets, tokens or personal data in the code.
- [ ] App Store apps: `tools/build_store_index.py` run, `index.json`
      entry filled in, `version` bumped on changes.
