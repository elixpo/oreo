"""BLE receive throughput benchmark, badge side (MicroPython).

Run it in place of OreoOS for one session (nothing is installed):

    .venv/bin/mpremote connect /dev/ttyACM0 run tools/ble_bench/badge.py

then run tools/ble_bench/host.py on a laptop. Reset the badge afterwards
to return to OreoOS.

Protocol (a dedicated service, so it never collides with the OS's
"oreo" file service):
  RX  write / write-without-response, host -> badge
      first write of a run: b"H" + u32 total + u8 mode ("M" memory, "F" flash)
      then raw payload bytes until total have arrived
  TX  notify, badge -> host
      b"C" + u32 received   credit, every CREDIT_BYTES
      b"D" + u32 received + u32 elapsed_us + u32 flash_us   at the end

The IRQ handler only accumulates bytes; flash writes (mode "F") happen in
the main loop, as a real receiver should do them.
"""

import bluetooth
import struct
import time
from micropython import const

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)

CREDIT_BYTES = const(8192)
RX_BUFFER = const(4096)   # characteristic buffer, append mode

SVC = bluetooth.UUID("6f72656f-00b0-1000-8000-00805f9b34fb")
RX = (bluetooth.UUID("6f72656f-00b1-1000-8000-00805f9b34fb"),
      bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE)
TX = (bluetooth.UUID("6f72656f-00b2-1000-8000-00805f9b34fb"),
      bluetooth.FLAG_NOTIFY)

ble = bluetooth.BLE()
ble.active(True)
ble.config(gap_name="OreoBench", mtu=512)
((rx_handle, tx_handle),) = ble.gatts_register_services(((SVC, (RX, TX)),))
ble.gatts_set_buffer(rx_handle, RX_BUFFER, True)

state = {
    "conn": None, "total": 0, "got": 0, "mode": b"M", "start": 0,
    "next_credit": CREDIT_BYTES, "pending": [], "done": False,
}


def notify(payload):
    if state["conn"] is not None:
        try:
            ble.gatts_notify(state["conn"], tx_handle, payload)
        except OSError:
            pass


def irq(event, data):
    if event == _IRQ_CENTRAL_CONNECT:
        state["conn"] = data[0]
        print("connected")
    elif event == _IRQ_CENTRAL_DISCONNECT:
        state["conn"] = None
        print("disconnected")
        advertise()
    elif event == _IRQ_MTU_EXCHANGED:
        print("mtu", data[1])
    elif event == _IRQ_GATTS_WRITE and data[1] == rx_handle:
        chunk = ble.gatts_read(rx_handle)
        if state["total"] == 0 or state["done"]:
            if len(chunk) >= 6 and chunk[0:1] == b"H":
                state["total"] = struct.unpack(">I", chunk[1:5])[0]
                state["mode"] = chunk[5:6]
                state["got"] = 0
                state["next_credit"] = CREDIT_BYTES
                state["pending"] = []
                state["done"] = False
                state["start"] = time.ticks_us()
                chunk = chunk[6:]   # append mode can merge payload bytes in
            if not chunk:
                return
        state["got"] += len(chunk)
        if state["mode"] == b"F":
            state["pending"].append(chunk)
        if state["got"] >= state["next_credit"] and state["got"] < state["total"]:
            state["next_credit"] += CREDIT_BYTES
            notify(b"C" + struct.pack(">I", state["got"]))


def advertise():
    name = b"OreoBench"
    adv = bytes((2, 0x01, 0x06, len(name) + 1, 0x09)) + name
    ble.gap_advertise(100_000, adv_data=adv)


ble.irq(irq)
advertise()
print("OreoBench advertising; run tools/ble_bench/host.py on the laptop")

flash_us = 0
f = None
while True:
    if state["mode"] == b"F" and state["pending"]:
        if f is None:
            f = open("/ble_bench.bin", "wb")
        t0 = time.ticks_us()
        while state["pending"]:
            f.write(state["pending"].pop(0))
        flash_us += time.ticks_diff(time.ticks_us(), t0)
    if state["total"] and not state["done"] and state["got"] >= state["total"] \
            and not state["pending"]:
        if f is not None:
            t0 = time.ticks_us()
            f.close()
            flash_us += time.ticks_diff(time.ticks_us(), t0)
            f = None
        elapsed = time.ticks_diff(time.ticks_us(), state["start"])
        state["done"] = True
        notify(b"D" + struct.pack(">III", state["got"], elapsed, flash_us))
        print("run: %d bytes in %d ms = %.1f KB/s (flash %d ms)" % (
            state["got"], elapsed // 1000,
            state["got"] / 1024 / (elapsed / 1e6), flash_us // 1000))
        flash_us = 0
    time.sleep_ms(2)
