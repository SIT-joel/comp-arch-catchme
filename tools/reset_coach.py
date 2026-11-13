"""Reset coach for board 1 (FIXTURE tool): beep when the board reboots.

Watches for board 1's sketch port (USB serial FB3F8F) to re-appear after a
drop. Every appearance = the board just rebooted = the bootloader's 500 ms
double-tap window is open RIGHT NOW. Beeps loudly so the user can land the
second reset click inside the window.

Usage: py -3 tools/reset_coach.py [minutes]   (default 15)
"""

import sys
import time
import winsound

import serial.tools.list_ports

SERIAL = "FB3F8F"


def board1_port():
    for p in serial.tools.list_ports.comports():
        if SERIAL in p.hwid:
            return p.device
    return None


def beep(pattern):
    for freq, ms in pattern:
        winsound.Beep(freq, ms)


def main() -> None:
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 15
    print(f"COACH: beeping on every board-1 reboot for {minutes:.0f} min.", flush=True)
    print("On each beep burst: CLICK THE RESET BUTTON AGAIN IMMEDIATELY.", flush=True)
    t0 = time.time()
    seen = False
    resets = 0
    while time.time() - t0 < minutes * 60:
        present = board1_port() is not None
        if present and not seen:
            resets += 1
            print(f"[{time.time()-t0:+6.1f}s] RESET #{resets} - CLICK NOW", flush=True)
            beep([(2000, 120), (2500, 120), (3000, 120)])
        seen = present
        time.sleep(0.03)
    print(f"coach done ({resets} reboots seen)")


if __name__ == "__main__":
    main()
