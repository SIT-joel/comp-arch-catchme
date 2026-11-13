"""Dump every BLE advertisement the PC hears with names/addresses/RSSI."""
import asyncio, sys, time
from bleak import BleakScanner

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
seen: dict[str, list] = {}

def on_detect(device, adv):
    name = adv.local_name or device.name or ""
    entry = seen.setdefault(device.address, [])
    if not entry or entry[-1][0] != name or entry[-1][1] != adv.rssi:
        entry.append((name, adv.rssi, round(time.time(), 2)))

async def main():
    scanner = BleakScanner(detection_callback=on_detect)
    t0 = time.time()
    await scanner.start()
    await asyncio.sleep(SECONDS)
    await scanner.stop()
    print(f"window {SECONDS:.0f}s, {len(seen)} distinct addresses:")
    for addr, entries in sorted(seen.items()):
        names = {e[0] for e in entries}
        rssi_min = min(e[1] for e in entries)
        rssi_max = max(e[1] for e in entries)
        count = len(entries)
        print(f"{addr}  hits={count:3d} rssi={rssi_min}..{rssi_max} names={sorted(n for n in names if n) or '-'}")

asyncio.run(main())
