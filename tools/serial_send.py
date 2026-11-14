"""Send a bench trigger line to a board and print its serial output.

Usage: python serial_send.py <port> <line> [read_seconds]
Used for bench triggers (QANS n / RAID / CARE / PETWIPE) when the crash
logger is not holding the port. Board 2 stays under the logger; board 1's
port is driven on demand during E2E validation.
"""
import serial
import sys
import time

port = sys.argv[1]
line = sys.argv[2]
read_s = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0

s = serial.Serial(port, 115200, timeout=0.5)
s.dtr = True
time.sleep(0.2)
s.write((line + "\n").encode())
end = time.time() + read_s
while time.time() < end:
    data = s.readline().decode(errors="replace").strip()
    if data:
        print(data, flush=True)
s.close()
