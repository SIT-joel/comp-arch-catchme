"""Watch OTA BLE for N seconds, reporting any device seen each round.
Usage: py -3 watch_ota.py [rounds]"""
import asyncio
import sys
import bleak

rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 4

async def main():
    for r in range(rounds):
        devs = await bleak.BleakScanner.discover(timeout=3.0)
        names = [(d.address, (d.name or "")[:16]) for d in devs]
        print(f"round {r}: {names}", flush=True)

asyncio.run(main())
