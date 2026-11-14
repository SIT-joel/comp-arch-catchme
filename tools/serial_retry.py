"""Send a bench trigger repeatedly until the board accepts it.

Usage: python serial_retry.py <port> <line> [max_tries]
The board's TDD cycle leaves the phone link up only ~5 s of every ~10 s;
a single-shot trigger can land in the disconnected window. Retries with
1.5 s gaps until the response lacks the refusal message.
"""
import serial
import sys
import time

port = sys.argv[1]
line = sys.argv[2]
max_tries = int(sys.argv[3]) if len(sys.argv) > 3 else 10

s = serial.Serial(port, 115200, timeout=0.5)
s.dtr = True
time.sleep(0.2)
for attempt in range(1, max_tries + 1):
    s.write((line + "\n").encode())
    end = time.time() + 2.0
    out = []
    while time.time() < end:
        data = s.readline().decode(errors="replace").strip()
        if data:
            out.append(data)
            print(data, flush=True)
    joined = "\n".join(out)
    if "NOT sent" not in joined and "fail" not in joined.lower():
        print(f"[accepted on try {attempt}]", flush=True)
        break
    time.sleep(1.5)
s.close()
