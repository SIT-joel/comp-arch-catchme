"""Telemetry ingestion, session lifecycle, quest completion, awards."""

import uuid
from datetime import datetime, timedelta, timezone

# Evidence only counts at/after the start-PIN confirmation moment (real wall
# clock), so fixture captures must sit AHEAD of runtime for the whole suite
# (the suite itself runs ~1 minute). A constant date here silently breaks the
# suite once real time passes it (observed with 2026-11-01 on 3 November);
# derive it per run instead.
T0 = datetime.now(timezone.utc) + timedelta(hours=1)


def iso(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def rec(
    seq: int,
    t: float,
    *,
    boot="boot-a-1",
    session=None,
    peer=None,
    gps=None,
    hr=None,
    uncertainty=500,
    captured=True,
):
    return {
        "boot_id": boot,
        "sequence": seq,
        "session_id": str(session) if session else None,
        "uptime_ms": int(t * 1000),
        "captured_at": iso(t) if captured else None,
        "clock": {"source": "phone_server_anchor", "uncertainty_ms": uncertainty},
        "gps": gps or {"valid": False, "latitude": None, "longitude": None, "fix_age_ms": None},
        "heart_rate": hr or {"valid": False, "bpm": None, "status": "no_contact"},
        "peer": peer or {"observed": False},
    }


def peer_obs(device_id, heartbeat, token, age=0, boot="peer-boot"):
    return {
        "observed": True,
        "device_id": str(device_id),
        "boot_id": boot,
        "heartbeat_sequence": heartbeat,
        "session_token": token,
        "observation_age_ms": age,
    }


def post_batch(client, device_id, records):
    return client.post(
        "/api/v1/telemetry/batches",
        json={"schema_version": 1, "device_id": str(device_id), "records": records},
    )


def start_active_session(clients, quest="together", demo=True):
    created = clients["a"].post("/api/v1/sessions", json={"quest_id": quest, "demo": demo})
    assert created.status_code == 201, created.text
    session = created.json()
    accepted = clients["b"].post(f"/api/v1/sessions/{session['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["state"] == "active"
    if quest == "together":
        exchange_pin_stage(clients, body["id"], "start")
        body = clients["a"].get(f"/api/v1/sessions/{body['id']}").json()
    return body


def interaction(clients, user, session_id):
    response = clients[user].get(f"/api/v1/sessions/{session_id}/interaction")
    assert response.status_code == 200, response.text
    return response.json()


def exchange_pin_stage(clients, session_id, stage):
    """Each participant enters the other participant's private display code."""
    a = interaction(clients, "a", session_id)
    b = interaction(clients, "b", session_id)
    assert a["stage"] == b["stage"] == stage
    for user, other in (("a", b), ("b", a)):
        response = clients[user].post(
            f"/api/v1/sessions/{session_id}/interaction/pin/submit",
            json={
                "stage": stage,
                "pin": other["own_code"],
                "code_version": other["own_code_version"],
                "command_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 200, response.text


# --- telemetry validation + idempotency ---


def test_duplicate_records_are_no_op(clients):
    batch = [rec(1, 1.0), rec(2, 2.0)]
    first = post_batch(clients["a"], clients["a_device"], batch)
    assert first.status_code == 200
    assert len(first.json()["accepted"]) == 2
    assert first.json()["duplicates"] == []

    second = post_batch(clients["a"], clients["a_device"], batch)
    assert second.status_code == 200
    assert second.json()["accepted"] == []
    assert len(second.json()["duplicates"]) == 2


def test_same_sequence_different_boot_are_distinct(clients):
    first = post_batch(clients["a"], clients["a_device"], [rec(1, 1.0, boot="boot-1")])
    second = post_batch(clients["a"], clients["a_device"], [rec(1, 1.0, boot="boot-2")])
    assert first.status_code == second.status_code == 200
    assert second.json()["duplicates"] == []


def test_out_of_order_records_accepted(clients):
    response = post_batch(clients["a"], clients["a_device"], [rec(3, 3.0), rec(1, 1.0), rec(2, 2.0)])
    assert response.status_code == 200
    assert len(response.json()["accepted"]) == 3


def test_invalid_batch_rejected_atomically(clients):
    bad = [
        rec(1, 1.0),
        rec(2, 2.0, gps={"valid": True, "latitude": None, "longitude": 5.0, "fix_age_ms": 0}),
    ]
    response = post_batch(clients["a"], clients["a_device"], bad)
    assert response.status_code == 422
    # Atomic: the valid record in the batch was not stored.
    follow = post_batch(clients["a"], clients["a_device"], [rec(1, 1.0)])
    assert follow.json()["duplicates"] == []


def test_oversize_batch_rejected(clients):
    records = [rec(i, float(i)) for i in range(101)]
    response = post_batch(clients["a"], clients["a_device"], records)
    assert response.status_code == 422


def test_telemetry_for_foreign_device_forbidden(clients):
    response = post_batch(clients["a"], clients["b_device"], [rec(1, 1.0)])
    assert response.status_code == 403


def test_telemetry_for_foreign_session_forbidden(clients):
    other_session = uuid.uuid4()
    response = post_batch(clients["a"], clients["a_device"], [rec(1, 1.0, session=other_session)])
    assert response.status_code in (403, 422)


def test_invalid_bpm_status_combination_rejected(clients):
    bad_hr = {"valid": True, "bpm": None, "status": "valid"}
    response = post_batch(clients["a"], clients["a_device"], [rec(1, 1.0, hr=bad_hr)])
    assert response.status_code == 422
    bad_hr2 = {"valid": False, "bpm": 80, "status": "no_contact"}
    response = post_batch(clients["a"], clients["a_device"], [rec(2, 2.0, hr=bad_hr2)])
    assert response.status_code == 422


def test_invalid_coordinates_rejected(clients):
    bad_gps = {"valid": True, "latitude": 123.0, "longitude": 5.0, "fix_age_ms": 0}
    response = post_batch(clients["a"], clients["a_device"], [rec(1, 1.0, gps=bad_gps)])
    assert response.status_code == 422


# --- session lifecycle ---


def test_session_lifecycle_create_accept_complete_cancel_rules(clients):
    # One-sided invitation, then double-accept rejected, cancel works.
    created = clients["a"].post("/api/v1/sessions", json={"quest_id": "together", "demo": True})
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert created.json()["state"] == "pending"

    # Creator cannot accept twice.
    again = clients["a"].post(f"/api/v1/sessions/{session_id}/accept")
    assert again.status_code == 409

    accepted = clients["b"].post(f"/api/v1/sessions/{session_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["state"] == "active"
    assert accepted.json()["target_ms"] == 30_000
    assert accepted.json()["token"]

    # Parallel session for the pair is rejected while one is active.
    parallel = clients["b"].post("/api/v1/sessions", json={"quest_id": "together", "demo": True})
    assert parallel.status_code == 409

    # Accepting an active session again is a conflict.
    late = clients["a"].post(f"/api/v1/sessions/{session_id}/accept")
    assert late.status_code == 409

    cancelled = clients["b"].post(f"/api/v1/sessions/{session_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"

    # After cancellation a new session may start.
    fresh = clients["a"].post("/api/v1/sessions", json={"quest_id": "together", "demo": True})
    assert fresh.status_code == 201
    # Close it again so the final check below can start yet another.
    assert clients["a"].post(f"/api/v1/sessions/{fresh.json()['id']}/cancel").status_code == 200

    # Session read access rules.
    stranger = clients["a"].get(f"/api/v1/sessions/{uuid.uuid4()}")
    assert stranger.status_code == 404


def test_explore_requires_configured_geofence(clients):
    response = clients["a"].post("/api/v1/sessions", json={"quest_id": "explore", "demo": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "geofence_not_configured"


def _create_together_start_pin(clients):
    created = clients["a"].post("/api/v1/sessions", json={"quest_id": "together", "demo": True})
    assert created.status_code == 201, created.text
    accepted = clients["b"].post(f"/api/v1/sessions/{created.json()['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    return created.json()["id"]


def test_pin_refresh_invalidates_only_that_code_version(clients):
    session_id = _create_together_start_pin(clients)
    a = interaction(clients, "a", session_id)
    b = interaction(clients, "b", session_id)
    assert a["own_code"] != b["own_code"]
    assert "own_code" not in clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    board_state_a = clients["a"].get(f"/api/v1/devices/{clients['a_device']}/state").json()
    board_state_b = clients["b"].get(f"/api/v1/devices/{clients['b_device']}/state").json()
    assert board_state_a["session"]["interaction"]["own_code"] == a["own_code"]
    assert board_state_b["session"]["interaction"]["own_code"] == b["own_code"]

    accepted = clients["a"].post(
        f"/api/v1/sessions/{session_id}/interaction/pin/submit",
        json={"stage": "start", "pin": b["own_code"],
              "code_version": b["own_code_version"], "command_id": str(uuid.uuid4())},
    )
    assert accepted.status_code == 200, accepted.text
    assert interaction(clients, "b", session_id)["own_code_confirmed_by_partner"] is True
    pending_state = clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    assert pending_state["state"] == "active" and pending_state["progress_ms"] == 0
    assert interaction(clients, "a", session_id)["phase"] == "start_pin"
    assert clients["a"].get("/api/v1/me").json()["user"]["points"] == 0

    refreshed = clients["b"].post(
        f"/api/v1/sessions/{session_id}/interaction/pin/refresh",
        json={"stage": "start", "command_id": str(uuid.uuid4())},
    )
    assert refreshed.status_code == 200, refreshed.text
    after_b = refreshed.json()
    after_a = interaction(clients, "a", session_id)
    assert after_b["own_code_version"] == 2
    assert after_b["own_code"] != b["own_code"]
    assert after_b["own_code_confirmed_by_partner"] is False
    assert after_a["own_code"] == a["own_code"]
    assert after_a["partner_code_version"] == 2
    assert after_a["partner_code_confirmed_by_me"] is False

    stale = clients["a"].post(
        f"/api/v1/sessions/{session_id}/interaction/pin/submit",
        json={"stage": "start", "pin": b["own_code"],
              "code_version": b["own_code_version"], "command_id": str(uuid.uuid4())},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "pin_expired"

    exchange_pin_stage(clients, session_id, "start")
    assert interaction(clients, "a", session_id)["phase"] == "timing"


def test_pin_limits_failed_attempts_and_preserves_leading_zero(clients, monkeypatch):
    # Force repeated values to prove leading zero formatting and collision
    # rejection across users. These codes remain strings end-to-end.
    values = iter([7, 7, 42])
    monkeypatch.setattr("app.services.interactions.secrets.randbelow", lambda upper: next(values))
    session_id = _create_together_start_pin(clients)
    a = interaction(clients, "a", session_id)
    b = interaction(clients, "b", session_id)
    assert {a["own_code"], b["own_code"]} == {"0007", "0042"}

    wrong_code = "0000" if b["own_code"] != "0000" else "0001"
    for _ in range(5):
        response = clients["a"].post(
            f"/api/v1/sessions/{session_id}/interaction/pin/submit",
            json={"stage": "start", "pin": wrong_code,
                  "code_version": b["own_code_version"], "command_id": str(uuid.uuid4())},
        )
        assert response.status_code == 422
    blocked = clients["a"].post(
        f"/api/v1/sessions/{session_id}/interaction/pin/submit",
        json={"stage": "start", "pin": wrong_code,
              "code_version": b["own_code_version"], "command_id": str(uuid.uuid4())},
    )
    assert blocked.status_code == 429


def test_expired_pin_requires_owner_refresh(clients, db_session):
    from app.models import SessionPin

    session_id = _create_together_start_pin(clients)
    a = interaction(clients, "a", session_id)
    b = interaction(clients, "b", session_id)
    partner_user_id = clients["b"].get("/api/v1/me").json()["user"]["id"]
    pin = db_session.get(SessionPin, (uuid.UUID(session_id), "start", uuid.UUID(partner_user_id)))
    pin.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    expired = clients["a"].post(
        f"/api/v1/sessions/{session_id}/interaction/pin/submit",
        json={"stage": "start", "pin": b["own_code"],
              "code_version": b["own_code_version"], "command_id": str(uuid.uuid4())},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "pin_expired"
    refreshed = clients["b"].post(
        f"/api/v1/sessions/{session_id}/interaction/pin/refresh",
        json={"stage": "start", "command_id": str(uuid.uuid4())},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["own_code_version"] == 2


def test_unversioned_legacy_session_keeps_legacy_scoring(clients, db_session):
    from app.models import QuestSession, SessionInteraction, SessionPin, SessionPinHistory

    created = clients["a"].post("/api/v1/sessions", json={"quest_id": "together", "demo": True})
    session_id = created.json()["id"]
    accepted = clients["b"].post(f"/api/v1/sessions/{session_id}/accept")
    assert accepted.status_code == 200
    session = accepted.json()

    row = db_session.get(QuestSession, uuid.UUID(session_id))
    row.interaction_version = None
    db_session.query(SessionPin).filter(SessionPin.session_id == row.id).delete()
    db_session.query(SessionPinHistory).filter(SessionPinHistory.session_id == row.id).delete()
    db_session.query(SessionInteraction).filter(SessionInteraction.session_id == row.id).delete()
    db_session.commit()

    push_mutual_observations(clients, session, 1, range(0, 31, 2), session["token"])
    final = clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    assert final["state"] == "completed"
    assert final["progress_ms"] == 30_000


# --- together quest end-to-end with awards ---


def push_mutual_observations(clients, session, start_seq, times, token):
    """Push simultaneous records from both devices. Heartbeat counters stay
    strictly increasing across pushes (start_seq keeps them monotonic)."""
    session_id = session["id"]
    for i, t in enumerate(times):
        seq = start_seq + i
        a_records = [
            rec(seq, t, session=session_id,
                peer=peer_obs(clients["b_device"], seq, token, boot="boot-b-7"))
        ]
        b_records = [
            rec(seq, t, boot="boot-b-7", session=session_id,
                peer=peer_obs(clients["a_device"], seq, token, boot="boot-a-1"))
        ]
        assert post_batch(clients["a"], clients["a_device"], a_records).status_code == 200
        assert post_batch(clients["b"], clients["b_device"], b_records).status_code == 200
    return start_seq + len(times)


def test_together_quest_completes_and_awards_exactly_once(clients):
    session = start_active_session(clients, "together", demo=True)
    assert session["target_ms"] == 30_000  # demo duration from PROJECT_SPEC
    token = session["token"]
    session_id = session["id"]

    # 30 s demo target: mutual observations every 2 s for 30 s.
    times = [float(t) for t in range(0, 31, 2)]
    push_mutual_observations(clients, session, 1, times, token)

    state = clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    assert state["state"] == "active", state
    assert state["progress_ms"] == 30_000
    assert interaction(clients, "a", session_id)["phase"] == "end_pin"
    assert clients["a"].get("/api/v1/me").json()["user"]["points"] == 0

    # The final participant confirmations, not elapsed presence alone, release awards.
    exchange_pin_stage(clients, session_id, "end")
    state = clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    assert state["state"] == "completed", state
    assert state["progress_ms"] == 30_000

    me_a = clients["a"].get("/api/v1/me").json()["user"]
    me_b = clients["b"].get("/api/v1/me").json()["user"]
    assert me_a["points"] == 100 and me_a["lifetime_xp"] == 100 and me_a["level"] == 2
    assert me_b["points"] == 100 and me_b["lifetime_xp"] == 100 and me_b["level"] == 2

    # Replaying old records must not re-award or change progress.
    replay = [rec(1, 0.0, peer=peer_obs(clients["b_device"], 1, token, boot="boot-b-7"))]
    assert post_batch(clients["a"], clients["a_device"], replay).json()["duplicates"]
    me_a2 = clients["a"].get("/api/v1/me").json()["user"]
    assert me_a2["points"] == 100

    # Cancel of a completed session is rejected (immutable).
    cancel = clients["a"].post(f"/api/v1/sessions/{session_id}/cancel")
    assert cancel.status_code == 409

    # Transaction history shows exactly one award row.
    txs = clients["a"].get("/api/v1/transactions").json()["transactions"]
    awards = [t for t in txs if t["kind"] == "quest_award"]
    assert len(awards) == 1
    assert awards[0]["delta"] == 100 and awards[0]["xp_delta"] == 100


def test_heart_quest_creation_rejected(clients):
    # v2: heart_challenge is removed from the creatable set (legacy reads only).
    created = clients["a"].post(
        "/api/v1/sessions", json={"quest_id": "heart_challenge", "demo": True}
    )
    assert created.status_code == 422, created.text


def test_legacy_heart_session_still_serializes(clients, db_session):
    # v2 removed the quest, but historical rows must keep rendering.
    from datetime import datetime, timedelta, timezone

    from app.models import QuestSession, SessionParticipant

    a_id, b_id = clients["a_user"], clients["b_user"]
    now = datetime.now(timezone.utc)
    legacy = QuestSession(
        quest_id="heart_challenge",
        demo=True,
        state="completed",
        created_by=a_id,
        created_at=now - timedelta(minutes=10),
        activated_at=now - timedelta(minutes=9),
        completed_at=now - timedelta(minutes=8),
        target_ms=30_000,
        progress_ms=30_000,
        session_token="legacy-heart-token",
    )
    db_session.add(legacy)
    db_session.flush()
    db_session.add_all(
        [
            SessionParticipant(session_id=legacy.id, user_id=a_id, accepted_at=now),
            SessionParticipant(session_id=legacy.id, user_id=b_id, accepted_at=now),
        ]
    )
    db_session.commit()

    state = clients["a"].get(f"/api/v1/sessions/{legacy.id}").json()
    assert state["quest_id"] == "heart_challenge"
    assert state["state"] == "completed"
    assert state["progress_ms"] == 30_000


def test_separation_pauses_and_resumes_progress(clients):
    session = start_active_session(clients, "together", demo=True)
    token = session["token"]
    session_id = session["id"]

    # 0..6 s mutual (6 s progress), then a 15 s separation gap. The gap is
    # never bridged: progress stays exactly at the first span's duration.
    push_mutual_observations(clients, session, 1, [0, 2, 4, 6], token)

    state = clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    assert state["state"] == "active"
    assert state["progress_ms"] == 6_000

    # Reunite long after: the gap contributes no time; new span resumes credit.
    push_mutual_observations(clients, session, 10, [21, 23, 25, 27], token)
    state = clients["a"].get(f"/api/v1/sessions/{session_id}").json()
    assert state["state"] == "active"
    assert state["progress_ms"] == 6_000 + 6_000


def test_one_sided_evidence_never_completes(clients):
    session = start_active_session(clients, "together", demo=True)
    token = session["token"]
    session_id = session["id"]
    # Only A reports observations of B; B never sees A.
    for i, t in enumerate(range(0, 40, 2)):
        post_batch(
            clients["a"],
            clients["a_device"],
            [rec(i + 1, float(t), session=session_id, peer=peer_obs(clients["b_device"], i + 1, token, boot="boot-b-7"))],
        )
    state = clients["a"].get(f"/api/v1/sessions/{session['id']}").json()
    assert state["state"] == "active"
    assert state["progress_ms"] == 0
