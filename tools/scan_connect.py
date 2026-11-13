"""Scan until the wearable is seen, then connect immediately and hold.
Robust against stale Windows BLE caches (see win-dev-env-quirks)."""
import asyncio
import bleak

ADDRESS = "01:80:E1:00:34:12"
HOLD = 12.0


async def main():
    print("scanning for the board...", flush=True)
    device = None
    for attempt in range(6):
        device = await bleak.BleakScanner.find_device_by_address(ADDRESS, timeout=4.0)
        if device:
            break
        print(f"  not seen (attempt {attempt + 1})", flush=True)
    if not device:
        print("BOARD NOT FOUND in 24s of scanning", flush=True)
        return
    print("seen! connecting...", flush=True)
    client = bleak.BleakClient(device)
    try:
        await client.connect(timeout=8.0)
        print(f"CONNECTED: {client.is_connected}", flush=True)
        services = client.services
        for s in services:
            print(" service", s.uuid, flush=True)
        await asyncio.sleep(HOLD)
    except Exception as exc:
        print("connect failed:", repr(exc), flush=True)
    finally:
        try:
            await client.disconnect()
            print("disconnected", flush=True)
        except Exception:
            pass


asyncio.run(main())
