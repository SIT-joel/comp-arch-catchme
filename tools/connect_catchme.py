"""Connect the PC to CATCHME-1 and hold the link; print GATT services found."""
import asyncio, sys, time
from bleak import BleakScanner, BleakClient

HOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0

async def main():
    print(f"searching for CATCHME-1 ({HOLD:.0f}s hold planned)...", flush=True)
    device = await BleakScanner.find_device_by_name("CATCHME-1", timeout=25)
    if device is None:
        print("NOT FOUND within 25s")
        return
    print(f"found {device.address}; connecting...", flush=True)
    async with BleakClient(device) as client:
        print(f"CONNECTED: {client.is_connected}", flush=True)
        for service in client.services:
            print(f"  service {service.uuid}")
            for ch in service.characteristics:
                print(f"    char {ch.uuid} props={ch.properties}")
        t0 = time.time()
        while time.time() - t0 < HOLD:
            await asyncio.sleep(1)
            print(f"still connected at {time.time()-t0:.0f}s", flush=True)
    print("disconnected cleanly")

asyncio.run(main())
