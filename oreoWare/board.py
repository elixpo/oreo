"""Which Falera hardware this is: the breadboard badge or the PCB badge.

The PCB badge (circuit/elixpo/) has an AW9523B I2C expander at 0x58 on
GPIO6 (SDA) / GPIO7 (SCL); the breadboard badge has buttons on those pins.
board() reads the expander's chip-ID register once and caches the answer.
A held LEFT or RIGHT button on the breadboard can pull SDA or SCL low, but
it can't answer with the AW9523B's ID (0x23), so the check can't be fooled
into "pcb".

A file /board.txt holding "pcb" or "breadboard" overrides the check, for
bring-up or a board whose expander is not fitted yet.
"""

BREADBOARD = "breadboard"
PCB = "pcb"

AW9523_ADDR = 0x58
AW9523_ID_REG = 0x10
AW9523_ID = 0x23
PCB_SDA = 6
PCB_SCL = 7
OVERRIDE_FILE = "/board.txt"

_board = None


def _override():
    try:
        with open(OVERRIDE_FILE) as f:
            v = f.read().strip().lower()
    except Exception:
        return None
    return v if v in (BREADBOARD, PCB) else None


def _probe():
    try:
        from machine import Pin, SoftI2C
    except ImportError:
        return BREADBOARD           # the host: no hardware
    found = BREADBOARD
    try:
        # timeout: SoftI2C waits up to 50 ms by default for a held-low SCL
        # (on the breadboard, RIGHT held at boot, or a pin still floating
        # low), twice per probe; 1 ms keeps boot fast and changes nothing
        # on the PCB, whose expander never stretches the clock.
        i2c = SoftI2C(scl=Pin(PCB_SCL), sda=Pin(PCB_SDA), freq=100_000,
                      timeout=1000)
        # Two good reads: one stray 0x23 can't make a breadboard a PCB.
        if (i2c.readfrom_mem(AW9523_ADDR, AW9523_ID_REG, 1)[0] == AW9523_ID and
                i2c.readfrom_mem(AW9523_ADDR, AW9523_ID_REG, 1)[0] == AW9523_ID):
            found = PCB
    except Exception:
        pass
    if found == BREADBOARD:
        # Hand the pins back as plain inputs: on the breadboard they are
        # LEFT and RIGHT, which oreoWare.buttons sets up next.
        try:
            Pin(PCB_SDA, Pin.IN, Pin.PULL_UP)
            Pin(PCB_SCL, Pin.IN, Pin.PULL_UP)
        except Exception:
            pass
    return found


def board():
    """"pcb" or "breadboard", decided once per boot."""
    global _board
    if _board is None:
        _board = _override() or _probe()
    return _board


def is_pcb():
    return board() == PCB
