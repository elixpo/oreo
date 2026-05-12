"""Gamepad — visual gamepad layout showing live button state.

Renders a stylised badge controller on the 240x320 portrait display.
All 8 buttons are drawn as labelled shapes.  Held buttons highlight in
PRIMARY (cyan).  Press A or HOME to exit.

Layout (portrait, y=30..320 is the body):
  Left half:  D-pad as a + cross  (UP/DOWN/LEFT/RIGHT)
  Right half: action cluster A/B/C as circles
  Top center: HOME button
"""

import lix
from lix import api

# ---- palette ----------------------------------------------------------------
C_BG        = api.rgb(12,  12,  24)
C_HEADER    = api.rgb(18,  18,  36)
C_PRIMARY   = api.rgb(0,  220, 200)   # highlight when pressed
C_IDLE_BTN  = api.rgb(40,  40,  70)   # unpressed button face
C_IDLE_Bdr  = api.rgb(80,  80, 120)   # unpressed border
C_LABEL     = api.WHITE
C_HINT      = api.rgb(100, 100, 140)
C_BODY_BG   = api.rgb(22,  22,  42)
C_TITLE     = api.rgb(0,  220, 200)

# ---- button geometry --------------------------------------------------------
# D-pad centre
DPAD_CX     = 68
DPAD_CY     = 195
DPAD_W      = 28    # arm width (and arm length from centre)
DPAD_ARM    = 28    # length of each arm from centre

# Action cluster centre
ACT_CX      = 180
ACT_CY      = 195
ACT_R       = 14    # circle radius

# HOME button
HOME_X      = 104   # top-left of HOME rect
HOME_Y      = 54
HOME_W      = 32
HOME_H      = 18

# Pad rectangle used for the body outline
PAD_X       = 14
PAD_Y       = 38
PAD_W       = 212
PAD_H       = 260
PAD_R       = 20    # conceptual corner radius (drawn as bevelled rect corners)


def _btn_colors(pressed):
    if pressed:
        return C_PRIMARY, C_PRIMARY
    return C_IDLE_BTN, C_IDLE_Bdr


def _draw_filled_circle(d, cx, cy, r, color):
    """Approximate a filled circle using horizontal spans (Bresenham)."""
    x = r
    y = 0
    err = 0
    while x >= y:
        d.rect(cx - x, cy - y, 2 * x + 1, 1, color, fill=True)
        d.rect(cx - x, cy + y, 2 * x + 1, 1, color, fill=True)
        d.rect(cx - y, cy - x, 2 * y + 1, 1, color, fill=True)
        d.rect(cx - y, cy + x, 2 * y + 1, 1, color, fill=True)
        y += 1
        err += 1 + 2 * y
        if 2 * (err - x) + 1 > 0:
            x -= 1
            err += 1 - 2 * x


def _draw_circle_outline(d, cx, cy, r, color):
    """Thin circle outline (8-point Bresenham)."""
    x = r
    y = 0
    err = 0
    while x >= y:
        for px, py in [
            (cx + x, cy + y), (cx - x, cy + y),
            (cx + x, cy - y), (cx - x, cy - y),
            (cx + y, cy + x), (cx - y, cy + x),
            (cx + y, cy - x), (cx - y, cy - x),
        ]:
            d.pixel(px, py, color)
        y += 1
        err += 1 + 2 * y
        if 2 * (err - x) + 1 > 0:
            x -= 1
            err += 1 - 2 * x


def _draw_rounded_rect(d, x, y, w, h, color, fill=True, corner=4):
    """Rounded rectangle using a filled interior + corner squares clipped."""
    # Fill the main cross-shaped area
    if fill:
        d.rect(x + corner, y,          w - 2 * corner, h,          color, fill=True)
        d.rect(x,          y + corner, w,               h - 2 * corner, color, fill=True)
    else:
        # outline approximation: draw four edges, skip the extreme corners
        d.rect(x + corner, y,              w - 2 * corner, 1, color, fill=True)
        d.rect(x + corner, y + h - 1,      w - 2 * corner, 1, color, fill=True)
        d.rect(x,          y + corner,     1, h - 2 * corner, color, fill=True)
        d.rect(x + w - 1,  y + corner,     1, h - 2 * corner, color, fill=True)


