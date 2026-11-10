"""Serial link to the badge, on mpremote's transport (used as a library).

`SerialLink` is the only class in the CLI that touches a serial port. It
opens lazily: building one does nothing until `open()`, so `--help`, `devs`
and unreachable badges never disturb the hardware.

Interface used by `badge.Badge` (and implemented by the test FakeTransport):

    enter()                              stop OreoOS, raw REPL, soft reset
    exec(code, timeout, consumer) -> b   run code, stream stdout to consumer
    restart(mode)                        "soft" | "hard" | "none"; then close
    close()
"""

import os
import sys
import time

from .errors import BadgeError, OreoError

RAW_BANNER = b"raw REPL; CTRL-B to exit\r\n"


def _import_mpremote():
    try:
        from mpremote.transport import TransportError
        from mpremote.transport_serial import SerialTransport
    except ImportError:
        raise OreoError("mpremote is not installed",
                        hint="pip install 'mpremote>=1.28,<1.29' (or reinstall oreo-cli)")
    return SerialTransport, TransportError


def explain_open_failure(device):
    """Why a port would not open, as (message, hint)."""
    if os.name != "nt" and not os.path.exists(device):
        return ("%s does not exist" % device,
                "the badge was unplugged or renumbered; run `oreo devs`")
    if os.name != "nt" and not os.access(device, os.R_OK | os.W_OK):
        if sys.platform.startswith("linux"):
            return ("no permission to open %s" % device,
                    "add yourself to the serial group, then log out and back in: "
                    "sudo usermod -aG dialout $USER  (Arch: uucp)")
        return ("no permission to open %s" % device, "run `oreo doctor`")
    return ("could not open %s" % device,
            "another program has it open (Thonny, mpremote, a serial monitor, "
            "another `oreo`); close it and try again")


