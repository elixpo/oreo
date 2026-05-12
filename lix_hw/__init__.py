"""Hardware backend for the Lix badge (runs on the device under stock MicroPython).

Implements the ABCs from `lix.api`. Apps and the OS should not import from here directly;
they import `lix` and receive backend instances via the `OS` object.
"""
