"""PC relay for board 2's telemetry (TEST TOOL — PC stands in for toma's
missing phone; the records themselves are REAL wearable observations).

Connects to board 2's UART service, anchors its clock (TIME_ANCHOR), then
decodes MSG_TELEMETRY frames (seq u32 + 32-byte record, layout per
firmware records.h) and uploads batches to the server as toma's bound
device. Peer observations are resolved to the partner device (board 1)
and the active quest session. Clearly labeled test harness; the product
path is always phone -> server (docs/DISCOVERY_PLAN.md).

Usage: py -3 tools/board2_telemetry_relay.py <bearer_token> [seconds]
"""

import asyncio
import json
import sys
import time
import urllib.request
import uuid

import bleak

ADDRESS = "02:80:E1:00:34:12"
UART_TX = bleak.normalize_uuid_str("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
UART_RX = bleak.normalize_uuid_str("6e400003-b5a3-f393-e0a9-e50e24dcca9e")

BASE = "http://127.0.0.1:8000/api/v1"
BOARD1_DEVICE = "904229f7-6dee-5ce6-85cb-51227471b2f4"  # miya's wearable
BOARD2_DEVICE = "cc018d28-8d17-5e40-b42f-bdb79c40758c"  # toma's wearable

MSG_TIME_ANCHOR = 2
MSG_TELEMETRY = 5
MSG_INTERACTION_STATE = 14

assembler = {}
completed = []  # (type, payload) — drained by the main loop, never overwritten


def crc8(data: bytes, seed: int = 0x00) -> int:
    crc = seed
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def frame(msg_id: int, msg_type: int, payload: bytes) -> bytes:
    header = bytes([0xA5, 0x01, msg_type, msg_id, 0x00, 0x01, len(payload)])
    return header + bytes([crc8(header + payload)]) + payload


def handle_notify(sender, data: bytes):
    stats["notifies"] += 1
    stats["bytes"] += len(data)
    if VERBOSE and stats["notifies"] % 10 == 0:
        print(f"  notify#{stats['notifies']} len={len(data)} "
              f"head={data[:10].hex()}", flush=True)
    if len(data) < 8 or data[0] != 0xA5:
        return
    stats["frames"] += 1
    msg_id, idx, count, chunk = data[3], data[4], data[5], data[6]
    body = data[8:8 + chunk]
    if crc8(data[:7] + body) != data[7]:
        return
    key = msg_id
    if idx == 0:
        assembler[key] = bytearray()
        assembler[key + 1000] = count
    buf = assembler.get(key)
    if buf is None:
        return
    buf += body
    assembler[key + 1000] -= 1
    if assembler[key + 1000] <= 0:
        completed.append((data[2], bytes(buf)))
        del assembler[key], assembler[key + 1000]


def decode_record(seq: int, rec: bytes) -> dict:
    import struct

    (uptime, captured_epoch, unc, flags, bpm, hr_status,
     lat, lon, fix_age, peer_dev, peer_hb, peer_age, peer_tok) = struct.unpack(
        "<IIHBBBiiHBHHH2x", rec)
    out = {
        "boot_id": BOOT_ID,
        "sequence": seq,
        "session_id": SESSION.get("id"),
        "uptime_ms": uptime,
        "captured_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(captured_epoch)) if captured_epoch else None,
        "clock": {"source": "phone_server_anchor" if captured_epoch else "unsynced",
                  "uncertainty_ms": unc if unc != 0xFFFF else None},
        "gps": ({"valid": True, "latitude": lat / 1e6, "longitude": lon / 1e6,
                 "fix_age_ms": fix_age if fix_age != 0xFFFF else 0}
                if flags & 1 else {"valid": False}),
        "heart_rate": ({"valid": True, "bpm": bpm, "status": "valid"}
                       if flags & 2 else {"valid": False, "status": "no_contact"}),
        "peer": {"observed": False},
    }
    if flags & 4 and peer_dev == 1:
        # Board 2 observing board 1: resolve to the partner device + session.
        out["peer"] = {
            "observed": True,
            "device_id": BOARD1_DEVICE,
            "boot_id": "d1-relay",
            "heartbeat_sequence": peer_hb,
            "session_token": SESSION.get("token"),
            "observation_age_ms": peer_age,
        }
        if not SESSION.get("token"):
            out["peer"] = {"observed": False}
    return out


def build_interaction_state(ds: dict, me_id: str) -> bytes:
    """58-byte INTERACTION_STATE, mirroring the phone's sendInteractionState."""
    out = bytearray(58)
    out[0] = 1
    session = ds.get("session")
    completion = ds.get("completion")
    is_finished = session is None and completion is not None
    interaction = (session or {}).get("interaction") or (completion or {}).get("interaction")
    if (not is_finished and (session is None or session.get("state") != "active")) or not interaction:
        return bytes(out)
    keep_summary = (not is_finished) or interaction.get("quest_id") == "heart_challenge"
    phase_map = {"start_pin": 1, "timing": 2, "end_pin": 3, "baseline": 4,
                 "select_prompt": 5, "round": 6, "summary": 7}
    out[1] = phase_map.get(interaction.get("phase"), 0) if keep_summary else 0
    stage_map = {"start": 1, "end": 2}
    out[3] = stage_map.get(interaction.get("stage"), 0)
    code = (interaction.get("own_code") or "----")[:4].ljust(4, "-").encode()
    out[4:8] = code
    out[8:10] = int(interaction.get("own_code_version", 0)).to_bytes(2, "little")
    out[10:12] = int(interaction.get("partner_code_version", 0)).to_bytes(2, "little")
    out[12] = 1 if interaction.get("own_code_confirmed_by_partner") else 0
    out[13] = 1 if interaction.get("partner_code_confirmed_by_me") else 0
    out[14] = int(interaction.get("round_index", 0)) & 0xFF
    out[15] = 1 if interaction.get("active_user_id") == me_id else 0
    kind_map = {"truth": 1, "dare": 2}
    out[16] = kind_map.get(interaction.get("prompt_kind"), 0)
    prompt = (interaction.get("prompt") or "")[:24].encode()
    out[17] = len(prompt)
    out[18:18 + len(prompt)] = prompt
    try:
        sid = uuid.UUID(interaction.get("session_id"))
        out[42:58] = sid.bytes  # BIG_ENDIAN longs, matching the phone
    except Exception:
        pass
    return bytes(out)


def api(path: str, method: str = "GET", body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(req, data=data, timeout=10) as resp:
        return json.loads(resp.read().decode() or "{}")


TOKEN = None
SESSION = {}
BOOT_ID = f"d2r-{int(time.time())}"
VERBOSE = "--verbose" in sys.argv

stats = {"notifies": 0, "bytes": 0, "frames": 0, "complete": 0, "decode_err": 0}


async def main():
    global TOKEN, SESSION
    args = [a for a in sys.argv[1:] if a != "--verbose"]
    TOKEN = args[0]
    seconds = float(sys.argv[-1]) if sys.argv[-1].isdigit() else 3600

    me = api("/me", token=TOKEN)
    ME_ID = me["user"]["id"]
    print("relay as", me["user"]["username"], flush=True)

    pending = []
    seq_seen = set()
    t0 = time.time()
    last_session_fetch = 0
    last_upload = time.time()

    def refresh_session():
        global SESSION
        sessions = api("/sessions", token=TOKEN)["sessions"]
        active = next((s for s in sessions if s["state"] == "active"), None)
        SESSION = ({"id": active["id"], "token": active["token"]}
                   if active else {})

    # The wearable's TDD schedule drops the link every ~8.5 s by design
    # (docs/PROGRESS.md): reconnect constantly, like the phone's supervisor.
    while time.time() - t0 < seconds:
        client = bleak.BleakClient(ADDRESS, timeout=8.0)
        ok = False
        while not ok and time.time() - t0 < seconds:  # keep trying: windows are scarce
            try:
                await client.connect()
                ok = True
                break
            except Exception:
                await asyncio.sleep(0.8)
        if not ok:
            print("connect failed this round", flush=True)
            await asyncio.sleep(2)
            continue
        try:
            await client.start_notify(UART_RX, handle_notify)
            anchor = frame(1, MSG_TIME_ANCHOR, struct.pack("<IH", int(time.time()), 500))
            await client.write_gatt_char(UART_TX, anchor, response=False)
            # Relay the interaction phase so board 2's screen keeps up.
            try:
                ds = api(f"/devices/{BOARD2_DEVICE}/state", token=TOKEN)
                ismsg = frame(2, MSG_INTERACTION_STATE,
                              build_interaction_state(ds, ME_ID))
                for off in range(0, len(ismsg), 12):
                    await client.write_gatt_char(
                        UART_TX, ismsg[off:off + 12], response=False)
                    await asyncio.sleep(0.05)
            except Exception as exc:
                print("interaction relay:", str(exc)[:60], flush=True)
            print("link up; subscribed + anchored", flush=True)
            polls = 0
            while client.is_connected and time.time() - t0 < seconds:
                await asyncio.sleep(0.3)
                polls += 1
                if polls % 30 == 0:
                    print(f"  stats {dict(stats)} pending={len(pending)}",
                          flush=True)
                if not completed:
                    continue
                mtype, payload = completed.pop(0)
                stats["complete"] += 1
                if mtype != MSG_TELEMETRY or len(payload) < 36:
                    continue
                seq = int.from_bytes(payload[:4], "little")
                if seq in seq_seen:
                    continue
                seq_seen.add(seq)
                if time.time() - last_session_fetch > 30:
                    last_session_fetch = time.time()
                    try:
                        refresh_session()
                    except Exception as exc:
                        print("session fetch:", exc, flush=True)
                try:
                    rec = decode_record(seq, payload[4:36])
                except Exception as exc:
                    stats["decode_err"] += 1
                    if VERBOSE:
                        print(f"  decode err: {exc}", flush=True)
                    continue
                if rec["peer"].get("observed") or rec["gps"]["valid"] or rec["heart_rate"]["valid"]:
                    pending.append(rec)
                    if VERBOSE and len(pending) % 5 == 0:
                        print(f"  pending={len(pending)} "
                              f"seq={seq}", flush=True)
                if pending and time.time() - last_upload > 10:
                    last_upload = time.time()
                    batch = {"schema_version": 1, "device_id": BOARD2_DEVICE,
                             "records": pending[:50]}
                    try:
                        ack = api("/telemetry/batches", "POST", batch, token=TOKEN)
                        print(f"uploaded {len(pending)} recs "
                              f"(acc {len(ack['accepted'])}, dup {len(ack['duplicates'])})",
                              flush=True)
                        pending = pending[50:]
                    except Exception as exc:
                        print("upload failed:", str(exc)[:80], flush=True)
        except Exception as exc:
            print("link error:", str(exc)[:60], flush=True)
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
        await asyncio.sleep(0.3)
    print("relay window ended", flush=True)


import struct

asyncio.run(main())
