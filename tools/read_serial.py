import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0

ser = None
for attempt in range(10):
    try:
        ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=1)
        break
    except Exception as exc:  # noqa: BLE001 - report and retry
        print(f"open attempt {attempt + 1} failed: {exc}", flush=True)
        time.sleep(1.5)

if ser is None:
    sys.exit(2)

deadline = time.time() + seconds
try:
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line:
            print(line, flush=True)
finally:
    ser.close()
