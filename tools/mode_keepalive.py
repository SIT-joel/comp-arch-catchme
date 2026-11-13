"""Periodically re-assert board 2's discovery mode over GATT (TEST TOOL).

Board 2 has no flash shield, so its discovery mode lives only in RAM and
any reboot silently disarms it. This loop re-sends DISCOVERY_MODE every
two minutes; the wearable ACKs each apply. Product path remains the phone
link (docs/DISCOVERY_PLAN.md); this keeps the bench demo state stable.

Usage: py -3 tools/mode_keepalive.py   (run in background)
"""

import asyncio
import subprocess
import sys
import time

ARGS = [sys.executable, "tools/discovery_mode_relay.py",
        "02:80:E1:00:34:12", "1", "61495"]

print("mode keepalive: re-asserting board 2 discovery every 120s", flush=True)
while True:
    try:
        r = subprocess.run(ARGS, capture_output=True, text=True, timeout=90)
        if "ACK RECEIVED" in r.stdout:
            print(f"[{time.strftime('%H:%M:%S')}] mode re-asserted (ACK)", flush=True)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] no ack (board busy?)", flush=True)
    except Exception as exc:
        print("keepalive error:", exc, flush=True)
    time.sleep(120)
