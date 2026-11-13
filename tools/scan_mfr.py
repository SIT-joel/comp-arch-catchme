"""Print CATCHME's raw manufacturer data bytes across several advertise windows."""
import asyncio, time
from bleak import BleakScanner

hits = []

def on_detect(device, adv):
    if "CATCHME" in (adv.local_name or device.name or "").upper():
        hits.append((round(time.time() % 1000, 1), adv.rssi, dict(adv.manufacturer_data or {})))

async def main():
    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    await asyncio.sleep(25)
    await scanner.stop()
    for t, rssi, mfr in hits[:20]:
        decoded = {cid: bytes(b).hex() for cid, b in mfr.items()}
        print(f"t={t} rssi={rssi} mfr={decoded}")
    print(f"total {len(hits)} hits")

asyncio.run(main())
