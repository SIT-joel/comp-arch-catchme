"""Dump full advertisement data of the wearable (return_adv mode).
Usage: py -3 dump_adv.py [seconds]"""
import asyncio
import sys
import bleak

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
TARGET = "01:80:E1:00:34:12"

async def main():
    devs = await bleak.BleakScanner.discover(timeout=secs, return_adv=True)
    hit = devs.get(TARGET)
    if hit is None:
        print("board NOT seen")
        for addr, (d, adv) in devs.items():
            print("other:", addr, (d.name or "")[:16],
                  "mfr", {hex(k): v.hex() for k, v in adv.manufacturer_data.items()})
        return
    d, adv = hit
    print("name:", d.name)
    print("rssi:", adv.rssi if hasattr(adv, "rssi") else "?")
    print("mfr:", {hex(k): v.hex() for k, v in adv.manufacturer_data.items()})
    print("service_uuids:", adv.service_uuids)
    print("platform_data:", adv.platform_data)

asyncio.run(main())
