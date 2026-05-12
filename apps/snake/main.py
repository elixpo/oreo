"""Snake — classic snake game for the Elixpo badge.

Play area: 240x280 pixels (y=30..310), 24 cols x 28 rows, cell size 10px.
Header bar: y=0..30 — shows title and score.
Controls: UP/DOWN/LEFT/RIGHT to steer, A to start or restart after game over.
Speed starts at 10 moves/sec and increases by 0.5/sec every 5 points.
"""

import lix
from lix import api

# ---- geometry ---------------------------------------------------------------
CELL          = 10          # pixels per cell
COLS          = 24          # 240 / 10
ROWS          = 28          # 280 / 10
PLAY_Y        = 30          # top of play area in pixels
PLAY_H        = 280         # height of play area

# ---- colors -----------------------------------------------------------------
C_BG          = api.rgb(8,   8,  20)
C_HEADER      = api.rgb(18,  18,  36)
C_HEAD        = api.rgb(0,  220, 200)
C_BODY        = api.rgb(0,  160, 140)
C_FOOD        = api.rgb(255, 80, 200)
C_GAMEOVER    = api.rgb(200,  30,  60)
C_TITLE       = api.rgb(0,  220, 200)
C_SCORE       = api.WHITE
C_HINT        = api.rgb(140, 140, 170)

# ---- speed ------------------------------------------------------------------
SPEED_BASE    = 10.0        # moves per second at score 0
SPEED_STEP    = 0.5         # extra moves/sec per 5-point bracket
SPEED_CAP     = 20.0        # hard cap so the game stays playable

# ---- LCG pseudo-random (no `random` module on MicroPython) ------------------
# next_seed = (seed * 1103515245 + 12345) & 0x7fffffff
_lcg_seed = 12345

def _lcg_next():
    global _lcg_seed
    _lcg_seed = (_lcg_seed * 1103515245 + 12345) & 0x7fffffff
    return _lcg_seed

def _rand_cell():
    """Return a random (col, row) within the play area."""
    c = _lcg_next() % COLS
    r = _lcg_next() % ROWS
    return (c, r)


# ---- directions -------------------------------------------------------------
DIR_RIGHT = (1,  0)
DIR_LEFT  = (-1, 0)
DIR_UP    = (0, -1)
DIR_DOWN  = (0,  1)


