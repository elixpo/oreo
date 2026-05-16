"""Updates — single page for everything version-related.

Reached from:
  * Settings → Version (replaces the old Check / Install rows)
  * About    → tap the version line
  * Notification panel → OTA notification

What it shows:
  * Current OS version (from oreoOS/config.py / launcher.VERSION)
  * On entry, auto-runs `ota.check()` so the page is meaningful
    without an extra tap. Status line reflects state of the check.
  * If a newer release exists, displays its tag + size + release-notes
    excerpt (`body` field from the GitHub releases API — the same text
    that shows on the GitHub Releases page).
  * Install button is *only* active when a newer release is staged
    or downloadable; otherwise it's a dim disabled chip.

Controls:
  UP / DOWN  pick a row (Refresh / Install)
  A          activate the focused row
  HOME       back to launcher
"""

import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

ROW_PAD_X    = 12
HEADER_Y     = widgets.HEADER_H + 6

# Layout slots — top block is read-only state, bottom is two action rows.
VER_Y        = HEADER_Y
VER_H        = 44
NOTES_Y      = VER_Y + VER_H + 6
NOTES_H      = 90
ACTION_TOP_Y = NOTES_Y + NOTES_H + 10
ACTION_H     = 22
ACTION_GAP   = 6

# States the page can be in. Maps to the OTA settings dict but with a
# UX-meaningful name so the renderer can switch on it directly.
S_IDLE          = "idle"
S_CHECKING      = "checking"
S_UP_TO_DATE    = "up_to_date"
S_AVAILABLE     = "available"
S_DOWNLOADING   = "downloading"
S_READY         = "ready"
S_FAILED        = "failed"


