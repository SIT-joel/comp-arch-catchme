"""Dump N seconds of board serial output. Usage: py -3 dump_serial.py [seconds]"""
import sys
import time
import serial

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
s = serial.Serial("COM5", 115200, timeout=0.2)
s.dtr = True
t0 = time.time()
while time.time() - t0 < secs:
    line = s.readline().decode(errors="replace").rstrip()
    if line:
        print(line, flush=True)
s.close()
