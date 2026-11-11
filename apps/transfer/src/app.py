"""Transfer — receive photos, videos and documents from a computer over USB.

Open the app, run `oreo transfer send <files>` on the computer and type
the six-character code shown here. Files are checked (SHA-256 and their
format header) before they appear in the Gallery or the Reader.

Screens follow the session in src/proto.py:
  waiting    the code, big, and the command to run on the computer
  hello      a computer connected and has not entered the code yet
  authed     ready; a progress bar while a file arrives; recent results
  locked     too many wrong codes: a countdown, then a new code

Controls:
  B      cancel the session (or leave the app when nobody is connected)
  RIGHT  draw a new code (when nobody is connected)
  HOME   leave; leaving always ends the session

Wi-Fi is not used: files come over the USB cable only.
"""

import time

import oreoOS
from oreoOS import api, theme, widgets

from . import proto
from .link import UsbLink


SW = api.SCREEN_W
SH = api.SCREEN_H
PAD = 12
TOP = widgets.HEADER_H + 8

READ_BUDGET_MS = 25              # serial reading per frame
PROGRESS_MS = 250                # repaint cadence while a file arrives
ANIM_MS = 400                    # "waiting..." dots

GREEN = api.rgb(61, 190, 120)


def _clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n - 1] + "~"


