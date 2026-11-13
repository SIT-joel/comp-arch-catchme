"""Purchase rules, concurrency on PostgreSQL, and SSE notifications."""

import threading

from tests.integration.conftest import login


def give_points(db_session, user, points):
    user.points_balance = points
    db_session.commit()


def buy(client, reward_id, key):
    return client.post(
        "/api/v1/purchases",
        json={"reward_id": reward_id},
        headers={"Idempotency-Key": key},
    )


def test_purchase_deducts_points_not_xp(clients, db_session):
    from tests.integration.test_telemetry_and_sessions import (
        push_mutual_observations,
        rec,
        post_batch,
        exchange_pin_stage,
        start_active_session,
    )

    session = start_active_session(clients)
    push_mutual_observations(clients, session, 1, [float(t) for t in range(0, 31, 2)], session["token"])
    exchange_pin_stage(clients, session["id"], "end")

    me = clients["a"].get("/api/v1/me").json()["user"]
    assert me["points"] == 100 and me["lifetime_xp"] == 100 and me["level"] == 2

    response = buy(clients["a"], "first_spark", "key-1")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["balance_after"] == 50
    assert body["price"] == 50

    me_after = clients["a"].get("/api/v1/me").json()["user"]
    assert me_after["points"] == 50
    assert me_after["lifetime_xp"] == 100  # spending never reduces XP
    assert me_after["level"] == 2


def test_insufficient_points_rejected(clients, seeded_pair):
    response = buy(clients["a"], "first_spark", "key-2")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_points"


def test_idempotent_replay_returns_same_outcome(clients, db_session, seeded_pair):
    give_points(db_session, seeded_pair["a"]["user"], 60)
    first = buy(clients["a"], "first_spark", "same-key")
    assert first.status_code == 201
    replay = buy(clients["a"], "first_spark", "same-key")
    assert replay.status_code == 201
    assert replay.json()["balance_after"] == first.json()["balance_after"]
    # Only one debit happened.
    txs = clients["a"].get("/api/v1/transactions").json()["transactions"]
    purchases = [t for t in txs if t["kind"] == "purchase"]
    assert len(purchases) == 1


def test_already_owned_conflict(clients, db_session, seeded_pair):
    give_points(db_session, seeded_pair["a"]["user"], 500)
    assert buy(clients["a"], "first_spark", "k1").status_code == 201
    second = buy(clients["a"], "first_spark", "k2")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_owned"


def test_concurrent_purchases_cannot_overspend(clients, db_session, seeded_pair):
    """Two threads race to buy a 50-point badge with only 60 points.
    PostgreSQL row locks + unique constraints must allow exactly one."""
    from app.db import SessionLocal

    give_points(db_session, seeded_pair["a"]["user"], 60)

    from starlette.testclient import TestClient

    from app.main import app

    tokens = login(TestClient(app, base_url="http://t"), "alpha", "pw-alpha")
    results = []
    barrier = threading.Barrier(2)

    def attempt(name):
        client = TestClient(
            app, base_url="http://t",
            headers={"Authorization": f"Bearer {tokens['token']}"},
        )
        barrier.wait()
        response = buy(client, "first_spark", f"race-{name}")
        results.append(response.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one purchase succeeded; the other was refused (insufficient or race).
    assert sorted(results) == [201, 409], results

    db = SessionLocal()
    user = db.get(type(seeded_pair["a"]["user"]), seeded_pair["a"]["user"].id)
    assert user.points_balance == 10  # 60 - 50, never negative
    db.close()


def test_rewards_catalog_and_ownership(clients, db_session, seeded_pair):
    give_points(db_session, seeded_pair["a"]["user"], 300)
    buy(clients["a"], "first_spark", "cat-1")
    catalog = clients["a"].get("/api/v1/rewards").json()
    prices = {r["id"]: r["price"] for r in catalog["rewards"]}
    assert prices == {"first_spark": 50, "adventure_pair": 100, "heart_duo": 200}
    owned = {r["id"] for r in catalog["rewards"] if r["owned"]}
    assert owned == {"first_spark"}


def test_sse_hello_and_state_event(api, clients, seeded_pair):
    """SSE stream sends hello, then a state event when the pair's state changes."""
    import json

    with clients["a"].stream("GET", "/api/v1/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        # Read the hello event first.
        lines = []
        it = response.iter_lines()
        for line in it:
            lines.append(line)
            if line == "":
                break
        hello = "\n".join(lines)
        assert "event: hello" in hello
        assert "state_version" in hello

        # Trigger a state change: user B toggles sharing (bumps version).
        clients["b"].put("/api/v1/me/location-sharing", json={"enabled": False})

        # Expect a state event to arrive on the stream (bounded by keepalives).
        got_state = False
        buffer = []
        blocks = 0
        for line in it:
            if line == "":
                payload = "\n".join(buffer)
                buffer = []
                if "event: state" in payload:
                    data_line = next(l for l in payload.splitlines() if l.startswith("data: "))
                    event = json.loads(data_line[6:])
                    assert "state_version" in event
                    got_state = True
                    break
                blocks += 1
                if blocks > 3:
                    break  # a few keepalives with no event: fail below
                continue
            buffer.append(line)
        assert got_state, "no state event observed after location-sharing toggle"


def test_partner_position_respects_sharing_toggle(clients):
    # Insert a valid GPS record for B's device through the telemetry API.
    from datetime import datetime, timedelta, timezone

    from tests.integration.test_telemetry_and_sessions import post_batch, rec

    t = datetime.now(timezone.utc)
    post_batch(
        clients["b"], clients["b_device"],
        [rec(1, 0, gps={"valid": True, "latitude": 35.0, "longitude": 135.0, "fix_age_ms": 0})],
    )

    state = clients["a"].get(f"/api/v1/devices/{clients['a_device']}/state").json()
    assert state["partner_position"] is not None
    assert state["partner_position"]["latitude"] == 35.0
    assert state["partner_alias"] == 2

    # B disables sharing: partner position must disappear.
    clients["b"].put("/api/v1/me/location-sharing", json={"enabled": False})
    state = clients["a"].get(f"/api/v1/devices/{clients['a_device']}/state").json()
    assert state["partner_position"] is None


def test_time_endpoint(api):
    response = api.get("/api/v1/time")
    assert response.status_code == 200
    body = response.json()
    assert "server_time" in body and body["unix_ms"] > 1_600_000_000_000


def test_health_endpoint(api):
    response = api.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
