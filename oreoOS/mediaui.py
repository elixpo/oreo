"""Shared screens for the audio apps (Radio, Podcasts, Jamendo, Music):
a scrolling list, an on-screen keyboard and the now-playing panel, each
drawn with the 8x8 font and driven by the buttons or by touch (PCB badge).

    lv = mediaui.ListView()
    lv.set(items)                       # anything; label(item) gives the text
    lv.key(btn)                         # UP/DOWN/LEFT/RIGHT move: True if moved
    i = lv.hit(x, y)                    # index under a touch, or None
    lv.draw(d, label, mark=None)        # mark(item) -> True draws a star

    kb = mediaui.Keyboard("search")
    kb.key(btn) / kb.hit(x, y)          # "ok", "cancel" or None
    kb.text

    mediaui.draw_player(d, info)        # see the function
    mediaui.player_hit(x, y)            # "play", "vol-", "vol+", "fav", ...
"""

from oreoOS import api, theme, widgets

ROW_H = 20
TOP = widgets.HEADER_H + 2
BOTTOM = api.SCREEN_H - widgets.HINT_H
ROWS = (BOTTOM - TOP) // ROW_H
CHARS = api.SCREEN_W // 8


def clean(s, n=None):
    """s as printable ASCII (the badge font has nothing else), clipped to
    n characters with a trailing '..'."""
    if s is None:
        return ""
    s = str(s)
    out = []
    for ch in s:
        o = ord(ch)
        if 32 <= o < 127:
            out.append(ch)
        elif o in (0xe4, 0xc4):
            out.append("a")
        elif o in (0xf6, 0xd6):
            out.append("o")
        elif o in (0xfc, 0xdc):
            out.append("u")
        elif o in (0xe9, 0xe8, 0xea, 0xc9):
            out.append("e")
        elif o in (0x2018, 0x2019):
            out.append("'")
        elif o in (0x2013, 0x2014):
            out.append("-")
        elif o in (9, 10, 13):
            out.append(" ")
        else:
            out.append("?")
    s = "".join(out).strip()
    if n is not None and len(s) > n:
        s = s[:max(0, n - 2)] + ".."
    return s


