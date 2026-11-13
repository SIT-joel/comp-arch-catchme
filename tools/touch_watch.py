"""Open the sketch port at 115200, keep reading, touch 1200 baud on a
second handle, and print everything that happens for 8 s. Tells us whether
the 1200 touch resets the board at all (fresh boot banner) and whether a
bootloader window follows."""

import serial
import serial.tools.list_ports
import threading
import time

lines = []
stop = False


def reader():
    global stop
    try:
        s = serial.Serial("COM5", 115200, timeout=0.2)
    except Exception as e:
        print("reader open fail:", e)
        return
    while not stop:
        try:
            line = s.readline().decode(errors="replace").rstrip()
            if line:
                lines.append((time.time(), line))
        except Exception as e:
            lines.append((time.time(), f"<read error: {e}>"))
            try:
                s.close()
            except Exception:
                pass
            time.sleep(0.3)
            try:
                s = serial.Serial("COM5", 115200, timeout=0.2)
            except Exception:
                pass
    try:
        s.close()
    except Exception:
        pass


t = threading.Thread(target=reader)
t.start()
time.sleep(2.0)
t0 = time.time()
print("--- touching 1200 ---")
try:
    s = serial.Serial("COM5", 1200)
    time.sleep(0.05)
    s.close()
except Exception as e:
    print("touch error:", e)
while time.time() - t0 < 8:
    time.sleep(0.1)
stop = True
t.join(timeout=2)
for ts, line in lines:
    print(f"[{ts - t0:+6.2f}s] {line[:80]}")
print("--- ports now ---")
for p in serial.tools.list_ports.comports():
    print(p.device, p.hwid)
