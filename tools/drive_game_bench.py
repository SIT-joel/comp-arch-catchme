"""v2 raid gate experiment driver: board-to-board BLE connection gate.

Per run: flashes the CM_GAME_GATE builds to both boards (the flash itself
resets each board, restarting the gate flow), watches both serials, scores
the GATE: RESULT line, and checks for watchdog resets.

Gate PASS criteria (docs/QUEST_INTERACTION_PLAN.md):
  - connection established within 10 s of the create attempt
  - >= 900 writes delivered in the 120 s window (10 Hz minus slack)
  - zero watchdog resets on either board during the run
  - clean disconnect afterwards

Usage:
  backend/.venv/Scripts/python.exe tools/drive_game_bench.py COM4 COM3 [runs=3]
  (COM4 = board 1 / central, COM3 = board 2 / peripheral)
"""

import re
import subprocess
import sys
import threading
import time

import serial

CENTRAL_PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
PERIPH_PORT = sys.argv[2] if len(sys.argv) > 2 else "COM3"
RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
WINDOW_S = 170  # boot+5 s arm + 120 s write window + slack

ARDUINO = ["tools/arduino-cli/bin/arduino-cli.exe", "--config-file",
           "tools/arduino-cli/arduino-cli.yaml"]
BUILD = {1: "tools/build/gate_d1", 2: "tools/build/gate_d2"}
FQBN = "TinyCircuits:samd:tinyscreen"


def flash_gate(port, device_id):
    """Touch bootloader, upload the gate build (upload resets the board)."""
    subprocess.run(
        ["backend/.venv/Scripts/python.exe", "tools/touch_bootloader.py", port],
        capture_output=True, text=True, timeout=60,
    )
    time.sleep(4)
    out = subprocess.run(
        ARDUINO + ["board", "list"], capture_output=True, text=True, timeout=60,
    ).stdout
    ports = [ln.split()[0] for ln in out.splitlines()
             if ln.startswith("COM") and "Unknown" not in ln and "COM1" not in ln]
    if port not in ports:
        # After the touch the board re-enumerates on a new port.
        candidates = [p for p in ports if p not in (CENTRAL_PORT, PERIPH_PORT)]
        if device_id == 1 and port == CENTRAL_PORT:
            port = candidates[0] if candidates else port
        else:
            port = candidates[-1] if candidates else port
    r = subprocess.run(
        ARDUINO + ["upload", "--fqbn", FQBN, "--input-dir", BUILD[device_id],
                   "-p", port, "--verify"],
        capture_output=True, text=True, timeout=180,
    )
    ok = "New upload port" in r.stdout or r.returncode == 0
    print(f"  flash board {device_id} -> {port}: {'OK' if ok else 'FAIL'}", flush=True)
    return port


def watch(port, duration_s, lines):
    try:
        s = serial.Serial(port, 115200, timeout=0.5)
        s.dtr = True
    except Exception as e:
        print(f"  serial {port} failed: {e}", flush=True)
        return
    t0 = time.time()
    while time.time() - t0 < duration_s:
        line = s.readline().decode(errors="replace").rstrip()
        if line:
            lines.append(line)
    s.close()


def run_once(idx):
    print(f"=== gate run {idx + 1}/{RUNS} ===", flush=True)
    # Flash both gate builds (each upload resets its board -> gate restarts).
    flash_gate(CENTRAL_PORT, 1)
    flash_gate(PERIPH_PORT, 2)
    time.sleep(2)

    a_lines, b_lines = [], []
    ta = threading.Thread(target=watch, args=(CENTRAL_PORT, WINDOW_S, a_lines))
    tb = threading.Thread(target=watch, args=(PERIPH_PORT, WINDOW_S, b_lines))
    ta.start(); tb.start(); ta.join(); tb.join()

    text = "\n".join(a_lines + b_lines)
    result = re.search(r"GATE: RESULT connect_ms=(\d+) writes=(\d+) duration_ms=(\d+)", text)
    resets = len(re.findall(r"boot reason: WATCHDOG", text))
    rx = re.findall(r"adv on cnt=(\d+)", "\n".join(b_lines))
    if not result:
        print("  VERDICT: INCOMPLETE - no GATE: RESULT line captured", flush=True)
        print("  central tail:", a_lines[-4:] if a_lines else "(none)", flush=True)
        print("  peripheral advert count:", rx[-1] if rx else "(none)", flush=True)
        return False
    connect_ms, writes, duration_ms = (int(g) for g in result.groups())
    ok = connect_ms <= 10_000 and writes >= 900 and duration_ms >= 115_000 and resets == 0
    print(
        f"  VERDICT: {'PASS' if ok else 'FAIL'} connect_ms={connect_ms} writes={writes} "
        f"duration_ms={duration_ms} watchdog_resets={resets} "
        f"peripheral_adv_cnt={rx[-1] if rx else '?'}",
        flush=True,
    )
    return ok


def main():
    passed = 0
    for idx in range(RUNS):
        if run_once(idx):
            passed += 1
        else:
            break  # a failing run stops the series; diagnose first
    print(f"\nGATE SERIES: {passed}/{RUNS} passed")
    print("Next: clean disconnect verified; reconnect the phones and confirm relink.")
    return 0 if passed == RUNS else 1


if __name__ == "__main__":
    sys.exit(main())