def wrap(s, width, lines):
    """s split into at most `lines` lines of `width` characters."""
    words = clean(s).split(" ")
    out = []
    cur = ""
    for w in words:
        while len(w) > width:
            if cur:
                out.append(cur)
                cur = ""
            out.append(w[:width])
            w = w[width:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = clean(out[-1], width - 1) + ".."
    return out


def mmss(seconds):
    s = int(seconds or 0)
    if s >= 3600:
        return "%d:%02d:%02d" % (s // 3600, (s // 60) % 60, s % 60)
    return "%d:%02d" % (s // 60, s % 60)


class ListView:
    def __init__(self, rows=ROWS):
        self.rows = rows
        self.items = []
        self.sel = 0
        self.top = 0

    def set(self, items, keep=False):
        self.items = items or []
        if not keep:
            self.sel = self.top = 0
        self.sel = max(0, min(self.sel, len(self.items) - 1))
        self._scroll()

    def current(self):
        if 0 <= self.sel < len(self.items):
            return self.items[self.sel]
        return None

    def _scroll(self):
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + self.rows:
            self.top = self.sel - self.rows + 1
        self.top = max(0, self.top)

    def key(self, btn):
        n = len(self.items)
        if not n:
            return False
        old = self.sel
        if btn == api.BTN_UP:
            self.sel = (self.sel - 1) % n
        elif btn == api.BTN_DOWN:
            self.sel = (self.sel + 1) % n
        elif btn == api.BTN_LEFT:
            self.sel = max(0, self.sel - self.rows)
        elif btn == api.BTN_RIGHT:
            self.sel = min(n - 1, self.sel + self.rows)
        else:
            return False
        self._scroll()
        return self.sel != old

    def hit(self, x, y):
        if y < TOP or y >= TOP + self.rows * ROW_H:
            return None
        i = self.top + (y - TOP) // ROW_H
        return i if 0 <= i < len(self.items) else None

    def draw(self, d, label, mark=None, right=None):
        d.rect(0, TOP - 2, api.SCREEN_W, BOTTOM - TOP + 2, theme.BG, fill=True)
        if not self.items:
            d.text("Nothing here.", 16, TOP + 8, theme.TEXT_DIM)
            return
        for row in range(self.rows):
            i = self.top + row
            if i >= len(self.items):
                break
            it = self.items[i]
            y = TOP + row * ROW_H
            sel = i == self.sel
            if sel:
                d.rect(2, y, api.SCREEN_W - 4, ROW_H - 2, theme.DOCK_SEL, fill=True)
                d.rect(2, y, 3, ROW_H - 2, theme.SEL_BORDER, fill=True)
            x = 10
            if mark is not None and mark(it):
                d.text("*", x, y + 6, theme.GOLD)
            x = 20
            r = clean(right(it)) if right is not None else ""
            room = CHARS - 3 - (len(r) + 1 if r else 0)
            d.text(clean(label(it), room), x, y + 6,
                   theme.TEXT_BRIGHT if sel else theme.TEXT_DIM)
            if r:
                d.text(r, api.SCREEN_W - 8 * len(r) - 8, y + 6, theme.MUTED)
        if len(self.items) > self.rows:
            # scroll bar
            h = BOTTOM - TOP - 4
            bh = max(8, h * self.rows // len(self.items))
            by = TOP + (h - bh) * self.top // max(1, len(self.items) - self.rows)
            d.rect(api.SCREEN_W - 3, by, 2, bh, theme.MUTED, fill=True)


# ── on-screen keyboard ─────────────────────────────────────────────────────

# Three layouts of 4 x 10 keys; the bottom row switches between them.
KB_LAYOUTS = (
    ("abcdefghij", "klmnopqrst", "uvwxyz0123", "456789-_.@"),
    ("ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ0123", "456789-_.@"),
    ("1234567890", "!#$%&*()+=", "/:;,?'\"~|^", "<>[]{}\\`-."),
)
KB_ROWS = KB_LAYOUTS[0]
KB_ACTIONS = ("aA", "#+", "SPACE", "DEL", "OK")
KB_X, KB_Y, KB_W, KB_H = 10, 80, 30, 28
KB_ACT_W = 60


class Keyboard:
    """Text entry: letters (lower and upper case), digits and symbols,
    space, delete and OK. B deletes, or cancels when the text is empty."""

    def __init__(self, prompt, text="", limit=64, secret=False):
        self.prompt = prompt
        self.text = text
        self.limit = limit
        self.secret = secret
        self.layout = 0
        self.r = 0
        self.c = 0

    def rows(self):
        return KB_LAYOUTS[self.layout]

    def _press(self, r, c):
        if r < 4:
            if len(self.text) < self.limit:
                self.text += self.rows()[r][c]
            return None
        act = KB_ACTIONS[c]
        if act == "aA":
            self.layout = 0 if self.layout == 1 else 1
        elif act == "#+":
            self.layout = 0 if self.layout == 2 else 2
        elif act == "SPACE":
            if len(self.text) < self.limit:
                self.text += " "
        elif act == "DEL":
            self.text = self.text[:-1]
        else:
            return "ok"
        return None

    def key(self, btn):
        if btn == api.BTN_UP:
            self.r = (self.r - 1) % 5
        elif btn == api.BTN_DOWN:
            self.r = (self.r + 1) % 5
        elif btn == api.BTN_LEFT:
            self.c -= 1
        elif btn == api.BTN_RIGHT:
            self.c += 1
        elif btn == api.BTN_A:
            return self._press(self.r, self.c)
        elif btn == api.BTN_B:
            if self.text:
                self.text = self.text[:-1]
                return None
            return "cancel"
        width = len(KB_ACTIONS) if self.r == 4 else 10
        self.c %= width
        return None

    def hit(self, x, y):
        """Press the key under a touch: "ok", or None."""
        if y < KB_Y:
            return None
        r = (y - KB_Y) // KB_H
        if r == 4:
            c = (x - KB_X) // KB_ACT_W
            if 0 <= c < len(KB_ACTIONS):
                self.r, self.c = r, c
                return self._press(r, c)
            return None
        if r > 4:
            return None
        c = (x - KB_X) // KB_W
        if 0 <= c < 10:
            self.r, self.c = r, c
            return self._press(r, c)
        return None

    def draw(self, d):
        d.rect(0, TOP - 2, api.SCREEN_W, BOTTOM - TOP + 2, theme.BG, fill=True)
        d.text(clean(self.prompt, CHARS - 2), 10, TOP + 6, theme.TEXT_DIM)
        widgets.draw_panel(d, 8, TOP + 20, api.SCREEN_W - 16, 22)
        shown = "*" * len(self.text) if self.secret else self.text
        d.text(clean(shown[-34:]) + "_", 14, TOP + 27, theme.TEXT_BRIGHT)
        for r, row in enumerate(self.rows()):
            for c, ch in enumerate(row):
                x, y = KB_X + c * KB_W, KB_Y + r * KB_H
                sel = r == self.r and c == self.c
                d.rect(x, y, KB_W - 2, KB_H - 2, theme.DOCK_SEL if sel else theme.CARD, fill=True)
                d.text(ch, x + 11, y + 9, theme.PRIMARY if sel else theme.TEXT_BRIGHT)
        y = KB_Y + 4 * KB_H
        for c, act in enumerate(KB_ACTIONS):
            x = KB_X + c * KB_ACT_W
            sel = self.r == 4 and self.c == c
            d.rect(x, y, KB_ACT_W - 4, KB_H - 2, theme.DOCK_SEL if sel else theme.CARD, fill=True)
            d.text(act, x + (KB_ACT_W - 4 - 8 * len(act)) // 2, y + 9,
                   theme.PRIMARY if sel else theme.TEXT_BRIGHT)


# ── now playing ────────────────────────────────────────────────────────────

# Touch buttons along the bottom of the now-playing screen.
PLAYER_BUTTONS = (
    ("back15", "-15"), ("play", ">/||"), ("fwd30", "+30"),
    ("vol-", "VOL-"), ("vol+", "VOL+"), ("fav", "*"),
)
BTN_Y = BOTTOM - 40
BTN_W = api.SCREEN_W // len(PLAYER_BUTTONS)


def player_hit(x, y, buttons=PLAYER_BUTTONS):
    if y < BTN_Y or y >= BTN_Y + 36:
        return None
    i = x // (api.SCREEN_W // len(buttons))
    if 0 <= i < len(buttons):
        return buttons[i][0]
    return None


STATE_TEXT = {
    "idle": "Stopped",
    "connecting": "Connecting...",
    "buffering": "Buffering...",
    "playing": "Playing",
    "error": "Error",
    "ended": "Finished",
}


def draw_player(d, name, title, state, detail="", volume=0, fav=None,
                position=None, duration=None, buttons=PLAYER_BUTTONS, extra=None):
    """The now-playing panel: name (station, show or artist), title (the
    track or StreamTitle), the player state with detail (an error, a
    licence), position / duration in seconds, a volume bar and the touch
    buttons. fav: None hides the star, else whether it is lit."""
    d.rect(0, TOP - 2, api.SCREEN_W, BOTTOM - TOP + 2, theme.BG, fill=True)
    widgets.draw_panel(d, 8, TOP + 4, api.SCREEN_W - 16, 104)
    y = TOP + 12
    d.text(clean(name, 36), 16, y, theme.PRIMARY)
    if fav is not None:
        d.text("*" if fav else "-", api.SCREEN_W - 26, y, theme.GOLD if fav else theme.MUTED)
    y += 16
    for line in wrap(title or "", 36, 3):
        d.text(line, 16, y, theme.TEXT_BRIGHT)
        y += 12
    y = TOP + 76
    st = STATE_TEXT.get(state, state or "")
    d.text(clean(st, 14), 16, y, theme.TEAL if state == "playing" else theme.TEXT_DIM)
    if position is not None:
        t = mmss(position) + (" / " + mmss(duration) if duration else "")
        d.text(t, api.SCREEN_W - 16 - 8 * len(t), y, theme.TEXT_DIM)
    if detail:
        d.text(clean(detail, 36), 16, y + 14, api.RED if state == "error" else theme.MUTED)
    if extra:
        d.text(clean(extra, 36), 16, TOP + 116, theme.TEXT_DIM)
    # volume
    vy = BTN_Y - 18
    d.text("VOL", 16, vy, theme.TEXT_DIM)
    bw = api.SCREEN_W - 80
    d.rect(48, vy, bw, 8, theme.CARD, fill=True)
    d.rect(48, vy, bw * max(0, min(100, volume)) // 100, 8, theme.PRIMARY, fill=True)
    d.text("%d" % volume, 52 + bw, vy, theme.TEXT_DIM)
    w = api.SCREEN_W // len(buttons)
    for i, (bid, label) in enumerate(buttons):
        x = i * w
        d.rect(x + 2, BTN_Y, w - 4, 36, theme.CARD, fill=True)
        if bid == "play":
            label = "STOP" if state in ("playing", "buffering", "connecting") else "PLAY"
        d.text(label, x + (w - 8 * len(label)) // 2, BTN_Y + 14, theme.TEXT_BRIGHT)


def draw_message(d, title, lines):
    """A centred card: a title and a few lines (setup steps, errors)."""
    d.rect(0, TOP - 2, api.SCREEN_W, BOTTOM - TOP + 2, theme.BG, fill=True)
    h = 30 + 12 * len(lines)
    y0 = max(TOP + 4, (TOP + BOTTOM - h) // 2)
    widgets.draw_panel(d, 10, y0, api.SCREEN_W - 20, h)
    d.text(clean(title, 36), 20, y0 + 8, theme.PRIMARY)
    y = y0 + 24
    for line in lines:
        d.text(clean(line, 36), 20, y, theme.TEXT_BRIGHT)
        y += 12


NEEDS_SPEAKER = ("This app plays through the speaker",
                 "of the PCB Falera Badge. This badge",
                 "has no speaker amp.")


def has_speaker(os):
    a = getattr(os, "audio", None)
    return bool(a is not None and getattr(a, "available", False))
