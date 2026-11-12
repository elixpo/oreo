"""oreo: the command-line tool for the Elixpo Oreo Badge.

Finds the badge by its USB ID (303a:83ec) and drives OreoOS over
MicroPython's raw REPL, using mpremote's serial transport as a library.
"""

__version__ = "1.1.0"

# USB identity of the badge's native port (espressif/usb-pids#425).
OREO_VID = 0x303A
OREO_PID = 0x83EC