class App(lix.App):
    name = "Gamepad"

    # ---- lifecycle ----------------------------------------------------------

    def on_enter(self, os):
        super().on_enter(os)
        self._dirty = True

    def on_button_press(self, btn):
        # A exits; HOME is handled by the OS launcher automatically.
        if btn == api.BTN_A:
            self.os.quit()
        self._dirty = True

    def on_button_release(self, btn):
        self._dirty = True

    def update(self, dt):
        pass

    # ---- draw ---------------------------------------------------------------

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False

        buttons = self.os.buttons

        # ---- background & header ----------------------------------------
        d.clear(C_BG)
        d.rect(0, 0, api.SCREEN_W, 30, C_HEADER, fill=True)
        d.text("GAMEPAD", 8, 9, C_TITLE, scale=2)

        # ---- gamepad body -----------------------------------------------
        # Body shadow/depth
        d.rect(PAD_X + 3, PAD_Y + 3, PAD_W, PAD_H, api.rgb(6, 6, 14), fill=True)
        # Body fill (rounded manually — draw cross + corner quads)
        _draw_rounded_rect(d, PAD_X, PAD_Y, PAD_W, PAD_H, C_BODY_BG, fill=True, corner=18)
        # Body outline
        _draw_rounded_rect(d, PAD_X, PAD_Y, PAD_W, PAD_H, api.rgb(60, 60, 90), fill=False, corner=18)

        # ---- HOME button ------------------------------------------------
        home_pressed = buttons.is_pressed(api.BTN_HOME)
        hbg, hbdr = _btn_colors(home_pressed)
        _draw_rounded_rect(d, HOME_X, HOME_Y, HOME_W, HOME_H, hbg,  fill=True,  corner=4)
        _draw_rounded_rect(d, HOME_X, HOME_Y, HOME_W, HOME_H, hbdr, fill=False, corner=4)
        # Label centred inside
        lbl = "HOME"
        lx = HOME_X + (HOME_W - len(lbl) * 8) // 2
        ly = HOME_Y + (HOME_H - 8) // 2
        d.text(lbl, lx, ly, api.BLACK if home_pressed else C_LABEL)
        # Sub-label
        sub = "back"
        slx = HOME_X + (HOME_W - len(sub) * 8) // 2
        d.text(sub, slx, HOME_Y + HOME_H + 3, C_HINT)

        # ---- D-pad  (+ cross shape, each arm is a rect) ----------------
        arm = DPAD_ARM
        aw  = DPAD_W

        # mapping: (btn_id, dx, dy, label)
        dpad_arms = [
            (api.BTN_UP,    0,  -arm, "UP"),
            (api.BTN_DOWN,  0,   arm, "DN"),
            (api.BTN_LEFT, -arm,  0,  "LT"),
            (api.BTN_RIGHT, arm,  0,  "RT"),
        ]

        # draw the cross background first
        d.rect(DPAD_CX - aw // 2, DPAD_CY - arm - aw // 2,
               aw, arm * 2 + aw, api.rgb(30, 30, 55), fill=True)
        d.rect(DPAD_CX - arm - aw // 2, DPAD_CY - aw // 2,
               arm * 2 + aw, aw, api.rgb(30, 30, 55), fill=True)

        # draw each arm button
        for btn_id, dx, dy, lbl in dpad_arms:
            pressed = buttons.is_pressed(btn_id)
            face, border = _btn_colors(pressed)

            if dx == 0:
                # vertical arm
                ax = DPAD_CX - aw // 2
                ay = DPAD_CY + (1 if dy > 0 else -arm)
                aw2, ah2 = aw, arm - 1
            else:
                # horizontal arm
                ax = DPAD_CX + (1 if dx > 0 else -arm)
                ay = DPAD_CY - aw // 2
                aw2, ah2 = arm - 1, aw

            _draw_rounded_rect(d, ax, ay, aw2, ah2, face,   fill=True,  corner=3)
            _draw_rounded_rect(d, ax, ay, aw2, ah2, border, fill=False, corner=3)

            # label centred in arm
            llx = ax + (aw2 - len(lbl) * 8) // 2
            lly = ay + (ah2 - 8) // 2
            d.text(lbl, llx, lly, api.BLACK if pressed else C_LABEL)

        # D-pad centre pip
        d.rect(DPAD_CX - aw // 2, DPAD_CY - aw // 2,
               aw, aw, api.rgb(50, 50, 80), fill=True)

        # ---- action buttons  A / B / C  (triangle cluster) -------------
        # A = right, B = top-left offset, C = bottom-left offset
        act_positions = [
            (api.BTN_A, ACT_CX + 28, ACT_CY,      "A",  "select"),
            (api.BTN_B, ACT_CX - 10, ACT_CY - 28, "B",  "action2"),
            (api.BTN_C, ACT_CX - 10, ACT_CY + 28, "C",  "action3"),
        ]

        for btn_id, cx, cy, lbl, sub in act_positions:
            pressed = buttons.is_pressed(btn_id)
            face, border = _btn_colors(pressed)

            # filled circle
            _draw_filled_circle(d, cx, cy, ACT_R, face)
            # border ring (2px thick)
            _draw_circle_outline(d, cx, cy, ACT_R,     border)
            _draw_circle_outline(d, cx, cy, ACT_R - 1, border)

            # label centred
            llx = cx - len(lbl) * 4       # scale=1, char=8px wide -> half = 4
            lly = cy - 4                   # char height 8px -> half = 4
            d.text(lbl, llx, lly, api.BLACK if pressed else C_LABEL)

        # ---- sub-labels for D-pad directions (below the cross) ---------
        dpad_labels = [
            (api.BTN_UP,    DPAD_CX - aw // 2 - 6, DPAD_CY - arm - aw // 2 - 10, "up"),
            (api.BTN_DOWN,  DPAD_CX - aw // 2 + 2, DPAD_CY + arm + aw // 2 + 2,  "down"),
            (api.BTN_LEFT,  DPAD_CX - arm - aw // 2 - 2, DPAD_CY + aw // 2 + 2,  "left"),
            (api.BTN_RIGHT, DPAD_CX + arm + aw // 2 - 2, DPAD_CY + aw // 2 + 2,  "right"),
        ]
        for btn_id, lx, ly, sub in dpad_labels:
            pressed = buttons.is_pressed(btn_id)
            col = C_PRIMARY if pressed else C_HINT
            d.text(sub, lx, ly, col)

        # ---- sub-labels for action buttons (below each circle) ---------
        for btn_id, cx, cy, lbl, sub in act_positions:
            pressed = buttons.is_pressed(btn_id)
            col = C_PRIMARY if pressed else C_HINT
            slx = cx - len(sub) * 4
            sly = cy + ACT_R + 3
            d.text(sub, slx, sly, col)

        # ---- bottom hint strip ------------------------------------------
        foot_y = api.SCREEN_H - 22
        d.rect(0, foot_y, api.SCREEN_W, 22, api.rgb(10, 10, 20), fill=True)
        d.text("A  exit    HOME  menu", 6, foot_y + 6, C_HINT)

        # ---- "LIVE" indicator -------------------------------------------
        live_x = api.SCREEN_W - 56
        d.rect(live_x, 9, 46, 14, api.rgb(0, 80, 60), fill=True)
        d.text("LIVE", live_x + 7, 11, C_PRIMARY)
