"""Catch CATCHME-1 via detection callback, then connect and hold."""
import asyncio, sys, time
from bleak import BleakScanner, BleakClient

HOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0

async def main():
    found: asyncio.Future = asyncio.Future()

    def on_detect(device, adv):
        name = (adv.local_name or device.name or "").upper()
        if "CATCHME" in name and not found.done():
            found.set_result(device)

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    print("scanning for CATCHME-1...", flush=True)
    try:
        device = await asyncio.wait_for(found, timeout=30)
    except asyncio.TimeoutError:
        await scanner.stop()
        print("NOT SEEN in 30s")
        return
    await scanner.stop()
    print(f"seen {device.address}, connecting...", flush=True)
    client = BleakClient(device, timeout=25)
    try:
        await client.connect()
    except Exception as exc:
        print(f"connect failed: {exc!r}")
        return
    try:
        print(f"CONNECTED: {client.is_connected}", flush=True)
        for service in client.services:
            print(f"  service {service.uuid}")
            for ch in service.characteristics:
                print(f"    char {ch.uuid} props={ch.properties}")
        t0 = time.time()
        while time.time() - t0 < HOLD:
            await asyncio.sleep(1)
        print(f"held link for {HOLD:.0f}s")
    finally:
        await client.disconnect()
        print("disconnected")

asyncio.run(main())
