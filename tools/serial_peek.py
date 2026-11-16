import sys
import time

from serial import Serial

port = sys.argv[1]
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
s = Serial(port, 115200, timeout=1)
if len(sys.argv) > 3 and sys.argv[3] == "--reset":
    s.setDTR(False)
    time.sleep(0.05)
    s.setDTR(True)   # toggle resets the SAMD21
    time.sleep(0.05)
    s.setDTR(False)
s.setDTR(False)  # do not reset the board
end = time.time() + seconds
while time.time() < end:
    line = s.readline().decode(errors="replace").strip()
    if line:
        print(line, flush=True)
