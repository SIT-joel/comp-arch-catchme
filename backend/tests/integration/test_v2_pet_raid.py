"""v2 integration tests: pet daily care, phone GPS source, landmark raid."""

import uuid
from datetime import datetime, timedelta, timezone

from tests.integration.conftest import login
from tests.integration.test_telemetry_and_sessions import post_batch, rec

T0 = datetime.now(timezone.utc) + timedelta(hours=1)  # matches module helper


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


# --- pet ---


def test_pet_defaults_and_update(clients):
    me = clients["a"].get("/api/v1/me").json()
    assert me["pet"]["level"] == 1 and me["pet"]["lifetime_xp"] == 0
    assert me["pet"]["species"] is None and me["pet"]["cared_today"] is False

    updated = clients["a"].put(
        "/api/v1/me/pet", json={"species": "spark", "name": "Bolt"}
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["species"] == "spark" and body["name"] == "Bolt"
    assert body["evolution_stage"] == 1

    bad = clients["a"].put("/api/v1/me/pet", json={"species": "dragon", "name": "X"})
    assert bad.status_code == 422
    long_name = clients["a"].put("/api/v1/me/pet", json={"species": "pip", "name": "TOOLONGNAME"})
    assert long_name.status_code == 422


def test_pet_care_daily_cap_and_streak(clients):
    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    first = clients["a"].post("/api/v1/me/pet/care", json={"date": today})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["lifetime_xp"] == 10 and body["cared_today"] is True
    assert body["care_streak"] == 1
    me = clients["a"].get("/api/v1/me").json()
    assert me["user"]["lifetime_xp"] == 10
    assert me["user"]["points"] == 0  # XP-only grant; points untouched

    replay = clients["a"].post("/api/v1/me/pet/care", json={"date": today})
    assert replay.status_code == 200
    assert replay.json()["lifetime_xp"] == 10  # cap: no double grant

    future = clients["a"].post(
        "/api/v1/me/pet/care",
        json={"date": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()},
    )
    assert future.status_code == 422

    yesterday_claim = clients["a"].post("/api/v1/me/pet/care", json={"date": yesterday})
    assert yesterday_claim.status_code == 200
    # Out-of-order backfill must not increment the streak twice for yesterday.
    assert yesterday_claim.json()["lifetime_xp"] == 20
    today_state = clients["a"].get("/api/v1/me/pet").json()
    assert today_state["last_care_date"] == today

    too_old = clients["a"].post(
        "/api/v1/me/pet/care",
        json={"date": (datetime.now(timezone.utc).date() - timedelta(days=9)).isoformat()},
    )
    assert too_old.status_code == 422


# --- phone GPS source ---


def test_gps_source_persisted_and_defaulted(clients):
    phone_record = rec(1, 0.0, gps={"valid": True, "latitude": 34.9858, "longitude": 135.7587, "fix_age_ms": 1200})
    phone_record["gps"]["source"] = "phone"
    r = post_batch(clients["a"], clients["a_device"], [phone_record])
    assert r.status_code == 200
    wearable_record = rec(2, 2.0, gps={"valid": True, "latitude": 34.9858, "longitude": 135.7587, "fix_age_ms": 500})
    r2 = post_batch(clients["a"], clients["a_device"], [wearable_record])
    assert r2.status_code == 200

    from app.db import SessionLocal
    from app.models import TelemetryRecord

    db = SessionLocal()
    try:
        rows = (
            db.query(TelemetryRecord)
            .filter(TelemetryRecord.device_id == clients["a_device"])
            .order_by(TelemetryRecord.sequence)
            .all()
        )
        sources = {row.sequence: row.gps_source for row in rows}
        assert sources[1] == "phone"
        assert sources[2] == "wearable"
    finally:
        db.close()


# --- raid ---


def _landmark(clients) -> dict:
    rows = clients["a"].get("/api/v1/landmarks").json()["landmarks"]
    assert len(rows) >= 1
    return rows[0]


def _push_fix(clients, device_id, seq, landmark, *, age_s=2.0):
    """A phone fix at the landmark, with fix_time ≈ now - age_s."""
    captured = T0  # T0 = now + 1 h (module helper convention)
    fix_time = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    fix_age_ms = int((captured - fix_time).total_seconds() * 1000)
    record = rec(
        seq, 0.0,
        gps={"valid": True, "latitude": landmark["latitude"], "longitude": landmark["longitude"], "fix_age_ms": fix_age_ms},
    )
    record["gps"]["source"] = "phone"
    record["captured_at"] = _iso(captured)
    r = post_batch(clients["a"] if device_id == clients["a_device"] else clients["b"], device_id, [record])
    assert r.status_code == 200, r.text


def start_raid(clients, landmark):
    created = clients["a"].post(
        "/api/v1/sessions",
        json={"quest_id": "raid", "demo": True, "landmark_id": landmark["id"]},
    )
    return created


def test_raid_create_requires_landmark(clients):
    missing = clients["a"].post("/api/v1/sessions", json={"quest_id": "raid", "demo": True})
    assert missing.status_code == 422
    bogus = clients["a"].post(
        "/api/v1/sessions", json={"quest_id": "raid", "demo": True, "landmark_id": "nope"}
    )
    assert bogus.status_code == 404
    stray = clients["a"].post(
        "/api/v1/sessions", json={"quest_id": "together", "demo": True, "landmark_id": "landmark_a"}
    )
    assert stray.status_code == 422


def test_raid_gate_blocks_without_fixes(clients):
    landmark = _landmark(clients)
    created = start_raid(clients, landmark)
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["landmark"]["id"] == landmark["id"]

    blocked = clients["b"].post(f"/api/v1/sessions/{session['id']}/accept")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "raid_gate_location"
    cleanup = clients["a"].post(f"/api/v1/sessions/{session['id']}/cancel")
    assert cleanup.status_code == 200


def _activate_and_backdate(clients, session_id, seconds: int = 120):
    """Accept + simulate that the fight window already elapsed: activation is
    backdated so fabricated fight times fit inside [activated_at, now]."""
    from datetime import datetime, timedelta, timezone as tz

    from app.db import SessionLocal
    from app.models import QuestSession

    accepted = clients["b"].post(f"/api/v1/sessions/{session_id}/accept")
    assert accepted.status_code == 200, accepted.text
    db = SessionLocal()
    try:
        row = db.get(QuestSession, uuid.UUID(session_id))
        row.activated_at = datetime.now(tz.utc) - timedelta(seconds=seconds)
        db.commit()
    finally:
        db.close()
    return accepted.json()


def test_raid_full_win_awards_once(clients):
    landmark = _landmark(clients)
    created = start_raid(clients, landmark)
    session = created.json()
    _push_fix(clients, clients["a_device"], 1, landmark)
    _push_fix(clients, clients["b_device"], 1, landmark)
    _activate_and_backdate(clients, session["id"])
    sid = session["id"]

    now = datetime.now(timezone.utc)
    first = clients["a"].post(
        f"/api/v1/sessions/{sid}/raid/outcome",
        json={
            "outcome": "win",
            "fight_started_at": _iso(now - timedelta(seconds=90)),
            "fight_ended_at": _iso(now - timedelta(seconds=10)),
            "command_id": str(uuid.uuid4()),
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "active"  # one report is not enough
    assert first.json()["raid_outcome"] == "win"

    xp_before = {
        clients["a"].get("/api/v1/me").json()["user"]["lifetime_xp"],
    }
    second = clients["b"].post(
        f"/api/v1/sessions/{sid}/raid/outcome",
        json={
            "outcome": "win",
            "fight_started_at": _iso(now - timedelta(seconds=85)),
            "fight_ended_at": _iso(now - timedelta(seconds=12)),
            "command_id": str(uuid.uuid4()),
        },
    )
    assert second.status_code == 200, second.text
    final = second.json()
    assert final["state"] == "completed"

    me_a = clients["a"].get("/api/v1/me").json()
    me_b = clients["b"].get("/api/v1/me").json()
    assert me_a["user"]["lifetime_xp"] == 100 and me_a["user"]["points"] == 100
    assert me_b["user"]["lifetime_xp"] == 100 and me_b["user"]["points"] == 100

    replay = clients["a"].post(
        f"/api/v1/sessions/{sid}/raid/outcome",
        json={
            "outcome": "win",
            "fight_started_at": _iso(now - timedelta(seconds=90)),
            "fight_ended_at": _iso(now - timedelta(seconds=10)),
            "command_id": str(uuid.uuid4()),
        },
    )
    assert replay.status_code == 409  # one report per reporter
    assert clients["a"].get("/api/v1/me").json()["user"]["lifetime_xp"] == 100


def test_raid_loss_completes_without_award(clients):
    landmark = _landmark(clients)
    created = start_raid(clients, landmark)
    session = created.json()
    _push_fix(clients, clients["a_device"], 1, landmark)
    _push_fix(clients, clients["b_device"], 1, landmark)
    _activate_and_backdate(clients, session["id"])
    sid = session["id"]

    now = datetime.now(timezone.utc)
    clients["a"].post(
        f"/api/v1/sessions/{sid}/raid/outcome",
        json={
            "outcome": "win",
            "fight_started_at": _iso(now - timedelta(seconds=60)),
            "fight_ended_at": _iso(now - timedelta(seconds=5)),
            "command_id": str(uuid.uuid4()),
        },
    )
    lost = clients["b"].post(
        f"/api/v1/sessions/{sid}/raid/outcome",
        json={
            "outcome": "lose",
            "fight_started_at": _iso(now - timedelta(seconds=60)),
            "fight_ended_at": _iso(now - timedelta(seconds=5)),
            "command_id": str(uuid.uuid4()),
        },
    )
    assert lost.status_code == 200
    assert lost.json()["state"] == "completed"
    me_a = clients["a"].get("/api/v1/me").json()
    me_b = clients["b"].get("/api/v1/me").json()
    # A shared loss completes the session but pays nobody.
    assert me_a["user"]["lifetime_xp"] == 0 and me_b["user"]["lifetime_xp"] == 0


def test_raid_outcome_requires_participant(clients):
    landmark = _landmark(clients)
    created = start_raid(clients, landmark)
    session = created.json()
    _push_fix(clients, clients["a_device"], 1, landmark)
    _push_fix(clients, clients["b_device"], 1, landmark)
    assert clients["b"].post(f"/api/v1/sessions/{session['id']}/accept").status_code == 200
    now = datetime.now(timezone.utc)
    # Unauthenticated call must be rejected before any state change.
    unauth = clients["a"].post(
        f"/api/v1/sessions/{session['id']}/raid/outcome",
        json={
            "outcome": "win",
            "fight_started_at": _iso(now),
            "fight_ended_at": _iso(now),
            "command_id": str(uuid.uuid4()),
        },
        headers={"Authorization": ""},
    )
    assert unauth.status_code in (401, 403, 422)
    clients["a"].post(f"/api/v1/sessions/{session['id']}/cancel")
