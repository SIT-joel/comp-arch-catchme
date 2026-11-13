"""External observation of the wearable's BLE advertisements via the PC adapter.

Verifies: (a) CATCHME-1 is visible to a third-party BLE host, (b) sightings
follow the board's 4 s advertise / 4 s scan alternation windows, (c) the
manufacturer data payload (0xC5 magic + heartbeat) matches the firmware spec
once the main app advertises it (the current probe advertises its name only).
"""
import asyncio
import sys
import time

from bleak import BleakScanner

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 16.0

sightings: list[tuple[float, str, int, dict]] = []
total_devices: set[str] = set()


def on_detect(device, advertisement_data):
    total_devices.add(device.address)
    name = advertisement_data.local_name or device.name or ""
    if "CATCHME" in name.upper():
        sightings.append(
            (
                time.time(),
                name,
                advertisement_data.rssi,
                dict(advertisement_data.manufacturer_data or {}),
            )
        )


async def main() -> None:
    scanner = BleakScanner(detection_callback=on_detect)
    t0 = time.time()
    await scanner.start()
    await asyncio.sleep(SECONDS)
    await scanner.stop()

    print(f"scan window: {SECONDS:.0f}s, distinct BLE devices seen: {len(total_devices)}")
    if not sightings:
        print("CATCHME-*: NOT SEEN — board not advertising during this window")
        return
    print(f"CATCHME sightings: {len(sightings)}")
    prev = None
    for ts, name, rssi, mfr in sightings:
        gap = f" +{ts - prev:5.2f}s" if prev else "        "
        prev = ts
        print(f"t={ts - t0:6.2f}s{gap} {name} rssi={rssi} mfr={mfr if mfr else '-'}")


asyncio.run(main())
