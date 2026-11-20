"""The card's folders and the play queue (shuffle, repeat).

Folder listing and the whole-card scan touch the card, so they run on a
worker; the queue is pure.
"""

try:
    import os
except ImportError:  # pragma: no cover
    os = None

MAX_SCAN = 1000         # files in a whole-card queue
MAX_DEPTH = 8

REPEAT_OFF, REPEAT_ALL, REPEAT_ONE = 0, 1, 2
REPEAT_NAMES = ("off", "all", "one")


def is_mp3(name):
    return name.lower().endswith(".mp3") and not name.startswith("._")


def _is_dir(path, stat=None):
    try:
        st = (stat or os.stat)(path)
    except OSError:
        return False
    return bool(st[0] & 0x4000)


def list_dir(path, listdir=None, stat=None):
    """(folders, mp3 files) in path, each sorted case-insensitively,
    hidden entries left out."""
    listdir = listdir or os.listdir
    dirs, files = [], []
    for name in listdir(path):
        if name.startswith(".") or name == "System Volume Information":
            continue
        full = path.rstrip("/") + "/" + name
        if _is_dir(full, stat):
            dirs.append(name)
        elif is_mp3(name):
            files.append(name)
    dirs.sort(key=lambda s: s.lower())
    files.sort(key=lambda s: s.lower())
    return dirs, files


def scan(root, listdir=None, stat=None, limit=MAX_SCAN):
    """Every MP3 under root (folder order, then file order), at most limit."""
    out = []
    stack = [(root.rstrip("/") or "/", 0)]
    while stack and len(out) < limit:
        path, depth = stack.pop()
        try:
            dirs, files = list_dir(path, listdir, stat)
        except OSError:
            continue
        for f in files:
            out.append(path.rstrip("/") + "/" + f)
            if len(out) >= limit:
                break
        if depth < MAX_DEPTH:
            for d in reversed(dirs):
                stack.append((path.rstrip("/") + "/" + d, depth + 1))
    return out


def display_name(path):
    """'/sd/Artist/01 - Song.mp3' -> '01 - Song'."""
    name = path.rsplit("/", 1)[-1]
    return name[:-4] if name.lower().endswith(".mp3") else name


def _randbelow(n, rnd=None):
    if rnd is not None:
        return rnd(n)
    import random
    try:
        return random.randrange(n)
    except AttributeError:
        return random.getrandbits(16) % n


class Queue:
    """Items (paths or song dicts) played in order or shuffled, with repeat
    off / all / one. `order` is a permutation of item indexes."""

    def __init__(self, items, start=0, shuffle=False, repeat=REPEAT_OFF, rnd=None):
        self.items = list(items)
        self.repeat = repeat
        self.shuffle = False
        self._rnd = rnd
        self.order = list(range(len(self.items)))
        self.pos = max(0, min(start, len(self.items) - 1)) if self.items else 0
        if shuffle:
            self.set_shuffle(True)

    def __len__(self):
        return len(self.items)

    def current(self):
        if not self.items:
            return None
        return self.items[self.order[self.pos]]

    def set_shuffle(self, on):
        if not self.items or on == self.shuffle:
            self.shuffle = on
            return
        cur = self.order[self.pos]
        if on:
            rest = [i for i in range(len(self.items)) if i != cur]
            for i in range(len(rest) - 1, 0, -1):
                j = _randbelow(i + 1, self._rnd)
                rest[i], rest[j] = rest[j], rest[i]
            self.order = [cur] + rest
            self.pos = 0
        else:
            self.order = list(range(len(self.items)))
            self.pos = cur
        self.shuffle = on

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        return self.repeat

    def next(self, auto=False):
        """The item after this one (auto: the track ended), or None at the
        end with repeat off."""
        if not self.items:
            return None
        if auto and self.repeat == REPEAT_ONE:
            return self.current()
        if self.pos + 1 < len(self.order):
            self.pos += 1
        elif self.repeat != REPEAT_OFF or not auto:
            self.pos = 0
        else:
            return None
        return self.current()

    def prev(self):
        if not self.items:
            return None
        self.pos = (self.pos - 1) % len(self.order)
        return self.current()
