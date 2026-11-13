"""Automated end-to-end feature sweep over the live dev API.

Stands in for wearable button input by submitting PINs through the API, so
every server-side quest/shop/discovery path can be exercised without physical
button entry. Telemetry injected here uses clearly labeled FIXTURE boot ids
(AGENTS.md fixture rule) and can never be presented as hardware evidence.

Usage: backend/.venv/Scripts/python.exe tools/test_feature_sweep.py [base_url]
Requires the dev server + seeded accounts miya/devpass-a and toma/devpass-b.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASS = {"miya": "devpass-a", "toma": "devpass-b"}

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (" — " + str(detail) if detail else ""), flush=True)


def call(method, path, token=None, body=None, expect=None, headers=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            code, data = r.status, json.load(r)
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            data = json.load(e)
        except Exception:
            data = {}
    if expect is not None and code != expect:
        raise AssertionError(f"{method} {path} -> {code}, expected {expect}: {data}")
    return code, data


def login(username):
    _, data = call("POST", "/api/v1/auth/login", body={"username": username, "password": PASS[username]}, expect=200)
    return data["token"]


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def fixture_record(seq, t_offset, *, session_id, peer_device, token, boot):
    """Clearly labeled fixture telemetry record (FIXTURE boot id)."""
    return {
        "boot_id": boot,
        "sequence": seq,
        "session_id": session_id,
        "uptime_ms": t_offset * 1000,
        "captured_at": iso(datetime.now(timezone.utc) + timedelta(seconds=120 + t_offset)),
        "clock": {"source": "phone_server_anchor", "uncertainty_ms": 500},
        "gps": {"valid": False, "latitude": None, "longitude": None, "fix_age_ms": None},
        "heart_rate": {"valid": False, "bpm": None, "status": "no_contact"},
        "peer": {
            "observed": True,
            "device_id": peer_device,
            "boot_id": "fixture-peer-boot",
            "heartbeat_sequence": seq,
            "session_token": token,
            "observation_age_ms": 0,
        },
    }


def main():
    tok_a, tok_b = login("miya"), login("toma")
    _, me_a = call("GET", "/api/v1/me", tok_a, expect=200)
    _, me_b = call("GET", "/api/v1/me", tok_b, expect=200)
    dev_a = me_a["device"]["id"]
    dev_b = me_b["device"]["id"]
    xp_a0, xp_b0 = me_a["user"]["lifetime_xp"], me_b["user"]["lifetime_xp"]
    pts_a0, pts_b0 = me_a["user"]["points"], me_b["user"]["points"]
    print(f"devices: a={dev_a} b={dev_b}; a pts/xp={pts_a0}/{xp_a0} b pts/xp={pts_b0}/{xp_b0}")

    # Self-heal: if a previous run ended the partnership, restore it first.
    code, _ = call("GET", "/api/v1/me/partnership", tok_a)
    if code == 404:
        print("partnership missing — restoring via profile+invitation")
        for tok in (tok_a, tok_b):
            call("PUT", "/api/v1/me/discovery-profile", tok, body={
                "display_name": "Miya" if tok is tok_a else "Toma",
                "age": 25, "pref_min_age": 18, "pref_max_age": 99,
                "radius_m": 500, "interests": ["gaming", "music"]}, expect=200)
            call("PUT", "/api/v1/me/discovery-settings", tok,
                 body={"bluetooth_enabled": True, "gps_enabled": True}, expect=200)
        code, inv = call("POST", "/api/v1/invitations", tok_a,
                         body={"to_user_id": me_b["user"]["id"]}, expect=201)
        call("POST", f"/api/v1/invitations/{inv['id']}/accept", tok_b, body={}, expect=200)
        print("partnership restored")

    # Cancel any leftover pending/active sessions so the sweep starts clean.
    _, existing = call("GET", "/api/v1/sessions", tok_a, expect=200)
    for s_old in existing.get("sessions", []):
        if s_old.get("state") in ("pending", "active"):
            call("POST", f"/api/v1/sessions/{s_old['id']}/cancel", tok_a, body={}, expect=200)
            print(f"cancelled leftover session {s_old['id']} ({s_old.get('state')})")

    # --- Together: start PIN -> fixture evidence -> end PIN -> awards ---
    _, s = call("POST", "/api/v1/sessions", tok_a, body={"quest_id": "together", "demo": True}, expect=201)
    sid = s["id"]
    _, acc = call("POST", f"/api/v1/sessions/{sid}/accept", tok_b, expect=200)
    check("together: accept -> active", acc.get("state") == "active")

    _, ia = call("GET", f"/api/v1/sessions/{sid}/interaction", tok_a, expect=200)
    _, ib = call("GET", f"/api/v1/sessions/{sid}/interaction", tok_b, expect=200)
    check("together: start stage + codes issued", ia["stage"] == ib["stage"] == "start" and ia["own_code"] and ib["own_code"])
    # owner-only exposure: the snapshot must not contain the PARTNER's code
    # (partner_code_version is a legitimate field; only the code value leaks)
    check("together: partner code not leaked",
          ib["own_code"] not in json.dumps(ia) and ia["own_code"] not in json.dumps(ib))

    session_token = acc.get("token") or ""
    check("together: session token exposed to participants", bool(session_token))

    import uuid
    _, sub_a = call("POST", f"/api/v1/sessions/{sid}/interaction/pin/submit", tok_a,
                    body={"stage": "start", "pin": ib["own_code"], "code_version": ib["own_code_version"],
                          "command_id": str(uuid.uuid4())}, expect=200)
    _, sub_b = call("POST", f"/api/v1/sessions/{sid}/interaction/pin/submit", tok_b,
                    body={"stage": "start", "pin": ia["own_code"], "code_version": ia["own_code_version"],
                          "command_id": str(uuid.uuid4())}, expect=200)
    _, ia2 = call("GET", f"/api/v1/sessions/{sid}/interaction", tok_a, expect=200)
    check("together: start PINs accepted -> timing phase", ia2["phase"] == "timing", ia2["phase"])

    # Wrong-code submission must be rejected and counted (on a fresh stage this
    # is covered by the suite; here verify the phase refuses to advance).
    code, wrong = call("POST", f"/api/v1/sessions/{sid}/interaction/pin/submit", tok_a,
                       body={"stage": "start", "pin": "0000", "code_version": ib["own_code_version"],
                             "command_id": str(uuid.uuid4())})
    check("together: stale-stage wrong PIN rejected", code in (409, 422), code)

    # Fixture evidence: mutual observations every 2 s for 30 s (16 points),
    # matching the suite's 30 s demo-target arithmetic. Boot ids carry a run
    # stamp so reruns don't collide with prior runs' ingested sequences.
    run_stamp = int(time.time())
    boot_a, boot_b = f"FIXTURE-sweep-a-{run_stamp}", f"FIXTURE-sweep-b-{run_stamp}"
    for seq in range(0, 16):
        t = seq * 2.0
        call("POST", "/api/v1/telemetry/batches", tok_a, body={
            "schema_version": 1, "device_id": dev_a,
            "records": [fixture_record(seq, t, session_id=sid, peer_device=dev_b,
                                       token=session_token, boot=boot_a)]}, expect=200)
        call("POST", "/api/v1/telemetry/batches", tok_b, body={
            "schema_version": 1, "device_id": dev_b,
            "records": [fixture_record(seq, t, session_id=sid, peer_device=dev_a,
                                       token=session_token, boot=boot_b)]}, expect=200)
    # duplicate replay must not double-count
    call("POST", "/api/v1/telemetry/batches", tok_a, body={
        "schema_version": 1, "device_id": dev_a,
        "records": [fixture_record(15, 30.0, session_id=sid, peer_device=dev_b,
                                   token=session_token, boot=boot_a)]}, expect=200)
    _, st = call("GET", f"/api/v1/sessions/{sid}", tok_a, expect=200)
    check("together: 30 s evidence accrued", st.get("progress_ms") == 30000, st.get("progress_ms"))

    _, ia3 = call("GET", f"/api/v1/sessions/{sid}/interaction", tok_a, expect=200)
    _, ib3 = call("GET", f"/api/v1/sessions/{sid}/interaction", tok_b, expect=200)
    check("together: end stage reached (no award yet)",
          ia3["phase"] == ib3["phase"] == "end_pin" and st.get("state") == "active",
          (ia3.get("phase"), ib3.get("phase"), st.get("state")))
    call("POST", f"/api/v1/sessions/{sid}/interaction/pin/submit", tok_a,
         body={"stage": "end", "pin": ib3["own_code"], "code_version": ib3["own_code_version"],
               "command_id": str(uuid.uuid4())}, expect=200)
    call("POST", f"/api/v1/sessions/{sid}/interaction/pin/submit", tok_b,
         body={"stage": "end", "pin": ia3["own_code"], "code_version": ia3["own_code_version"],
               "command_id": str(uuid.uuid4())}, expect=200)
    _, done = call("GET", f"/api/v1/sessions/{sid}", tok_a, expect=200)
    check("together: completed after both end PINs", done.get("state") == "completed", done.get("state"))

    _, ma = call("GET", "/api/v1/me", tok_a, expect=200)
    _, mb = call("GET", "/api/v1/me", tok_b, expect=200)
    check("award: exactly +100 pts/+100 XP each",
          ma["user"]["points"] == pts_a0 + 100 and ma["user"]["lifetime_xp"] == xp_a0 + 100
          and mb["user"]["points"] == pts_b0 + 100 and mb["user"]["lifetime_xp"] == xp_b0 + 100,
          (ma["user"]["points"] - pts_a0, ma["user"]["lifetime_xp"] - xp_a0,
           mb["user"]["points"] - pts_b0, mb["user"]["lifetime_xp"] - xp_b0))

    # --- Shop (use whichever user has an affordable unowned badge) ---
    code, rewards_a = call("GET", "/api/v1/rewards", tok_a, expect=200)
    rewards_a = rewards_a if isinstance(rewards_a, list) else rewards_a.get("rewards", rewards_a)
    check("shop: rewards listed with owned flags", len(rewards_a) >= 3,
          [(r["id"], r["price"], r.get("owned")) for r in rewards_a])
    buyer_tok, buyer_pts0, buyer_xp0, buyer_label = tok_a, pts_a0, xp_a0, "miya"
    affordable_unowned = [r for r in rewards_a if not r.get("owned") and r["price"] <= 100]
    if not affordable_unowned:
        code, rewards_b = call("GET", "/api/v1/rewards", tok_b, expect=200)
        rewards_b = rewards_b if isinstance(rewards_b, list) else rewards_b.get("rewards", rewards_b)
        affordable_unowned = [r for r in rewards_b if not r.get("owned") and r["price"] <= 100]
        buyer_tok, buyer_pts0, buyer_xp0, buyer_label = tok_b, pts_b0, xp_b0, "toma"
    if not affordable_unowned:
        check("shop: affordable unowned badge available", False, "both users own all affordable badges")
    else:
        cheap = min(affordable_unowned, key=lambda r: r["price"])
        key = str(uuid.uuid4())
        idem = {"Idempotency-Key": key}
        _, p1 = call("POST", "/api/v1/purchases", buyer_tok, body={"reward_id": cheap["id"]}, expect=201, headers=idem)
        bal_after_buy = p1["balance_after"]
        code, p2 = call("POST", "/api/v1/purchases", buyer_tok, body={"reward_id": cheap["id"]}, headers=idem)
        check("shop: idempotent replay (no double charge)",
              code in (200, 201) and p2["balance_after"] == bal_after_buy,
              (code, p2["balance_after"]))
        cost = cheap["price"]
        check("shop: balance reduced by price once", bal_after_buy == buyer_pts0 + 100 - cost,
              (bal_after_buy, buyer_pts0 + 100 - cost))
        # one-time ownership: same reward with a NEW key must 409 already_owned
        code, owned = call("POST", "/api/v1/purchases", buyer_tok,
                           body={"reward_id": cheap["id"]},
                           headers={"Idempotency-Key": str(uuid.uuid4())})
        check("shop: already-owned rejected", code == 409, (code, owned))
        # insufficient points: pick any reward priced above the current balance
        code, me3 = call("GET", "/api/v1/me", buyer_tok, expect=200)
        too_much = [r for r in rewards_a + rewards_b if r["price"] > me3["user"]["points"]]
        if too_much:
            code, _ = call("POST", "/api/v1/purchases", buyer_tok,
                           body={"reward_id": too_much[0]["id"]},
                           headers={"Idempotency-Key": str(uuid.uuid4())})
            check("shop: insufficient points rejected", code in (402, 409), code)
        else:
            check("shop: insufficient points rejected", True, "balance covers all rewards; skipped")
        _, mbuyer = call("GET", "/api/v1/me", buyer_tok, expect=200)
        check("shop: XP never reduced by spending", mbuyer["user"]["lifetime_xp"] == buyer_xp0 + 100,
              mbuyer["user"]["lifetime_xp"])

    # --- v2: the heart quest is removed (covered by the v2 checks below) ---
    code, err = call("POST", "/api/v1/sessions", tok_a, body={"quest_id": "heart_challenge", "demo": True})
    check("v2: heart quest cannot be created", code == 422, (code, err))

    # --- Explore: geofence unset -> honest 409 at creation (documented) ---
    code, e = call("POST", "/api/v1/sessions", tok_a, body={"quest_id": "explore", "demo": True})
    check("explore: honest 409 without configured geofence",
          code == 409 and e.get("error", {}).get("code") == "geofence_not_configured", (code, e))

    # --- Discovery round-trip (API level): end pair -> settings -> invite -> restore ---
    code, _ = call("DELETE", "/api/v1/me/partnership", tok_a, body={})
    check("discovery: partnership ended explicitly", code in (200, 204), code)
    _, dset = call("GET", "/api/v1/me/discovery", tok_a, expect=200)
    check("discovery: list reachable after unpair", isinstance(dset, (list, dict)))
    # complete discovery profiles (invitations require them)
    for tok in (tok_a, tok_b):
        call("PUT", "/api/v1/me/discovery-profile", tok, body={
            "display_name": "Miya" if tok is tok_a else "Toma",
            "age": 25, "pref_min_age": 18, "pref_max_age": 99,
            "radius_m": 500, "interests": ["gaming", "music"]}, expect=200)
        call("PUT", "/api/v1/me/discovery-settings", tok,
             body={"bluetooth_enabled": True, "gps_enabled": True}, expect=200)
    check("discovery: profiles completed + opted in", True)
    # re-pair via invitation (contract: {"to_user_id": ...})
    code, inv = call("POST", "/api/v1/invitations", tok_a, body={"to_user_id": me_b["user"]["id"]}, expect=201)
    check("discovery: invitation created", code == 201, (code, inv))
    iid = (inv or {}).get("id")
    if iid:
        code2, pair = call("POST", f"/api/v1/invitations/{iid}/accept", tok_b, body={})
        check("discovery: invitation accepted -> partnership restored", code2 == 200, (code2, pair))
    _, part = call("GET", "/api/v1/me/partnership", tok_a, expect=200)
    check("discovery: active partnership present again", bool(part), str(part)[:80])


    # --- v2: pet daily care, phone GPS source, raid flow, heart rejection ---
    print("--- v2 checks ---", flush=True)

    # heart_challenge creation must be rejected (removed quest).
    code, err = call("POST", "/api/v1/sessions", tok_a, body={"quest_id": "heart_challenge", "demo": True})
    check("v2: heart creation rejected", code == 422, (code, err))

    # Pet mirror + daily care cap (+10 XP once per user per day).
    code, pet0 = call("GET", "/api/v1/me/pet", tok_a, expect=200)
    xp0 = pet0["lifetime_xp"]
    code, pet = call("PUT", "/api/v1/me/pet", tok_a, body={"species": "fluff", "name": "Sweep"}, expect=200)
    check("v2: pet mirror updated", pet["species"] == "fluff" and pet["name"] == "Sweep")
    today = datetime.now(timezone.utc).date().isoformat()
    code, care1 = call("POST", "/api/v1/me/pet/care", tok_a, body={"date": today}, expect=200)
    check("v2: care grants +10 XP", care1["lifetime_xp"] == xp0 + 10, (xp0, care1["lifetime_xp"]))
    code, care2 = call("POST", "/api/v1/me/pet/care", tok_a, body={"date": today}, expect=200)
    check("v2: care capped at once per day", care2["lifetime_xp"] == xp0 + 10, care2["lifetime_xp"])
    code, me_v2 = call("GET", "/api/v1/me", tok_a, expect=200)
    check("v2: /me carries the pet", me_v2["pet"]["name"] == "Sweep", me_v2["pet"])

    # Phone GPS source rides the batch and lands in the record.
    run_stamp2 = int(time.time())
    phone_rec = fixture_record(1, 0.0, session_id="00000000-0000-0000-0000-000000000000",
                               peer_device=dev_b, token="unused", boot=f"FIXTURE-gps-{run_stamp2}")
    phone_rec["gps"] = {"valid": True, "latitude": 34.9858, "longitude": 135.7587,
                        "fix_age_ms": 1200, "source": "phone"}
    phone_rec["session_id"] = None
    code, ack = call("POST", "/api/v1/telemetry/batches", tok_a, body={
        "schema_version": 1, "device_id": dev_a, "records": [phone_rec]}, expect=200)
    check("v2: phone-GPS record accepted", ack["accepted"], ack)

    # Landmarks list (raid prerequisites).
    code, lms = call("GET", "/api/v1/landmarks", tok_a, expect=200)
    check("v2: landmarks seeded", len(lms["landmarks"]) >= 1, len(lms["landmarks"]))

    # Raid: creation without a landmark rejected; gate blocks acceptance
    # without fixes; full flow needs both outcome reports.
    code, err = call("POST", "/api/v1/sessions", tok_a, body={"quest_id": "raid", "demo": True})
    check("v2: raid requires a landmark", code == 422, (code, err))
    code, raid = call("POST", "/api/v1/sessions", tok_a,
                      body={"quest_id": "raid", "demo": True, "landmark_id": lms["landmarks"][0]["id"]},
                      expect=201)
    code, err = call("POST", f"/api/v1/sessions/{raid['id']}/accept", tok_b)
    check("v2: raid gate blocks without fixes", code == 409 and err["error"]["code"] == "raid_gate_location", (code, err))
    code, _ = call("POST", f"/api/v1/sessions/{raid['id']}/cancel", tok_a, body={}, expect=200)
    check("v2: gated raid cancels cleanly", True)

    failed = [r for r in results if not r[1]]
    print(f"\n== {len(results) - len(failed)}/{len(results)} checks passed ==")
    if failed:
        for name, _, detail in failed:
            print("FAILED:", name, detail)
        sys.exit(1)


if __name__ == "__main__":
    main()
