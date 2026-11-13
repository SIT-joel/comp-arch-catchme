"""Scan continuously (keeps Windows cache fresh) while retrying connect."""
import asyncio, sys, time
from bleak import BleakScanner, BleakClient

ADDRESS = "01:80:E1:00:34:12"
HOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 50.0

async def main():
    scanner = BleakScanner()
    await scanner.start()
    print("background scanning; retrying connect every 5s...", flush=True)
    deadline = time.time() + 90
    client = None
    while time.time() < deadline and client is None:
        try:
            client = BleakClient(ADDRESS, timeout=10)
            await client.connect()
        except Exception:
            client = None
            await asyncio.sleep(5)
    if client is None:
        await scanner.stop()
        print("CONNECT FAILED within 90s")
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
        await scanner.stop()
        print("disconnected")

asyncio.run(main())
