"""Keep `adb reverse tcp:8000 tcp:8000` applied to every connected phone
transport.

Wireless adb transports flap (mDNS re-registrations rotate ports), and each
flap silently kills the phone's tunnel to the dev server. This watchdog
re-applies the reverse mapping to all connected devices every few seconds.

Usage: py -3 tools/reverse_keepalive.py [port]   (run in background)
"""

import subprocess
import sys
import time

ADB = r"C:\Users\Joell\AppData\Local\Android\Sdk\platform-tools\adb.exe"
PORT = sys.argv[1] if len(sys.argv) > 1 else "8000"


def transports() -> list[str]:
    out = subprocess.run([ADB, "devices"], capture_output=True, text=True,
                         timeout=10).stdout
    serials = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device" and "emulator" not in parts[0]:
            serials.append(parts[0])
    return serials


def main() -> None:
    print(f"reverse keepalive on port {PORT}; Ctrl+C to stop", flush=True)
    while True:
        for serial in transports():
            subprocess.run(
                [ADB, "-s", serial, "reverse", f"tcp:{PORT}", f"tcp:{PORT}"],
                capture_output=True, timeout=10)
        time.sleep(4)


if __name__ == "__main__":
    main()
