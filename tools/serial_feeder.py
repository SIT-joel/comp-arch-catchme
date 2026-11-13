"""Open COM5 at 9600 (unblocks the vendor example's wait-for-host), then
write test bytes every 3 s so the example notifies them over BLE."""
import time
import serial

s = serial.Serial("COM5", 9600, timeout=1)
s.dtr = True
s.write(b"NOTIFYTEST\n")
n = 0
while n < 40:
    time.sleep(3)
    s.write(b"nt-%d\n" % n)
    n += 1
    try:
        data = s.read(256)
        if data:
            print("board:", data.decode(errors="replace").strip(), flush=True)
    except Exception:
        pass
s.close()