class App(lix.App):
    name = "Snake"

    # ---- lifecycle ----------------------------------------------------------

    def on_enter(self, os):
        super().on_enter(os)
        self._state = "title"   # "title" | "playing" | "gameover"
        self._reset()
        self._dirty = True

    def _reset(self):
        """Initialise / restart the game state."""
        # Snake stored as list of (col, row), head first.
        cx = COLS // 2
        cy = ROWS // 2
        self._snake   = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self._dir     = DIR_RIGHT
        self._next_dir = DIR_RIGHT
        self._score   = 0
        self._timer   = 0.0     # accumulates dt between moves
        self._speed   = SPEED_BASE
        self._food    = self._place_food()
        self._dirty   = True
        self._prev_tail = None  # used for erasing just the tail cell

    def _place_food(self):
        """Find a random empty cell (not occupied by the snake)."""
        snake_set = set(self._snake)
        attempts = 0
        while attempts < COLS * ROWS:
            cell = _rand_cell()
            if cell not in snake_set:
                return cell
            attempts += 1
        # board nearly full — just find the first empty cell
        for r in range(ROWS):
            for c in range(COLS):
                if (c, r) not in snake_set:
                    return (c, r)
        return self._snake[-1]  # shouldn't happen

    # ---- input --------------------------------------------------------------

    def on_button_press(self, btn):
        if self._state == "title":
            if btn == api.BTN_A:
                self._state = "playing"
                self._dirty = True
            return

        if self._state == "gameover":
            if btn == api.BTN_A:
                self._reset()
                self._state = "playing"
                self._dirty = True
            return

        # playing
        if btn == api.BTN_UP and self._dir != DIR_DOWN:
            self._next_dir = DIR_UP
        elif btn == api.BTN_DOWN and self._dir != DIR_UP:
            self._next_dir = DIR_DOWN
        elif btn == api.BTN_LEFT and self._dir != DIR_RIGHT:
            self._next_dir = DIR_LEFT
        elif btn == api.BTN_RIGHT and self._dir != DIR_LEFT:
            self._next_dir = DIR_RIGHT

    # ---- update -------------------------------------------------------------

    def update(self, dt):
        if self._state != "playing":
            return

        self._timer += dt
        interval = 1.0 / self._speed

        if self._timer < interval:
            return

        self._timer -= interval
        self._step()

    def _step(self):
        """Advance the snake by one cell."""
        self._dir = self._next_dir
        hc, hr = self._snake[0]
        dc, dr = self._dir
        nc, nr = hc + dc, hr + dr

        # wall collision
        if nc < 0 or nc >= COLS or nr < 0 or nr >= ROWS:
            self._state = "gameover"
            self._dirty = True
            return

        # self collision (skip the tail because it will move away)
        if (nc, nr) in set(self._snake[:-1]):
            self._state = "gameover"
            self._dirty = True
            return

        # move: prepend new head
        self._prev_tail = self._snake[-1]
        self._snake.insert(0, (nc, nr))

        ate = (nc, nr) == self._food
        if ate:
            self._score += 1
            self._prev_tail = None      # tail stays — no erase needed
            self._food = self._place_food()
            # speed increase every 5 points
            bracket = self._score // 5
            self._speed = min(SPEED_BASE + bracket * SPEED_STEP, SPEED_CAP)
        else:
            self._snake.pop()           # remove tail

        self._dirty = True

    # ---- draw ---------------------------------------------------------------

    def _cell_rect(self, c, r):
        """Return (px, py) top-left pixel of a cell."""
        return c * CELL, PLAY_Y + r * CELL

    def draw(self, d):
        if self._state == "title":
            self._draw_title(d)
            return

        if not self._dirty:
            return

        if self._state == "playing":
            self._draw_playing(d)
        elif self._state == "gameover":
            self._draw_gameover(d)

        self._dirty = False

    def _draw_header(self, d):
        d.rect(0, 0, api.SCREEN_W, PLAY_Y, C_HEADER, fill=True)
        d.text("SNAKE", 8, 9, C_TITLE, scale=2)
        score_str = "SCORE:%d" % self._score
        sx = api.SCREEN_W - len(score_str) * 8 * 2 - 6
        d.text(score_str, sx, 9, C_SCORE, scale=2)

    def _draw_title(self, d):
        if not self._dirty:
            return
        d.clear(C_BG)
        # header
        d.rect(0, 0, api.SCREEN_W, PLAY_Y, C_HEADER, fill=True)
        d.text("SNAKE", 8, 9, C_TITLE, scale=2)
        # big title
        d.text("SNAKE", 50, 100, C_HEAD, scale=4)
        # prompt
        d.text("press A to start", 20, 180, C_HINT, scale=2)
        d.text("arrow keys  move", 20, 210, C_HINT, scale=2)
        d.text("no 180 turns!", 36, 240, C_HINT, scale=2)
        self._dirty = False

    def _draw_playing(self, d):
        # Full redraw on first frame; afterwards incremental erase+draw
        # For simplicity and correctness on this small display we do a full
        # play-area clear each step.  At 10-20 moves/sec with 60fps rendering,
        # the display update is the bottleneck anyway.
        d.rect(0, PLAY_Y, api.SCREEN_W, PLAY_H, C_BG, fill=True)
        self._draw_header(d)

        # food
        fc, fr = self._food
        fx, fy = self._cell_rect(fc, fr)
        d.rect(fx + 1, fy + 1, CELL - 2, CELL - 2, C_FOOD, fill=True)

        # snake body (tail to neck, then head)
        for i in range(len(self._snake) - 1, 0, -1):
            c, r = self._snake[i]
            px, py = self._cell_rect(c, r)
            d.rect(px + 1, py + 1, CELL - 2, CELL - 2, C_BODY, fill=True)

        # head
        hc, hr = self._snake[0]
        hx, hy = self._cell_rect(hc, hr)
        d.rect(hx + 1, hy + 1, CELL - 2, CELL - 2, C_HEAD, fill=True)

    def _draw_gameover(self, d):
        # Freeze the board; overlay the game-over banner
        self._draw_playing(d)
        # semi-transparent overlay via a dark tinted band across centre
        d.rect(0, 120, api.SCREEN_W, 80, api.rgb(10, 5, 15), fill=True)
        d.rect(0, 120, api.SCREEN_W, 3,  C_GAMEOVER, fill=True)
        d.rect(0, 197, api.SCREEN_W, 3,  C_GAMEOVER, fill=True)

        d.text("GAME  OVER", 20, 130, C_GAMEOVER, scale=3)
        score_str = "SCORE: %d" % self._score
        # center the score text
        sx = (api.SCREEN_W - len(score_str) * 16) // 2
        d.text(score_str, sx, 164, api.WHITE, scale=2)

        d.text("A  restart", 64, 220, C_HINT, scale=2)
        d.text("HOME  menu", 60, 248, C_HINT, scale=2)
