"""The microSD card: 1-bit SDMMC on pins.SD_CLK / SD_CMD / SD_D0 (GPIO 38 /
39 / 40 on both badges), mounted at /sd.

On the PCB badge the card-detect switch is the AW9523B's P1_5
(pins.EXP_SD_DET, low = card in), so present() answers without touching
the card. The breadboard's breakout has no detect line: present() is None
(unknown) and mount() simply tries.

    sd = os.sdcard
    if sd.present() is not False:
        path = sd.mount()       # "/sd", or None (no card, unreadable)
    ...
    sd.unmount()

mount() takes a few hundred milliseconds (the card's power-up and the FAT
mount), so call it from a worker (oreoOS.cache.Refresh), never in draw().
"""

from oreoWare import pins

PATH = "/sd"
FREQ = 20_000_000


class SDCard:
    def __init__(self, expander=None, sdcard_class=None, vfs_module=None):
        self._exp = expander
        self._cls = sdcard_class
        self._vfs = vfs_module
        self._card = None
        self.path = None
        self.error = None

    def _expander(self):
        if self._exp is None and getattr(pins, "EXPANDER", False):
            try:
                from oreoWare import aw9523
                self._exp = aw9523.get()
            except Exception:
                self._exp = None
        return self._exp

    def present(self):
        """True / False from the card-detect switch, None when the board
        has none (breadboard)."""
        exp = self._expander()
        if exp is None:
            return None
        try:
            return bool(exp.card_present())
        except Exception:
            return None

    def mounted(self):
        return self.path is not None

    def _vfs_mod(self):
        if self._vfs is not None:
            return self._vfs
        try:
            import vfs
            return vfs
        except ImportError:
            import os
            return os

    def mount(self):
        """Mount the card at PATH; returns PATH, or None with self.error."""
        if self.path is not None:
            return self.path
        if self.present() is False:
            self.error = "no card"
            return None
        try:
            cls = self._cls
            if cls is None:
                from machine import SDCard as cls       # noqa: N813
            card = cls(slot=1, width=1, sck=pins.SD_CLK, cmd=pins.SD_CMD,
                       data=(pins.SD_D0,), freq=FREQ)
            self._vfs_mod().mount(card, PATH)
        except Exception as e:
            self.error = str(e) or "card unreadable"
            try:
                card.deinit()
            except Exception:
                pass
            return None
        self._card = card
        self.path = PATH
        self.error = None
        return PATH

    def unmount(self):
        if self.path is None:
            return
        try:
            self._vfs_mod().umount(PATH)
        except Exception:
            pass
        try:
            self._card.deinit()
        except Exception:
            pass
        self._card = None
        self.path = None


_sd = None


def get():
    global _sd
    if _sd is None:
        _sd = SDCard()
    return _sd
