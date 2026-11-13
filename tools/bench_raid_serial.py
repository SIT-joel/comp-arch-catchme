"""Hardware bench: co-op raid fight via the serial RAID trigger.

Opens BOTH serials FIRST (no blind window), sends "RAID\\n" to both boards
(twice, in case a boot-spew byte poisoned the trigger line buffer), then
captures. Expected flow:
  raid: mode ON (TDD suspended)          both boards
  raid: connected - fight starts         board 1 (host, after peer connect)
  raid: FIGHT!                           both
  raid: fight over, won=<0|1>            board 1 (host terminates)
  raid: fight over (client view)         board 2
  raid: outcome ACKed by the phone       both (needs a signed-in phone link)

PASS = connection formed, FIGHT on both, outcomes on both, zero watchdog
resets. (Outcome ACK requires the phone relay path — separate bench.)

Usage: backend/.venv/Scripts/python.exe tools/bench_raid_serial.py [duration_s=120]
"""

import re
import sys
import threading
import time

import serial

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 120
PORTS = {"board1": "COM3", "board2": "COM4"}  # board1=host/central, board2=client


def main():
    ser = {}
    for name, port in PORTS.items():
        ser[name] = serial.Serial(port, 115200, timeout=0.5)
        ser[name].dtr = True
        ser[name].reset_input_buffer()

    lines = {n: [] for n in PORTS}
    stop = threading.Event()

    def watch(name):
        s = ser[name]
        while not stop.is_set():
            try:
                line = s.readline().decode(errors="replace").rstrip()
                if line:
                    lines[name].append(
                        f"[{time.strftime('%H:%M:%S')}] {line}")
            except Exception:
                # Board reset / USB re-enumeration: poll for the port to
                # return (Windows re-assigns the same number here) so the
                # boot-reason line is captured.
                time.sleep(0.5)
                for _ in range(30):
                    if stop.is_set():
                        return
                    try:
                        s.close()
                        s = serial.Serial(PORTS[name], 115200, timeout=0.5)
                        s.dtr = True
                        lines[name].append(f"[{time.strftime('%H:%M:%S')}] <<reopened {PORTS[name]}>>")
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    return

    watchers = [threading.Thread(target=watch, args=(n,), daemon=True) for n in PORTS]
    for t in watchers:
        t.start()

    time.sleep(1)
    # Clear any boot-spue garbage in the trigger line buffer with a bare
    # newline, then send the trigger twice.
    for name in PORTS:
        ser[name].write(b"\n")
        ser[name].flush()
    time.sleep(0.5)
    for name in PORTS:
        ser[name].write(b"RAID\n")
        ser[name].flush()
        print(f"trigger sent to {name}", flush=True)

    time.sleep(DURATION)
    stop.set()
    time.sleep(1)

    def hits(name, needle):
        return [l for l in lines[name] if needle in l]

    ok = True
    for name in PORTS:
        with open(f"tools/bench_raid_last_{name}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines[name]))
        print(f"--- {name} ({len(lines[name])} lines) ---", flush=True)
        for needle in [
            "raid: mode ON",
            "raid: connected",
            "raid: FIGHT",
            "raid: fight over",
            "raid: outcome ACKed",
            "raid: link lost mid-fight",
            "raid: connect timeout",
            "raid: resuming TDD",
        ]:
            for h in hits(name, needle)[:2]:
                print(f"  {h}")
        resets = len(re.findall(r"boot reason: WATCHDOG", "\n".join(lines[name])))
        if resets:
            ok = False
            print(f"  WATCHDOG RESETS: {resets}")

    b1, b2 = lines["board1"], lines["board2"]
    # Exact match: "raid: connected — fight starts" (em dash) — the plain
    # "raid: connected" substring also hits "ble: disconnected".
    connected = any("fight starts" in l for l in b1)
    fought = any("raid: FIGHT" in l for l in b1) and any("raid: FIGHT" in l for l in b2)
    outcome = any("fight over" in l for l in b1) and any("fight over" in l for l in b2)
    print(f"\nVERDICT: {'PASS' if connected and fought and outcome and ok else 'INCOMPLETE'} "
          f"connected={connected} fought={fought} outcomes={outcome} resets_ok={ok}")
    return 0 if connected and fought and outcome and ok else 1


if __name__ == "__main__":
    sys.exit(main())