class SerialLink:
    def __init__(self, device, baudrate=115200):
        self.device = device
        self.baudrate = baudrate
        self.t = None
        self._have_prompt = False   # we already read the raw REPL '>' prompt
        self._busy = False          # code sent (or being sent) and not finished
        self.mounted = False

    # ── lifecycle ────────────────────────────────────────────────────
    def open(self):
        if self.t is not None:
            return self
        SerialTransport, TransportError = _import_mpremote()
        try:
            self.t = SerialTransport(self.device, baudrate=self.baudrate)
        except (TransportError, OSError):
            msg, hint = explain_open_failure(self.device)
            raise OreoError(msg, hint=hint)
        return self

    def enter(self, soft_reset=True):
        """Interrupt OreoOS and enter the raw REPL (soft reset: clean heap,
        main.py does not run while we are in the raw REPL)."""
        self.open()
        _, TransportError = _import_mpremote()
        try:
            self.t.enter_raw_repl(soft_reset=soft_reset)
        except (TransportError, OSError) as e:
            raise OreoError("the badge did not answer on %s (%s)" % (self.device, e),
                            hint="unplug and replug the badge, then run `oreo doctor`")
        self._have_prompt = False
        self._busy = False

    def close(self):
        if self.t is None:
            return
        try:
            self.t.close()
        except Exception:
            pass
        self.t = None

    def restart(self, mode="soft"):
        """Leave OreoOS running again, then close the port."""
        if self.t is None:
            return
        try:
            if self._busy and self.t.in_raw_repl:
                self._recover()
            if self.mounted:
                try:
                    if self.t.in_raw_repl:
                        self._resync()
                    else:   # leaving `oreo dev`'s REPL: same as mpremote's disconnect
                        self.t.enter_raw_repl(soft_reset=False)
                        self._have_prompt = False
                    self.t.umount_local()
                except Exception:
                    pass
                self.mounted = False
            if mode == "hard":
                if not self.t.in_raw_repl:
                    self.t.enter_raw_repl(soft_reset=False)
                    self._have_prompt = False
                self._send(b"import machine\nmachine.reset()\n")
            else:
                if self.t.in_raw_repl:
                    self.t.exit_raw_repl()           # ctrl-B: friendly REPL
                    time.sleep(0.05)
                if mode == "soft":
                    self.t.serial.write(b"\x04")     # ctrl-D: soft reboot -> main.py
                    time.sleep(0.2)
        except Exception:
            pass
        finally:
            self.close()

    def _recover(self, quiet=0.15, limit=2.0):
        """Back to a clean raw REPL prompt after an exec was cut short (Ctrl-C
        on the host, a timeout) while the badge was still reading the code
        or running it.

        Ctrl-C ends a raw paste without compiling it, interrupts running
        code, or clears a half-sent line in the plain raw REPL. Without it
        the bytes restart() sends next would be read as more of the paste,
        and the soft reset would never happen."""
        ser = self.t.serial
        ser.write(b"\x03\x03")
        start = last = time.monotonic()
        while time.monotonic() - last < quiet and time.monotonic() - start < limit:
            n = ser.inWaiting()
            if n:
                ser.read(n)
                last = time.monotonic()
            else:
                time.sleep(0.01)
        self.t.enter_raw_repl(soft_reset=False)   # ctrl-A: banner + '>' again
        self._have_prompt = False
        self._busy = False

    # ── raw REPL execution ───────────────────────────────────────────
    def _resync(self):
        """Hand the link back to mpremote's own helpers in a known state:
        the '>' prompt unread (re-sent by ctrl-A in raw REPL)."""
        if self._have_prompt:
            self.t.serial.write(b"\x01")
            self.t.read_until(1, RAW_BANNER, timeout=5)
            self._have_prompt = False

    def _send(self, code):
        """mpremote's exec_raw_no_follow, aware of a prompt we already read."""
        _, TransportError = _import_mpremote()
        ser = self.t.serial
        if not self._have_prompt:
            data = self.t.read_until(1, b">", timeout=10)
            if not data.endswith(b">"):
                raise OreoError("the badge is not at the raw REPL prompt",
                                hint="unplug and replug the badge")
        self._have_prompt = False
        if self.t.use_raw_paste:
            ser.write(b"\x05A\x01")
            data = ser.read(2)
            if data == b"R\x01":
                try:
                    self.t.raw_paste_write(code)
                except TransportError as e:
                    raise OreoError("transfer to the badge failed: %s" % e)
                return
            if data != b"R\x00":
                data = self.t.read_until(1, b"w REPL; CTRL-B to exit\r\n>")
                if not data.endswith(b"w REPL; CTRL-B to exit\r\n>"):
                    raise OreoError("the badge left the raw REPL")
            self.t.use_raw_paste = False
        for i in range(0, len(code), 256):
            ser.write(code[i:i + 256])
            time.sleep(0.01)
        ser.write(b"\x04")
        if ser.read(2) != b"OK":
            raise OreoError("the badge refused the command")

    def _follow(self, timeout, consumer):
        """Read stdout up to the first EOF and stderr up to the second, in
        bulk (mpremote's follow() reads one byte per call)."""
        ser = self.t.serial
        out, err = bytearray(), bytearray()
        stage = 0
        last = time.monotonic()
        while stage < 2:
            n = ser.inWaiting()
            if not n:
                if timeout is not None and time.monotonic() - last > timeout:
                    raise OreoError("the badge stopped answering (%ss without output)" % timeout,
                                    hint="it may be busy; unplug and replug if it stays stuck")
                time.sleep(0.003)
                continue
            data = ser.read(n)
            last = time.monotonic()
            while data and stage < 2:
                i = data.find(b"\x04")
                part = data if i < 0 else data[:i]
                if stage == 0:
                    out += part
                    if consumer and part:
                        consumer(bytes(part))
                else:
                    err += part
                if i < 0:
                    data = b""
                else:
                    data = data[i + 1:]
                    stage += 1
            if stage == 2 and data.startswith(b">"):
                self._have_prompt = True
        return bytes(out), bytes(err)

    def exec(self, code, timeout=15, consumer=None):
        if self.t is None or not self.t.in_raw_repl:
            self.enter()
        elif self._busy:     # the previous exec was cut short (Ctrl-C)
            self._recover()
        if isinstance(code, str):
            code = code.encode("utf-8")
        self._busy = True
        self._send(code)
        out, err = self._follow(timeout, consumer)
        self._busy = False
        if err:
            text = err.decode("utf-8", "replace")
            last = text.strip().splitlines()[-1] if text.strip() else "error"
            raise BadgeError("the badge raised %s" % last, detail=text)
        return out

    def interrupt(self):
        if self.t is not None:
            self.t.serial.write(b"\x03")

    # ── interactive helpers (shell, dev) ─────────────────────────────
    def mount(self, path):
        """Mount a host folder at /remote with mpremote's remote filesystem."""
        if self.t is None or not self.t.in_raw_repl:
            self.enter()
        self._resync()
        self.t.mount_local(path)
        self.mounted = True

    def friendly(self):
        """Switch to the friendly REPL for an interactive session."""
        if self.t is not None and self.t.in_raw_repl:
            self._resync()
            self.t.exit_raw_repl()
            self._have_prompt = False
