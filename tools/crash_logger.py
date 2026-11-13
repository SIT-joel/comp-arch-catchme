"""Resilient crash logger: reconnects on USB glitch, logs to file 6h."""
import serial, sys, time

port = sys.argv[1]
outfile = sys.argv[2]
end = time.time() + 6 * 3600

while time.time() < end:
    try:
        s = serial.Serial(port, 115200, timeout=1)
        s.dtr = True
    except Exception as e:
        print(f"open failed: {e}", flush=True)
        time.sleep(5)
        continue
    print(f"[{time.strftime('%H:%M:%S')}] logging {port}", flush=True)
    while time.time() < end:
        try:
            line = s.readline().decode(errors="replace").rstrip()
            if line:
                stamp = time.strftime("%H:%M:%S")
                with open(outfile, "a", encoding="utf-8") as f:
                    f.write(f"[{stamp}] {line}\n")
        except Exception:
            with open(outfile, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] <<serial glitch, reopening>>\n")
            break
    s.close()
    time.sleep(3)
