"""Watch for serial-port changes; report only real additions/removals/PID flips."""
import time
import serial.tools.list_ports

def snapshot():
    return {p.device: p.hwid for p in serial.tools.list_ports.comports()}

last = snapshot()
print("baseline:", last, flush=True)
deadline = time.time() + 600
while time.time() < deadline:
    time.sleep(1.5)
    now = snapshot()
    if now != last:
        added = {d: h for d, h in now.items() if last.get(d) != h}
        removed = {d: h for d, h in last.items() if d not in now}
        if added:
            print("ADDED/CHANGED:", added, flush=True)
        if removed:
            print("REMOVED:", removed, flush=True)
        last = now
print("watch window ended", flush=True)
