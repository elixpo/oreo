"""App Store: discover, install, update and remove apps.

Pages (B switches):
  Discover   featured card (LEFT/RIGHT cycles it) and every catalogue app,
             each with its icon, name, tagline, category, size and an
             INSTALL / OPEN / UPDATE state.
  Installed  every app on the badge. Built-in apps can only be opened;
             others can be updated or uninstalled (with a confirm step).

A on a row opens the app's detail page (icon, name, author, version,
size, description and the actions). B or HOME goes back.

Speed: the catalogue cached on flash is drawn on the first frame; the
refresh from GitHub (one small JSON file) and any missing icons are
fetched afterwards from update(), one request per frame, while the
cached list is already on screen. Selection moves repaint only the two
rows involved.
"""

import gc
import time
import oreoOS
from oreoOS import api, store
from . import render as R

DISCOVER = 0
INSTALLED = 1

LABEL = {store.INSTALL: "INSTALL", store.OPEN: "OPEN",
         store.UPDATE: "UPDATE"}


class App(oreoOS.App):
    name = "App Store"
    author = "Circuit-Overtime"

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os = os_
        self._page = DISCOVER
        self._view = "list"          # list | detail | confirm
        self._sel = [0, 0]
        self._top = [0, 0]
        self._feat_i = 0
        self._icons = {}             # id → (data, w, h) | False
        self._big = {}               # id → 2x icon (at most two kept)
        self._queue = []             # entries whose icon to download
        self._queued = set()
        self._sizes = {}             # installed id → bytes on flash
        self._status = ""
        self._frames = 0
        self._paint = "full"         # full | rows | None
        self._paint_rows = ()
        self._entry = None           # detail page entry
        self._actions = []
        self._act = 0
        self._confirm_sel = 0
        self._note = ""
        self._busy = False
        self._prog_ms = 0
        self._installed = []
        self._dirty = False          # set by the OS after an overlay closes
        store.forget_installed()
        self._load_rows()
        self._want_refresh = store.needs_refresh()
        if not store.wifi_up():
            self._status = "OFFLINE" if self._apps else ""
            self._want_refresh = False
        # Settings may ask for an app's page (store.open_app). Without a
        # cached catalogue it is opened once the refresh has loaded one.
        self._pending = store.take_pending()
        self._open_pending()

    def _open_pending(self):
        if not self._pending:
            return
        e = store.find(self._pending)
        if e is not None:
            self._pending = None
            self._open_detail(e)
        elif not self._want_refresh:
            self._pending = None

    # ── data ───────────────────────────────────────────────────────────

    def _load_rows(self):
        apps, featured = store.catalogue()
        self._apps = apps
        self._featured = [store.find(f) for f in featured]
        self._featured = [e for e in self._featured if e]
        if self._feat_i >= len(self._featured):
            self._feat_i = 0
        self._installed = store.list_installed()
        self._clamp()

    def _rows(self, page=None):
        page = self._page if page is None else page
        if page == DISCOVER:
            return (1 if self._featured else 0) + len(self._apps)
        return len(self._installed)

    def _clamp(self):
        for p in (DISCOVER, INSTALLED):
            n = self._rows(p)
            if self._sel[p] >= n:
                self._sel[p] = max(0, n - 1)
            if self._top[p] > self._sel[p]:
                self._top[p] = self._sel[p]

    def _discover_entry(self, i):
        """(kind, entry) for a Discover row index."""
        if self._featured:
            if i == 0:
                return "feat", self._featured[self._feat_i]
            i -= 1
        return "app", self._apps[i]

    def _installed_entry(self, i):
        """Catalogue entry for an installed app, or one built from its
        manifest when it is built in or side-loaded."""
        a = self._installed[i]
        e = store.find(a["dir"])
        if e is not None:
            return e
        m = store.installed_manifest(a["dir"]) or {}
        return {
            "id": a["dir"], "name": a.get("name") or a["dir"],
            "tagline": m.get("description") or "",
            "description": m.get("description") or "",
            "category": "System" if store.is_default(a["dir"]) else "",
            "author": a.get("author") or "", "icon": a.get("icon") or "",
            "version": str(m.get("version") or "0"), "size": 0,
            "files": [], "data": None, "local": True,
        }

    def _icon(self, e):
        k = e["id"]
        ico = self._icons.get(k)
        if ico is None:
            ico = store.local_icon(k, e.get("icon")) or False
            self._icons[k] = ico
            if not ico and e.get("icon") and not e.get("local") \
               and k not in self._queued:
                self._queued.add(k)
                self._queue.append(e)
        return ico or None

    def _big_icon(self, e):
        k = e["id"]
        if k not in self._big:
            ico = self._icon(e)
            if len(self._big) >= 2:
                self._big.clear()
            if ico and ico[1] <= 32 and ico[2] <= 32:
                ico = R.upscale2x(ico[0], ico[1], ico[2])
            self._big[k] = ico
        return self._big[k]

    def _size(self, app_id):
        if app_id not in self._sizes:
            self._sizes[app_id] = store.installed_size(app_id)
        return self._sizes[app_id]

    # ── background work ────────────────────────────────────────────────

    def update(self, dt):
        if self._frames < 2:
            self._frames += 1        # let the cached list reach the screen
            return
        if self._busy or self._view == "confirm":
            return
        if self._want_refresh:
            self._want_refresh = False
            self._refresh()
        elif self._queue:
            e = self._queue.pop(0)
            if store.fetch_icon(e):
                self._icons.pop(e["id"], None)
                self._big.pop(e["id"], None)
                self._paint = "full"

    def _refresh(self):
        self._status = "UPDATING"
        self._paint_now_header()
        keep = self._current_id()
        ok = store.refresh()
        self._status = "" if ok else (
            "OFFLINE" if store.last_error() == "offline" else "ERROR")
        self._load_rows()
        self._icons.clear()
        self._big.clear()
        self._queued.clear()
        self._queue = []
        if keep and self._view == "list":
            self._select_id(keep)
        if self._view == "list":
            self._open_pending()
        else:
            self._pending = None
        gc.collect()
        self._paint = "full"

    def _current_id(self):
        n = self._rows()
        if not n:
            return None
        i = self._sel[self._page]
        if self._page == DISCOVER:
            kind, e = self._discover_entry(i)
            return None if kind == "feat" else e["id"]
        return self._installed[i]["dir"]

    def _select_id(self, app_id):
        for i in range(self._rows()):
            if self._page == DISCOVER:
                kind, e = self._discover_entry(i)
                if kind == "app" and e["id"] == app_id:
                    break
            elif self._installed[i]["dir"] == app_id:
                break
        else:
            return
        self._sel[self._page] = i
        self._scroll()

    # ── input ──────────────────────────────────────────────────────────

    def on_home_press(self):
        """HOME backs out of the detail page / dialog; on a list it exits."""
        if self._busy:
            return True
        if self._view == "confirm":
            self._view = "detail"
            self._paint = "full"
            return True
        if self._view == "detail":
            self._back()
            return True
        return False

    def on_button_press(self, btn):
        if self._busy:
            return
        if self._view == "confirm":
            self._btn_confirm(btn)
        elif self._view == "detail":
            self._btn_detail(btn)
        else:
            self._btn_list(btn)

    def _btn_list(self, btn):
        p = self._page
        if btn == api.BTN_B:
            self._page = 1 - p
            if self._page == INSTALLED:
                self._installed = store.list_installed()
                self._clamp()
            self._paint = "full"
            return
        n = self._rows()
        if not n:
            if btn == api.BTN_A and store.wifi_up():
                self._want_refresh = True
            return
        old = self._sel[p]
        if btn == api.BTN_UP and old > 0:
            self._move(old - 1)
        elif btn == api.BTN_DOWN and old < n - 1:
            self._move(old + 1)
        elif btn in (api.BTN_LEFT, api.BTN_RIGHT) and p == DISCOVER \
                and old == 0 and len(self._featured) > 1:
            step = 1 if btn == api.BTN_RIGHT else -1
            self._feat_i = (self._feat_i + step) % len(self._featured)
            self._mark_rows(0)
        elif btn == api.BTN_A:
            if p == DISCOVER:
                self._open_detail(self._discover_entry(old)[1])
            else:
                self._open_detail(self._installed_entry(old))

    def _move(self, new):
        p = self._page
        old = self._sel[p]
        self._sel[p] = new
        top = self._top[p]
        self._scroll()
        if self._top[p] != top:
            self._paint = "full"
        else:
            self._mark_rows(old, new)

    def _mark_rows(self, *rows):
        """Queue rows for repaint, merging with rows already queued."""
        if self._paint == "full":
            return
        if self._paint == "rows":
            rows = tuple(set(self._paint_rows) | set(rows))
        self._paint = "rows"
        self._paint_rows = rows

    def _scroll(self):
        p = self._page
        sel = self._sel[p]
        if sel < self._top[p]:
            self._top[p] = sel
        while self._top[p] < sel and \
                sel not in [r[0] for r in self._layout()]:
            self._top[p] += 1

    def _layout(self):
        """[(row index, y, height)] of the rows that fit on screen."""
        p = self._page
        out = []
        y = R.TOP + 2
        i = self._top[p]
        n = self._rows()
        while i < n:
            h = R.FEAT_H if (p == DISCOVER and self._featured and i == 0) \
                else R.ROW_H
            if y + h > R.BOTTOM:
                break
            out.append((i, y, h))
            y += h + R.GAP
            i += 1
        return out

    # ── detail page ────────────────────────────────────────────────────

    def _open_detail(self, e):
        self._entry = e
        self._view = "detail"
        self._note = ""
        self._set_actions()
        self._paint = "full"

    def _set_actions(self):
        e = self._entry
        built_in = store.is_default(e["id"])
        installed = store.is_installed(e["id"])
        acts = []
        if e.get("local") or built_in:
            if installed:
                acts.append(("Open", False))
        else:
            state = store.app_state(e)
            if state == store.INSTALL:
                acts.append(("Install", False))
            elif state == store.UPDATE:
                acts.append(("Update", False))
        if installed and ("Open", False) not in acts:
            acts.append(("Open", False))
        if installed and not built_in:
            acts.append(("Uninstall", True))
        self._actions = acts
        self._act = 0
        if built_in and not self._note:
            self._note = "Built-in app: it can't be uninstalled."

    def _back(self):
        self._view = "list"
        self._entry = None
        self._big.clear()
        self._installed = store.list_installed()
        self._sizes.clear()
        self._clamp()
        self._paint = "full"

    def _btn_detail(self, btn):
        if btn == api.BTN_B:
            self._back()
        elif btn in (api.BTN_LEFT, api.BTN_RIGHT) and self._actions:
            step = 1 if btn == api.BTN_RIGHT else -1
            self._act = (self._act + step) % len(self._actions)
            self._paint = self._paint or "buttons"
        elif btn == api.BTN_A and self._actions:
            label = self._actions[self._act][0]
            if label == "Open":
                self._launch()
            elif label == "Uninstall":
                self._view = "confirm"
                self._confirm_sel = 0        # Cancel is the default
                self._paint = "full"
            else:
                self._install()

    def _btn_confirm(self, btn):
        if btn == api.BTN_B:
            self._view = "detail"
            self._paint = "full"
        elif btn in (api.BTN_LEFT, api.BTN_RIGHT):
            self._confirm_sel = 1 - self._confirm_sel
            self._paint = "full"
        elif btn == api.BTN_A:
            self._view = "detail"
            if self._confirm_sel == 1:
                ok, msg = store.uninstall(self._entry["id"])
                self._note = ("Uninstalled. Reinstall it from Discover."
                              if ok else "Uninstall failed: " + msg)
                self._set_actions()
                if ok and self._entry.get("local"):
                    self._actions = []
            self._paint = "full"

    def _launch(self):
        try:
            self._os.launch(self._entry["id"])
        except Exception:
            self._note = "Couldn't open the app."
            self._paint = "full"

    def _install(self):
        e = self._entry
        self._busy = True
        self._note = ""
        self._prog_ms = 0
        self._on_progress(0, store.total_size(e), "Starting")
        gc.collect()
        try:
            ok, msg = store.install(e["id"], self._on_progress)
        except Exception as ex:
            ok, msg = False, str(ex)
        self._busy = False
        self._sizes.clear()
        self._icons.pop(e["id"], None)
        self._note = "Installed." if ok else "Install failed: " + msg
        self._set_actions()
        gc.collect()
        self._paint = "full"

    def _on_progress(self, received, total, label):
        """Repaint only the progress bar, at most every 120 ms."""
        now = time.ticks_ms()
        if self._prog_ms and received < total and \
           time.ticks_diff(now, self._prog_ms) < 120:
            return
        self._prog_ms = now
        d = self._os.display
        try:
            R.progress(d, label, received, total)
            d.present()
        except Exception:
            pass

    # ── render ─────────────────────────────────────────────────────────

    def _paint_now_header(self):
        d = self._os.display
        try:
            R.header(d, self._status)
            d.present()
        except Exception:
            pass

    def draw(self, d):
        if self._dirty:
            # The notification panel or pair prompt painted over us.
            self._dirty = False
            self._paint = "full"
        paint = self._paint
        if not paint:
            return
        self._paint = None
        if self._view == "list":
            if paint == "rows":
                lay = dict((i, (y, h)) for i, y, h in self._layout())
                for i in self._paint_rows:
                    if i in lay:
                        self._draw_row(d, i, lay[i][0])
                return
            d.clear(R.theme.BG)
            R.header(d, self._status)
            R.tabs(d, self._page)
            self._draw_list(d)
            return
        e = self._entry
        if paint == "buttons" and self._view == "detail":
            R.buttons(d, self._actions, self._act)
            return
        d.clear(R.theme.BG)
        R.header(d, self._status)
        R.detail(d, self._big_icon(e), e, self._meta(e), self._note)
        R.buttons(d, self._actions, self._act)
        if self._view == "confirm":
            R.confirm(d, e["name"], self._confirm_lines(e),
                      self._confirm_sel)
            R.hint(d, "L/R=choose  A=confirm  B=cancel")
        else:
            R.hint(d, "L/R=choose  A=select  B=back")

    def _meta(self, e):
        parts = []
        local = store.installed_version(e["id"])
        if local is not None and not e.get("local") \
           and store.is_newer(e["version"], local):
            parts.append("v%s > v%s" % (local, e["version"]))
        else:
            parts.append("v" + (e.get("version") or "0"))
        if e.get("local"):
            parts.append(R.fmt_size(self._size(e["id"])))
        elif store.total_size(e):
            parts.append(R.fmt_size(store.total_size(e)))
        return "  ".join(parts)

    def _confirm_lines(self, e):
        lines = [e["name"] + " and its files will", "be deleted from this badge.",
                 "", "You can reinstall it later",
                 "from Discover."]
        if e.get("local"):
            lines[3:] = ["It isn't in the catalogue,", "so it can't be reinstalled."]
        return lines

    def _draw_list(self, d):
        if not self._rows():
            if self._page == DISCOVER:
                if store.wifi_up():
                    lines = ("Loading the catalogue...",
                             "A = try again")
                else:
                    lines = ("No apps to show yet",
                             "Connect to WiFi in Settings",
                             "to browse the App Store.")
            else:
                lines = ("No apps installed",)
            R.empty(d, lines)
            return
        for i, y, _h in self._layout():
            self._draw_row(d, i, y)

    def _draw_row(self, d, i, y):
        sel = (i == self._sel[self._page])
        if self._page == DISCOVER:
            kind, e = self._discover_entry(i)
            label = LABEL[store.app_state(e)]
            if kind == "feat":
                R.featured(d, y, sel, self._big_icon(e), e, label,
                           len(self._featured), self._feat_i)
                return
            size = store.total_size(e)
            meta = e["category"] + ("  " + R.fmt_size(size) if size else "")
            R.row(d, y, sel, self._icon(e), e["name"], e["tagline"], meta,
                  label, e["category"])
            return
        e = self._installed_entry(i)
        app_id = e["id"]
        if store.is_default(app_id):
            meta, label = "Built-in", "BUILT-IN"
        else:
            meta = "%s  %s" % (e.get("category") or "Sideloaded",
                               R.fmt_size(self._size(app_id)))
            label = "UPDATE" if (not e.get("local") and
                                 store.app_state(e) == store.UPDATE) \
                else "OPEN"
        R.row(d, y, sel, self._icon(e), e["name"], e.get("tagline"), meta,
              label, e.get("category"))
