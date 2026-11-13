"""Connect to the wearable by known address; hold; print services."""
import asyncio, sys, time
from bleak import BleakClient

ADDRESS = sys.argv[1] if len(sys.argv) > 1 else "01:80:E1:00:34:12"
HOLD = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0

async def main():
    print(f"connecting to {ADDRESS}...", flush=True)
    client = BleakClient(ADDRESS, timeout=30)
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