class App(oreoOS.App):
    name         = "Updates"
    author       = "Circuit-Overtime"
    SHOW_LOADING = True

    # Logical action rows (selectable).
    ROW_REFRESH, ROW_INSTALL = 0, 1
    ROWS = (ROW_REFRESH, ROW_INSTALL)

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os    = os_
        self._sel   = self.ROW_REFRESH
        self._dirty = True

        # State backing the rendering. _release / _peeked are cached
        # results of ota.check() and ota.peek() so we don't refetch on
        # every redraw.
        self._state    = S_IDLE
        self._release  = None
        self._peeked   = None
        self._error    = ""

        # Auto-run the check on entry — most users open this page
        # because they want to know whether there's an update, so
        # making them press A immediately is friction.
        self._run_check()

    # ── input ──────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if btn == api.BTN_HOME:
            self._os.quit()
            return
        if btn == api.BTN_UP:
            self._sel = (self._sel - 1) % len(self.ROWS)
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + 1) % len(self.ROWS)
        elif btn == api.BTN_A:
            self._activate()
        else:
            return
        self._dirty = True

    def _activate(self):
        r = self._sel
        if r == self.ROW_REFRESH:
            self._run_check()
        elif r == self.ROW_INSTALL and self._install_enabled():
            self._run_install()

    def _install_enabled(self):
        """Install row is active only when there's a discovered release
        we can either re-download or apply on reboot."""
        return self._state in (S_AVAILABLE, S_READY)

    # ── OTA wrappers ───────────────────────────────────────────────────
    def _run_check(self):
        try:
            from oreoOS import ota
        except Exception:
            self._state = S_FAILED
            self._error = "ota module missing"
            return

        self._state = S_CHECKING
        self._dirty = True
        # Paint the "checking" state before the synchronous HTTP fires
        # so the user sees feedback during the (up to T_GH_API seconds)
        # network round-trip.
        try:
            self.draw(self._os.display)
            self._os.display.present()
        except Exception:
            pass

        rel = self._safe(lambda: ota.check())
        if not rel:
            self._state = S_UP_TO_DATE
            try:
                self._os.settings_set("ota_status", "up-to-date")
            except Exception:
                pass
            self._dirty = True
            return

        # Surface the discovery in the global notification ring AND
        # peek so we know the byte count + whether the patch is small.
        try:
            ota.push_update_notification(rel.get("version", ""))
        except Exception:
            pass
        peeked = self._safe(lambda: ota.peek(rel))
        if not peeked:
            self._state = S_FAILED
            self._error = "couldn't read manifest"
            self._dirty = True
            return

        self._release = rel
        self._peeked  = peeked

        try:
            self._os.settings_set("ota_pending_version", rel.get("version", ""))
            self._os.settings_set("ota_pending_bytes",   peeked["bytes"])
            self._os.settings_set("ota_pending_major",   peeked["major"])
            self._os.settings_set("ota_pending_changed", len(peeked["changed"]))
            self._os.settings_set("ota_pending_url",     rel["manifest_url"])
            self._os.settings_set("ota_status",          "available")
        except Exception:
            pass

        self._state = S_AVAILABLE
        self._dirty = True

    def _run_install(self):
        try:
            from oreoOS import ota
        except Exception:
            self._state = S_FAILED
            return
        # If the bytes are already staged, just reboot — the boot path
        # applies them. Otherwise download first.
        if not ota.is_pending():
            if not self._peeked:
                # Reflect a fresh check that might've expired between
                # opening the page and pressing Install.
                rel = self._safe(lambda: ota.check())
                if not rel:
                    self._state = S_UP_TO_DATE
                    self._dirty = True
                    return
                self._peeked = self._safe(lambda: ota.peek(rel))
                if not self._peeked:
                    self._state = S_FAILED
                    self._dirty = True
                    return
            self._state = S_DOWNLOADING
            self._dirty = True
            try:
                self.draw(self._os.display); self._os.display.present()
            except Exception:
                pass
            ok = self._safe(lambda: ota.download(self._peeked))
            if not ok:
                self._state = S_FAILED
                self._error = "download failed"
                try: self._os.settings_set("ota_status", "download-failed")
                except Exception: pass
                self._dirty = True
                return
            try: self._os.settings_set("ota_status", "ready")
            except Exception: pass
            self._state = S_READY
        try:
            self._os.settings_set("ota_pending_peek_ok", False)
        except Exception:
            pass
        # Boot path applies the staged manifest before the launcher runs.
        try:
            import machine
            machine.reset()
        except Exception:
            self._os.quit()

    @staticmethod
    def _safe(fn):
        try:
            return fn()
        except Exception:
            return None

    # ── render ─────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "UPDATES")
        widgets.draw_hint(d, "A=run  HOME=back")

        self._draw_version_card(d)
        self._draw_notes_card(d)
        self._draw_action_row(d, self.ROW_REFRESH,
                              y=ACTION_TOP_Y,
                              label=self._refresh_label(),
                              enabled=True)
        self._draw_action_row(d, self.ROW_INSTALL,
                              y=ACTION_TOP_Y + ACTION_H + ACTION_GAP,
                              label=self._install_label(),
                              enabled=self._install_enabled())

    def _draw_version_card(self, d):
        x, y, w, h = 6, VER_Y, SW - 12, VER_H
        d.rect(x, y, w, h, theme.CARD, fill=True)
        d.rect(x, y, w, 3, theme.PRIMARY, fill=True)
        d.text("Current", x + 8, y + 6, theme.MUTED, scale=1)
        cur = self._current_version()
        d.text(cur, x + 8, y + 20, theme.PRIMARY, scale=2)

        # State pill on the right.
        pill, pcol = self._state_pill()
        if pill:
            pw = len(pill) * 8 + 12
            d.rect(x + w - pw - 8, y + 18, pw, 16,
                   pcol, fill=True)
            d.text(pill, x + w - pw - 8 + 6, y + 22, api.WHITE, scale=1)

    def _draw_notes_card(self, d):
        x, y, w, h = 6, NOTES_Y, SW - 12, NOTES_H
        d.rect(x, y, w, h, theme.DOCK_SEL, fill=True)
        d.rect(x, y, w, 1, theme.MUTED2, fill=True)
        d.rect(x, y + h - 1, w, 1, theme.MUTED2, fill=True)

        if self._state == S_CHECKING:
            self._centred(d, "checking GitHub releases...",
                          y + h // 2 - 4, theme.MUTED)
            return
        if self._state == S_DOWNLOADING:
            self._centred(d, "downloading update bytes...",
                          y + h // 2 - 4, theme.PRIMARY)
            return
        if self._state == S_UP_TO_DATE:
            self._centred(d, "You're on the latest version",
                          y + h // 2 - 4, theme.TEAL)
            return
        if self._state == S_FAILED:
            self._centred(d, "Last attempt failed:",
                          y + h // 2 - 12, theme.PRIMARY)
            self._centred(d, (self._error or "try again")[:36],
                          y + h // 2 + 2, theme.MUTED)
            return
        if self._state in (S_AVAILABLE, S_READY):
            rel = self._release or {}
            ver = rel.get("version", "?")
            d.text("New release", x + 8, y + 6, theme.PRIMARY, scale=1)
            d.text(ver,            x + 8, y + 18, theme.TEXT_BRIGHT, scale=2)
            # Bytes line — right-aligned to give space for the notes body.
            if self._peeked:
                kb = max(1, self._peeked["bytes"] // 1024)
                meta = "%d KB · %d files" % (kb,
                                             len(self._peeked["changed"]))
                d.text(meta, x + w - len(meta) * 8 - 8, y + 22,
                       theme.MUTED, scale=1)
            # Release-notes excerpt — pull from rel["notes"] (the
            # GitHub release body). 3 lines, hard-wrapped, ellipsis on
            # overflow. Mirrors what shows on the GitHub Releases page
            # for this tag.
            notes_y = y + 42
            for i, line in enumerate(self._wrap_notes(rel.get("notes") or "",
                                                       (w - 16) // 8, 3)):
                d.text(line, x + 8, notes_y + i * 12,
                       theme.TEXT_DIM, scale=1)
            return
        # idle (rarely seen — we auto-check on entry)
        self._centred(d, "Press A on 'Check for updates'",
                      y + h // 2 - 4, theme.MUTED)

    def _draw_action_row(self, d, idx, y, label, enabled):
        x = 6
        w = SW - 12
        sel = (idx == self._sel)
        bg = theme.DOCK_SEL if sel else theme.CARD
        d.rect(x, y, w, ACTION_H, bg, fill=True)
        if sel:
            d.rect(x, y,                w, 1, theme.SEL_BORDER, fill=True)
            d.rect(x, y + ACTION_H - 1, w, 1, theme.SEL_BORDER, fill=True)
            d.rect(x, y,                1, ACTION_H, theme.SEL_BORDER, fill=True)
            d.rect(x + w - 1, y,        1, ACTION_H, theme.SEL_BORDER, fill=True)
        color = (theme.TEXT_BRIGHT if enabled else theme.MUTED2)
        d.text(label, x + 10, y + 7, color, scale=1)
        # Right-edge state hint
        if idx == self.ROW_INSTALL and not enabled:
            hint = "no update"
            d.text(hint, x + w - len(hint) * 8 - 10,
                   y + 7, theme.MUTED2, scale=1)

    # ── label / state helpers ─────────────────────────────────────────
    def _refresh_label(self):
        if self._state == S_CHECKING:
            return "Checking..."
        return "Check for updates"

    def _install_label(self):
        if self._state == S_DOWNLOADING:
            return "Downloading..."
        if self._state == S_READY:
            return "Install + reboot"
        if self._state == S_AVAILABLE:
            ver = (self._release or {}).get("version", "")
            return ("Install " + ver) if ver else "Install update"
        return "Install update"

    def _state_pill(self):
        if self._state == S_CHECKING:    return ("CHECKING",    theme.MUTED)
        if self._state == S_DOWNLOADING: return ("DOWNLOADING", theme.PRIMARY)
        if self._state == S_AVAILABLE:   return ("UPDATE",      theme.PRIMARY)
        if self._state == S_READY:       return ("READY",       theme.PRIMARY)
        if self._state == S_UP_TO_DATE:  return ("LATEST",      theme.TEAL)
        if self._state == S_FAILED:      return ("ERROR",       theme.PRIMARY)
        return (None, None)

    @staticmethod
    def _current_version():
        try:
            from oreoOS.config import VERSION
            return VERSION
        except Exception:
            return "?"

    @staticmethod
    def _wrap_notes(text, max_chars, max_lines):
        """Soft word-wrap with a hard ellipsis on overflow. Returns a
        list of up to `max_lines` strings."""
        out  = []
        rest = (text or "").split()
        cur  = ""
        while rest and len(out) < max_lines:
            w = rest[0]
            cand = (cur + " " + w) if cur else w
            if len(cand) <= max_chars:
                cur = cand
                rest.pop(0)
                continue
            if cur:
                out.append(cur)
                cur = ""
                continue
            out.append(w[:max_chars])
            rest[0] = w[max_chars:]
        if cur and len(out) < max_lines:
            out.append(cur)
        if rest and out:
            # Trailing ellipsis on the last line if the body got cut off.
            last = out[-1]
            cut  = max_chars - 1
            out[-1] = (last[:cut].rstrip() + "…") if len(last) > cut else last + "…"
        return out

    @staticmethod
    def _centred(d, msg, y, color):
        d.text(msg, (SW - len(msg) * 8) // 2, y, color, scale=1)