def _kb(n):
    return "%d KB" % ((n + 1023) // 1024)


def _center(d, s, y, color, scale=1):
    d.text(s, (SW - len(s) * 8 * scale) // 2, y, color, scale=scale)


class App(oreoOS.App):
    name = "Transfer"
    author = "Circuit-Overtime"
    SHOW_LOADING = False
    BLOCK_IDLE = False               # set while a computer is connected

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os = os_
        self._dirty = True
        self._sig = None
        self._next_paint = 0
        self._err = ""
        try:
            from oreoOS.config import VERSION
        except Exception:
            VERSION = ""
        self._link = None
        try:
            self._link = UsbLink(proto.MAX_LINE)
            self._link.open()
            out = self._link.write_line
        except Exception as e:
            self._err = "USB serial unavailable: %s" % e
            out = lambda s: None
        try:
            self._rx = proto.Receiver(out, notify=self._notify, os_version=VERSION)
        except Exception as e:      # no hardware RNG: no code, no transfer
            self._rx = None
            self._err = "cannot make a code: %s" % e

    def on_exit(self):
        if self._rx is not None:
            self._rx.close()
        if self._link is not None:
            self._link.close()
        self.BLOCK_IDLE = False

    def realtime_mode(self):
        # While a computer is connected: the 1 ms frame floor (the serial
        # stream is read once per frame) and no network housekeeping.
        return self._rx is not None and self._rx.active()

    # ── events ──────────────────────────────────────────────────────────
    def _notify(self, kind, name, size):
        try:
            from oreoOS import notifications
            notifications.push("file", "Received %s" % kind,
                               "%s - %s" % (_clip(name, 18), _kb(size)),
                               target="gallery" if kind in ("image", "video") else "reader")
        except Exception:
            pass

    def on_button_press(self, btn):
        rx = self._rx
        if btn == api.BTN_HOME:
            self._os.quit()
            return
        if btn == api.BTN_B:
            if rx is not None and rx.active():
                rx.cancel()
                self._dirty = True
            else:
                self._os.quit()
            return
        if btn == api.BTN_RIGHT and rx is not None and not rx.active() \
                and not rx.locked_ms():
            rx.new_code()
            self._dirty = True

    # ── per frame ───────────────────────────────────────────────────────
    def update(self, dt):
        rx = self._rx
        if rx is None or self._link is None:
            return
        try:
            lines = self._link.read_lines(READ_BUDGET_MS)
        except Exception as e:
            self._err = "USB read failed: %s" % e
            self._dirty = True
            return
        for ln in lines:
            rx.feed(ln)
        rx.tick()
        if lines:
            pm = getattr(self._os, "_power", None)
            if pm is not None:
                try:
                    pm.note_event()
                except Exception:
                    pass
        self.BLOCK_IDLE = rx.active()

        now = time.ticks_ms()
        prog = rx.progress()
        sig = (rx.state, rx.code, rx.host, rx.tries, len(rx.log),
               rx.log[-1] if rx.log else None, (rx.locked_ms() + 999) // 1000,
               prog[0] if prog else None)
        if sig != self._sig:
            self._sig = sig
            self._dirty = True
        elif prog and rx.changed and time.ticks_diff(now, self._next_paint) >= 0:
            self._dirty = True
        elif rx.state in (proto.WAITING, proto.HELLO) and \
                time.ticks_diff(now, self._next_paint) >= 0:
            self._dirty = True       # animated dots
        if self._dirty:
            rx.changed = False
            self._next_paint = time.ticks_add(
                now, PROGRESS_MS if prog else ANIM_MS)

    # ── drawing ─────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "TRANSFER")
        rx = self._rx
        if rx is None or self._err:
            d.text("Transfer cannot start:", PAD, TOP + 10, theme.PRIMARY)
            d.text(_clip(self._err, 38), PAD, TOP + 26, theme.TEXT_DIM)
            widgets.draw_hint(d, "B=back")
            return
        locked = (rx.locked_ms() + 999) // 1000
        if locked:
            self._draw_locked(d, locked)
        elif rx.state == proto.WAITING:
            self._draw_waiting(d, rx)
        elif rx.state == proto.HELLO:
            self._draw_hello(d, rx)
        else:
            self._draw_session(d, rx)
        self._draw_log(d, rx)
        if rx.active():
            widgets.draw_hint(d, "B=cancel  HOME=leave")
        else:
            widgets.draw_hint(d, "B=back  R=new code")

    def _dots(self):
        return "." * (1 + (time.ticks_ms() // ANIM_MS) % 3)

    def _draw_code(self, d, rx, y):
        _center(d, rx.code, y, theme.PRIMARY, scale=3)

    def _draw_waiting(self, d, rx):
        _center(d, "Code for your computer", TOP, theme.TEXT_DIM)
        self._draw_code(d, rx, TOP + 16)
        _center(d, "Waiting for a computer" + self._dots(), TOP + 50, theme.GOLD)
        y = TOP + 72
        d.text("On the computer, over USB:", PAD, y, theme.TEXT_DIM)
        d.text("oreo transfer send <files>", PAD, y + 14, theme.TEAL)
        d.text("then type the code above.", PAD, y + 28, theme.TEXT_DIM)

    def _draw_hello(self, d, rx):
        _center(d, "Connected: " + _clip(rx.host, 26), TOP, theme.TEXT_BRIGHT)
        self._draw_code(d, rx, TOP + 16)
        _center(d, "Type this code on the computer" + self._dots(),
                TOP + 50, theme.GOLD)
        if rx.tries:
            _center(d, "Wrong code - %d tries left" % rx.tries_left(),
                    TOP + 66, theme.PRIMARY)

    def _draw_locked(self, d, secs):
        _center(d, "TOO MANY WRONG CODES", TOP + 6, theme.PRIMARY, scale=1)
        _center(d, "%ds" % secs, TOP + 26, theme.PRIMARY, scale=3)
        _center(d, "A new code appears after this.", TOP + 60, theme.TEXT_DIM)

    def _draw_session(self, d, rx):
        d.rect(PAD, TOP + 2, 8, 8, GREEN, fill=True)
        d.text(_clip(rx.host, 30), PAD + 14, TOP + 2, theme.TEXT_BRIGHT)
        if rx.received:
            d.text("%d in" % rx.received, SW - PAD - 48, TOP + 2, theme.TEXT_DIM)
        prog = rx.progress()
        y = TOP + 22
        if prog is None:
            d.text("Ready. Send files from the computer.", PAD, y, theme.TEXT_DIM)
            return
        name, got, size = prog
        size = max(1, size)
        pct = got * 100 // size
        d.text("Receiving " + _clip(name, 28), PAD, y, theme.TEAL)
        bw = SW - 2 * PAD
        d.rect(PAD, y + 16, bw, 8, theme.MUTED2, fill=True)
        d.rect(PAD, y + 16, bw * got // size, 8, theme.PRIMARY, fill=True)
        d.text("%d%%  %s / %s" % (pct, _kb(got), _kb(size)), PAD, y + 30,
               theme.TEXT_DIM)

    def _draw_log(self, d, rx):
        if not rx.log:
            return
        y = SH - widgets.HINT_H - 4 - 13 * len(rx.log)
        d.rect(PAD, y - 5, SW - 2 * PAD, 1, theme.MUTED2, fill=True)
        for ok, text in rx.log:
            d.text("OK" if ok else "!!", PAD, y, GREEN if ok else theme.PRIMARY)
            d.text(_clip(text, 34), PAD + 24, y, theme.TEXT_BRIGHT)
            y += 13
