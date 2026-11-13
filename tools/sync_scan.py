"""Scan the PC BLE radio synchronized with the board's ADV windows.

Watches the board serial for 'ble: -> ADVERTISING', then immediately runs a
short bleak discovery covering the 1.5 s advertisement window.
"""
import asyncio
import time
import serial
import bleak

def scan_once(results):
    async def run():
        devs = await bleak.BleakScanner.discover(timeout=2.5)
        results.append([(d.address, (d.name or "")[:16]) for d in devs])
    asyncio.run(run())

def main():
    s = serial.Serial("COM5", 115200, timeout=0.2)
    s.dtr = True
    for cycle in range(4):
        t0 = time.time()
        saw_adv = False
        while time.time() - t0 < 10:
            line = s.readline().decode(errors="replace").strip()
            if "-> ADVERTISING" in line:
                saw_adv = True
                break
        if saw_adv:
            print(f"[cycle {cycle}] ADV entered, scanning 2.5s...", flush=True)
            results = []
            scan_once(results)
            print("  scan:", results[-1], flush=True)
        else:
            print(f"[cycle {cycle}] no ADV window in 10s", flush=True)
    s.close()

main()
