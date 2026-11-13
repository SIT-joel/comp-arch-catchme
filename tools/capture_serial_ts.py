"""Timestamped serial capture: each board line prefixed with host wall-clock."""
import sys, time
import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
out = open(sys.argv[3], "w", encoding="utf-8") if len(sys.argv) > 3 else None

def emit(line: str):
    stamp = f"{time.time():.3f}"
    print(f"[{stamp}] {line}", flush=True)
    if out:
        out.write(f"[{stamp}] {line}\n")
        out.flush()

ser = None
for attempt in range(8):
    try:
        ser = serial.Serial(port, 115200, timeout=0.5)
        break
    except Exception as exc:
        emit(f"open attempt {attempt+1} failed: {exc}")
        time.sleep(1.5)
if ser is None:
    sys.exit(2)

deadline = time.time() + seconds
while time.time() < deadline:
    line = ser.readline().decode(errors="replace").strip()
    if line:
        emit(line)
ser.close()
