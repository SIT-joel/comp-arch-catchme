"""Open the port at 1200 baud (Arduino SAMD bootloader touch), then watch
for a port re-enumeration (bootloader PID 03EB:8008)."""
import sys, time
import serial, serial.tools.list_ports

port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
try:
    s = serial.Serial(port, 1200)
    print("1200bps open OK -> touch sent", flush=True)
    s.close()
except Exception as exc:
    print("1200bps open FAILED:", exc, flush=True)
    sys.exit(1)

before = {p.device: p.hwid for p in serial.tools.list_ports.comports()}
deadline = time.time() + 15
while time.time() < deadline:
    now = {p.device: p.hwid for p in serial.tools.list_ports.comports()}
    if now != before:
        print("PORTS CHANGED:", {d: h for d, h in now.items() if before.get(d) != h}, flush=True)
        sys.exit(0)
    time.sleep(0.5)
print("no re-enumeration within 15s", flush=True)
