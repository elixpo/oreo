"""Touch screen calibration (PCB badge): tap four targets, get a calibration.

Settings runs a Calibration while its "Touch" row is open. It never
blocks: update() takes one raw reading per frame from the touch driver
(oreoWare.touch, read_raw() samples only while the screen is pressed) and
draw() paints a target only when the step changes.

solve() turns the four raw readings into a calibration for
oreoWare.touch.to_screen(): it works out whether the panel's axes are
swapped, and reports each axis as the raw values at the screen's two
edges. A flipped axis simply has x_min > x_max, which to_screen() handles,
so the flip flags stay False. load()/save() keep it in oreoOS.state.
"""

SCREEN_W = 320
SCREEN_H = 240
INSET = 24
# The four targets, clockwise from the top left.
TARGETS = ((INSET, INSET), (SCREEN_W - 1 - INSET, INSET),
           (SCREEN_W - 1 - INSET, SCREEN_H - 1 - INSET),
           (INSET, SCREEN_H - 1 - INSET))
MIN_SAMPLES = 3         # readings that make a tap (one per frame)
MIN_SPAN = 600          # raw counts the targets must span on each axis
STATE_NAME = "touch"


def _edges(r_lo, u_lo, r_hi, u_hi, size):
    """The raw values at screen positions 0 and size - 1, from two
    (raw, screen) pairs on one axis."""
    k = (r_hi - r_lo) / (u_hi - u_lo)      # raw counts per pixel
    lo = r_lo - u_lo * k
    hi = lo + (size - 1) * k
    return int(round(lo)), int(round(hi))


def solve(points):
    """Calibration from the raw (x, y) readings at the four TARGETS, or
    None if they don't look like four taps on the targets."""
    if len(points) != 4:
        return None
    tl, tr, br, bl = points
    # Moving right along the top edge changes the raw axis that follows
    # screen x; if that's raw y, the panel is mounted with its axes swapped.
    swap = abs(tr[1] - tl[1]) > abs(tr[0] - tl[0])
    if swap:
        tl, tr, br, bl = [(p[1], p[0]) for p in (tl, tr, br, bl)]
    left = (tl[0] + bl[0]) / 2
    right = (tr[0] + br[0]) / 2
    top = (tl[1] + tr[1]) / 2
    bottom = (bl[1] + br[1]) / 2
    if abs(right - left) < MIN_SPAN or abs(bottom - top) < MIN_SPAN:
        return None
    x_min, x_max = _edges(left, INSET, right, SCREEN_W - 1 - INSET, SCREEN_W)
    y_min, y_max = _edges(top, INSET, bottom, SCREEN_H - 1 - INSET, SCREEN_H)
    return {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max,
            "swap_xy": swap, "flip_x": False, "flip_y": False}


def load():
    """The saved calibration, or None."""
    try:
        from oreoOS import state
        cal = state.load(STATE_NAME, None)
    except Exception:
        return None
    if isinstance(cal, dict) and all(k in cal for k in
                                     ("x_min", "x_max", "y_min", "y_max")):
        return cal
    return None


def save(cal):
    try:
        from oreoOS import state
        state.save(STATE_NAME, cal)
        return True
    except Exception:
        return False


class Calibration:
    """Four taps, one per target. state is "target" until the last tap,
    then "done" (calibration in .result) or "failed"."""

    def __init__(self, touch):
        self._touch = touch
        self.points = []
        self.state = "target"
        self.result = None
        self.dirty = True
        self._sx = self._sy = self._n = 0

    @property
    def step(self):
        return len(self.points)

    def update(self):
        if self.state != "target":
            return
        try:
            r = self._touch.read_raw()
        except Exception:
            r = None
        if r is not None:
            self._sx += r[0]
            self._sy += r[1]
            self._n += 1
            return
        if self._n == 0:
            return
        # The finger lifted: a tap if it lasted a few readings.
        if self._n >= MIN_SAMPLES:
            self.points.append((self._sx // self._n, self._sy // self._n))
            self.dirty = True
        self._sx = self._sy = self._n = 0
        if len(self.points) == len(TARGETS):
            self.result = solve(self.points)
            self.state = "done" if self.result else "failed"
            self.dirty = True

    def draw(self, d, theme):
        if not self.dirty:
            return
        self.dirty = False
        d.clear(theme.BG)
        if self.state == "target":
            x, y = TARGETS[self.step]
            d.line(x - 12, y, x + 12, y, theme.PRIMARY)
            d.line(x, y - 12, x, y + 12, theme.PRIMARY)
            d.rect(x - 3, y - 3, 7, 7, theme.PRIMARY, fill=True)
            msg = "Tap the target (%d of %d)" % (self.step + 1, len(TARGETS))
            d.text(msg, (SCREEN_W - len(msg) * 8) // 2, 104, theme.TEXT_BRIGHT)
            hint = "Use a fingernail or stylus.  B = cancel"
            d.text(hint, (SCREEN_W - len(hint) * 8) // 2, 124, theme.MUTED)
        elif self.state == "done":
            msg = "Touch calibrated"
            d.text(msg, (SCREEN_W - len(msg) * 16) // 2, 100, theme.GREEN, scale=2)
            hint = "Saved.  Any button to go back"
            d.text(hint, (SCREEN_W - len(hint) * 8) // 2, 130, theme.MUTED)
        else:
            msg = "Didn't work"
            d.text(msg, (SCREEN_W - len(msg) * 16) // 2, 92, theme.PRIMARY, scale=2)
            for i, line in enumerate(("The taps were too close together.",
                                      "A = try again   B = back")):
                d.text(line, (SCREEN_W - len(line) * 8) // 2, 122 + i * 16,
                       theme.MUTED)
