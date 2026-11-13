"""Serial-synced advertisement scan with full manufacturer payload dump.

Watches the board serial for 'ble: -> ADVERTISING', then scans exactly
during the 1.5 s ADV window. Prints each captured CATCHME manufacturer
payload, classifying quest heartbeats (0xC5) vs discovery adverts (0xC6).

Usage: py -3 tools/scan_discovery_adv.py [max_hits] [timeout_s]
"""

import asyncio
import sys
import time
from collections import Counter

import serial
from bleak import BleakScanner


async def scan_window(seconds: float) -> list[str]:
    found: list[str] = []

    def cb(bd, adv):
        if bd.name and "CATCHME" in bd.name:
            for _mfr, val in (adv.manufacturer_data or {}).items():
                found.append(bytes(val).hex())

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    await asyncio.sleep(seconds)
    await scanner.stop()
    return found


def main() -> None:
    max_hits = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 120

    s = serial.Serial("COM5", 115200, timeout=0.2)
    hits: list[str] = []
    deadline = time.time() + timeout_s
    cycle = 0
    while time.time() < deadline and len(hits) < max_hits:
        line = s.readline().decode(errors="replace")
        if "-> ADVERTISING" in line:
            cycle += 1
            got = asyncio.run(scan_window(2.5))
            print(f"[cycle {cycle}] {got or '-'}", flush=True)
            hits += got
    s.close()

    print("\n=== captured payloads ===")
    for payload, n in Counter(hits).most_common():
        kind = "*** DISCOVERY 0xC6 ***" if payload.startswith("c6") else "HEARTBEAT 0xC5"
        print(f"{n:3d}x  {payload}  -> {kind}")
    if not hits:
        print("no payloads captured")


if __name__ == "__main__":
    main()
