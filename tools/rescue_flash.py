"""Rescue flash: race the rebooting WDT-test build after a USB power cycle.

The test sketch reboots every ~16 s (WDT persists across soft resets; only
a power-on reset clears it). After replug, its setup() waits 20 s for a
serial host BEFORE re-enabling the watchdog — that is the clean window.

Waits for the sketch port (PID 8009), touches 1200 baud, polls hard for
the bootloader (PID 8008), and uploads immediately when it appears.

Usage: py -3 tools/rescue_flash.py <build_dir>
"""

import serial
import serial.tools.list_ports
import subprocess
import sys
import time

BUILD = sys.argv[1] if len(sys.argv) > 1 else "tools/build/catch_me_disc"
UPLOAD = [
    "tools/arduino-cli/bin/arduino-cli.exe",
    "--config-file", "tools/arduino-cli/arduino-cli.yaml",
    "upload", "--fqbn", "TinyCircuits:samd:tinyscreen",
    "--input-dir", BUILD,
]


def find(pid_fragment: str) -> str | None:
    for p in serial.tools.list_ports.comports():
        if pid_fragment in p.hwid:
            return p.device
    return None


def touch_dtr_less(port: str) -> None:
    """Trigger the CDC bootloader reset WITHOUT asserting DTR.

    The core's SerialUSB truth is DTR-based (CDC.cpp: lineState > 0), so a
    DTR-less open never makes the sketch believe a host is listening — the
    running sketch stays in its serial-attach wait and never reaches its
    watchdog init. The core arms the bootloader jump on any
    SET_(LINE_CODING|CONTROL_LINE_STATE) while baud==1200 with DTR clear
    (classic auto-reset); we force that with an RTS toggle at DTR=0.
    """
    s = serial.Serial()
    s.port = port
    s.baudrate = 1200
    s.dtr = False   # applied on open: SET_CONTROL_LINE_STATE with DTR=0
    s.rts = False
    s.open()
    time.sleep(0.05)
    s.rts = True    # another control-line-state packet, DTR still 0
    time.sleep(0.05)
    s.close()


def main() -> None:
    print("waiting for sketch port (8009)...", flush=True)
    sketch = None
    while sketch is None:
        sketch = find("8009")
        if sketch is None:
            time.sleep(0.05)
    print(f"sketch on {sketch}; DTR-less bootloader touch", flush=True)
    try:
        touch_dtr_less(sketch)
    except Exception as exc:
        print("touch failed:", exc)
        sys.exit(1)

    t0 = time.time()
    while time.time() - t0 < 12:
        for p in serial.tools.list_ports.comports():
            if "8008" in p.hwid:
                print(f"bootloader on {p.device} after {time.time()-t0:.2f}s; uploading", flush=True)
                port = p.device
                result = subprocess.run(UPLOAD + ["-p", port], capture_output=True, text=True)
                out = (result.stdout + result.stderr).strip().splitlines()
                print("\n".join(out[-3:]))
                sys.exit(0 if result.returncode == 0 else 2)
        time.sleep(0.05)
    print("no bootloader window; rerun the script")
    sys.exit(1)


if __name__ == "__main__":
    main()
