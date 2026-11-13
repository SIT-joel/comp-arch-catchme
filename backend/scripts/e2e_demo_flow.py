"""End-to-end demo flow over real HTTP against a running local server.

Proof script (not a test): signs in both seeded users, binds devices, runs a
demo 'together' quest to completion with mutual peer observations, checks the
awards, and purchases a badge. Prints each step's outcome.
"""

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "http://127.0.0.1:8000/api/v1"
T0 = datetime.now(timezone.utc) - timedelta(seconds=90)


def call(method: str, path: str, token: str | None = None, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data) as resp:
            text = resp.read().decode()
            return resp.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def main(user_a, pass_a, user_b, pass_b):
    _, a = call("POST", "/auth/login", body={"username": user_a, "password": pass_a})
    _, b = call("POST", "/auth/login", body={"username": user_b, "password": pass_b})
    ta, tb = a["token"], b["token"]
    print(f"1. login ok: {a['user']['display_name']} + {b['user']['display_name']}")

    _, me_a = call("GET", "/me", ta)
    if me_a["device"] is None:
        status, out = call("POST", "/devices/bind", ta, {"pairing_code": "PAIR-CODE-A"})
        print(f"2a. bind A: {status} -> {out['device']['name']}")
        _, me_a = call("GET", "/me", ta)
    _, me_b = call("GET", "/me", tb)
    if me_b["device"] is None:
        status, out = call("POST", "/devices/bind", tb, {"pairing_code": "PAIR-CODE-B"})
        print(f"2b. bind B: {status} -> {out['device']['name']}")
        _, me_b = call("GET", "/me", tb)
    device_a, device_b = me_a["device"], me_b["device"]
    print(f"2. devices: {device_a['name']} / {device_b['name']}")

    call("POST", "/sessions/00000000-0000-4000-8000-000000000000/cancel", ta)  # noop warmup
    _, created = call("POST", "/sessions", ta, {"quest_id": "together", "demo": True})
    sid = created["id"]
    print(f"3. session created: {sid} state={created['state']}")

    _, accepted = call("POST", f"/sessions/{sid}/accept", tb)
    token = accepted["token"]
    print(f"4. accepted: state={accepted['state']} target_ms={accepted['target_ms']}")

    def rec(seq, t, peer_device, heartbeat):
        return {
            "boot_id": f"boot-{peer_device['firmware_alias']}",
            "sequence": seq,
            "session_id": sid,
            "uptime_ms": int(t * 1000),
            "captured_at": (T0 + timedelta(seconds=t)).isoformat().replace("+00:00", "Z"),
            "clock": {"source": "phone_server_anchor", "uncertainty_ms": 300},
            "gps": {"valid": False, "latitude": None, "longitude": None, "fix_age_ms": None},
            "heart_rate": {"valid": False, "bpm": None, "status": "no_contact"},
            "peer": {
                "observed": True,
                "device_id": peer_device["id"],
                "boot_id": f"boot-{peer_device['firmware_alias']}",
                "heartbeat_sequence": heartbeat,
                "session_token": token,
                "observation_age_ms": 0,
            },
        }

    seq = 0
    for t in range(0, 32, 2):
        seq += 1
        call("POST", "/telemetry/batches", ta,
             {"schema_version": 1, "device_id": device_a["id"], "records": [rec(seq, t, device_b, seq)]})
        call("POST", "/telemetry/batches", tb,
             {"schema_version": 1, "device_id": device_b["id"], "records": [rec(seq, t, device_a, seq)]})
    print(f"5. pushed {seq} mutual observation pairs")

    _, final = call("GET", f"/sessions/{sid}", ta)
    print(f"6. session state={final['state']} progress_ms={final['progress_ms']}")

    _, me_a = call("GET", "/me", ta)
    _, me_b = call("GET", "/me", tb)
    print(f"7. awards: A {me_a['user']['points']}pts/{me_a['user']['lifetime_xp']}xp/L{me_a['user']['level']}"
          f"  B {me_b['user']['points']}pts/{me_b['user']['lifetime_xp']}xp/L{me_b['user']['level']}")

    key = f"e2e-{sid[:8]}"
    status, purchase = call("POST", "/purchases", ta, {"reward_id": "first_spark"}, {"Idempotency-Key": key})
    print(f"8. purchase first_spark: {status} balance={purchase.get('balance_after')}")

    status, replay = call("POST", "/purchases", ta, {"reward_id": "first_spark"}, {"Idempotency-Key": key})
    print(f"9. idempotent replay: {status} balance={replay.get('balance_after')}")

    _, state = call("GET", f"/devices/{device_a['id']}/state", ta)
    print(f"10. device state relay: completion={state.get('completion', {}).get('completion_event_id')}"
          f" partner_alias={state.get('partner_alias')}")

    ok = (
        final["state"] == "completed"
        and me_a["user"]["points"] == 100
        and me_b["user"]["lifetime_xp"] == 100
        and purchase.get("balance_after") == 50
        and replay.get("balance_after") == 50
    )
    print("E2E RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(*(sys.argv[1:] or ["miya", "devpass-a", "toma", "devpass-b"]))
