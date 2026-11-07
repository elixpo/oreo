"""BLE receive throughput benchmark, laptop side (Python + bleak).

    .venv/bin/pip install bleak
    .venv/bin/python tools/ble_bench/host.py              # memory and flash runs
    .venv/bin/python tools/ble_bench/host.py --size 1048576 --mode F

Start tools/ble_bench/badge.py on the badge first. Each run sends --size
bytes of incompressible data with write-without-response, never more than
--window bytes ahead of the badge's last credit (flow control, so no write
is silently dropped), and prints the badge-measured throughput.

A laptop is not a phone: phones usually allow fewer packets per
connection event (iOS especially), so expect phone numbers below these.
"""

import argparse
import asyncio
import os
import struct
import time

from bleak import BleakClient, BleakScanner

RX = "6f72656f-00b1-1000-8000-00805f9b34fb"
TX = "6f72656f-00b2-1000-8000-00805f9b34fb"


async def one_run(client, size, mode, chunk, window):
    credit = asyncio.Event()
    done = asyncio.get_running_loop().create_future()
    acked = [0]

    def on_notify(_, data):
        if data[:1] == b"C":
            acked[0] = struct.unpack(">I", data[1:5])[0]
            credit.set()
        elif data[:1] == b"D" and not done.done():
            done.set_result(struct.unpack(">III", data[1:13]))

    await client.start_notify(TX, on_notify)
    payload = os.urandom(size)
    await client.write_gatt_char(RX, b"H" + struct.pack(">I", size) + mode.encode(),
                                 response=True)
    t0 = time.perf_counter()
    sent = 0
    while sent < size:
        while sent - acked[0] >= window:
            credit.clear()
            await asyncio.wait_for(credit.wait(), 10)
        n = min(chunk, size - sent)
        await client.write_gatt_char(RX, payload[sent:sent + n], response=False)
        sent += n
    got, elapsed_us, flash_us = await asyncio.wait_for(done, 60)
    host_s = time.perf_counter() - t0
    await client.stop_notify(TX)
    kbs = got / 1024 / (elapsed_us / 1e6)
    print("mode %s  chunk %3d B  %7d B  badge %6.0f ms  %6.1f KB/s  (host %.1f s, flash %d ms)"
          % (mode, chunk, got, elapsed_us / 1000, kbs, host_s, flash_us // 1000))
    return kbs


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=262144)
    p.add_argument("--mode", choices=("M", "F", "both"), default="both")
    p.add_argument("--window", type=int, default=16384)
    args = p.parse_args()

    print("scanning for OreoBench ...")
    dev = await BleakScanner.find_device_by_name("OreoBench", timeout=15)
    if dev is None:
        raise SystemExit("OreoBench not found; is badge.py running?")
    async with BleakClient(dev) as client:
        char = client.services.get_characteristic(RX)
        limit = char.max_write_without_response_size
        print("connected; max write-without-response size %d B" % limit)
        chunks = sorted({c for c in (20, 180, 244, limit) if c <= limit})
        modes = ("M", "F") if args.mode == "both" else (args.mode,)
        for mode in modes:
            for chunk in chunks:
                await one_run(client, args.size, mode, chunk, args.window)
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
