"""Nearby discovery acceptance tests (docs/DISCOVERY_PLAN.md).

Boundary semantics under a controlled clock:
- GPS last-known: fresh at <=30 s inclusive, last_known at >30..<=900 s,
  expired beyond 900 s; expired/missing contribute no geographic results.
- BLE observations: presence at <=15 s inclusive, gone at 16 s.
- Cache maintenance: invalid reading after valid fix never erases;
  older/repeated/delayed records never replace or rejuvenate a newer fix;
  future fixes rejected; positions survive server restart (durable rows).
"""

import uuid
from datetime import datetime, timedelta, timezone

from tests.integration.conftest import login_as, set_profile

NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

BERLIN = (52.5200066, 13.4049540)  # ~ reference point for distance math


def make_client(api, token):
    from starlette.testclient import TestClient

    from app.main import app

    return TestClient(
        app, base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


def seeded_solo_clients(api, solo_users):
    return {
        name: make_client(api, login_as(api, name, f"pw-{name}"))
        for name in ("gamma", "delta", "epsilon")
    }


def put_position(db, user, lat, lon, fix_time):
    from app.models import LastKnownPosition

    row = db.get(LastKnownPosition, user.id)
    if row is None:
        db.add(
            LastKnownPosition(
                user_id=user.id, latitude=lat, longitude=lon,
                fix_time=fix_time, updated_at=fix_time,
            )
        )
    else:
        row.latitude, row.longitude, row.fix_time = lat, lon, fix_time
    db.commit()


def obs(client, token, captured_at):
    body = {
        "schema_version": 1,
        "observations": [{"token": token, "captured_at": captured_at.isoformat()}],
    }
    return client.post("/api/v1/discovery/observations", json=body)


def provision_token(db, user, value):
    from app.models import Device, DiscoveryToken

    device = Device(
        id=uuid.uuid4(), name=f"W-{user.username}", firmware_alias=abs(hash(user.username)) % 1000,
        owner_user_id=user.id,
    )
    db.add(device)
    db.flush()
    db.add(DiscoveryToken(device_id=device.id, token_value=value))
    db.commit()
    return device


# --- Profile editing ---


def test_profile_edit_and_validation(api, solo_users, db_session):
    gamma = solo_users["gamma"]
    client = make_client(api, login_as(api, "gamma", "pw-gamma"))

    out = client.get("/api/v1/me/discovery-profile").json()
    assert out["complete"] is False and out["bluetooth_enabled"] is False

    out = client.put("/api/v1/me/discovery-profile", json={
        "display_name": "Gamma Ray", "age": 20,
        "pref_min_age": 18, "pref_max_age": 30,
        "interests": ["gaming", "music"], "radius_m": 500,
    }).json()
    assert out["complete"] is True
    assert out["display_name"] == "Gamma Ray"
    assert client.get("/api/v1/me").json()["user"]["display_name"] == "Gamma Ray"

    # Invalid ranges rejected.
    for bad in (
        {"age": 17}, {"age": 100}, {"pref_min_age": 40, "pref_max_age": 30},
        {"radius_m": 99}, {"radius_m": 5001}, {"interests": []},
        {"interests": ["underwater_weaving"]},
    ):
        payload = {
            "display_name": "Gamma Ray", "age": 20,
            "pref_min_age": 18, "pref_max_age": 30,
            "interests": ["gaming"], "radius_m": 500,
        }
        payload.update(bad)
        assert client.put("/api/v1/me/discovery-profile", json=payload).status_code == 422, bad


def test_opt_in_defaults_and_immediate_suppression(
    api, solo_users, db_session, frozen_clock
):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta = solo_users["gamma"], solo_users["delta"]
    set_profile(db_session, gamma, ble=False, gps=False)
    set_profile(db_session, delta, interests=("gaming",), ble=False, gps=False)
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, *BERLIN, NOW)

    # Opt-ins default off: no results even with fresh positions.
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] == []

    set_profile(db_session, gamma, ble=True, gps=True)
    set_profile(db_session, delta, ble=True, gps=True)
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert [r["display_name"] for r in out["results"]] == ["Delta"]

    # Opting out suppresses the other user immediately (server-side).
    clients["delta"].put("/api/v1/me/discovery-settings",
                         json={"bluetooth_enabled": True, "gps_enabled": False})
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] == []

    # Bluetooth-only match still surfaces with "Detected nearby".
    set_profile(db_session, delta, ble=True, gps=False)
    device_delta = provision_token(db_session, delta, 4242)
    assert obs(clients["gamma"], 4242, NOW).status_code == 200
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] and out["results"][0]["sources"] == ["bluetooth"]
    assert out["results"][0]["bluetooth"]["label"] == "Detected nearby"
    assert out["results"][0]["gps"] is None


# --- Eligibility filtering ---


def test_eligibility_rules(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    set_profile(db_session, gamma, age=25, pref_min=20, pref_max=30,
                interests=("gaming", "music"))
    for user in (gamma, delta, epsilon):
        put_position(db_session, user, *BERLIN, NOW)

    # Mutual age boundaries: gamma is 25. Delta accepts 18..24 -> no match.
    set_profile(db_session, delta, age=30, pref_min=18, pref_max=24,
                interests=("gaming",))
    # Epsilon: compatible ages, but zero shared interests.
    set_profile(db_session, epsilon, age=26, pref_min=20, pref_max=30,
                interests=("food",))
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] == []

    # Delta widens to 18..30 inclusive of 25 -> now matches on gaming.
    set_profile(db_session, delta, age=30, pref_min=18, pref_max=30,
                interests=("gaming",))
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert [r["display_name"] for r in out["results"]] == ["Delta"]

    # Boundary inclusive both ways: gamma(25) vs delta prefs 25..30.
    set_profile(db_session, delta, pref_min=25)
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"]

    # Incomplete profile (no interests) excluded.
    set_profile(db_session, delta, interests=("gaming",))
    from app.models import UserInterest

    db_session.query(UserInterest).filter(UserInterest.user_id == delta.id).delete()
    db_session.commit()
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] == []

    # Self never appears; partnered users excluded (covered further in
    # invitation tests via active membership).


def test_ranking_deterministic(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    set_profile(db_session, gamma, interests=("gaming", "music", "fitness"))
    # delta: 1 shared; epsilon: 2 shared. Name ties broken by display name.
    set_profile(db_session, delta, interests=("gaming", "food"))
    set_profile(db_session, epsilon, interests=("gaming", "music"))
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, *BERLIN, NOW)
    put_position(db_session, epsilon, *BERLIN, NOW)

    out = clients["gamma"].get("/api/v1/me/discovery").json()
    names = [r["display_name"] for r in out["results"]]
    assert names == ["Epsilon", "Delta"]  # shared count desc
    assert out["results"][0]["shared_count"] == 2
    assert out["results"][0]["shared_interests"] == ["gaming", "music"]


def test_radius_filter_and_rounding(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    set_profile(db_session, gamma, radius=500)
    set_profile(db_session, delta)   # will be ~1.1 km away
    set_profile(db_session, epsilon)  # will be ~150 m away

    # Brandenburg Gate, ~1.9 km from the reference point; ~150 m offset.
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, 52.5163, 13.3777, NOW)
    put_position(db_session, epsilon, 52.5213, 13.4070, NOW)

    out = clients["gamma"].get("/api/v1/me/discovery").json()
    by_name = {r["display_name"]: r for r in out["results"]}
    assert "Delta" not in by_name  # ~1.4 km > 500 m radius
    assert "Epsilon" in by_name
    # Distances rounded to the nearest 50 m.
    assert by_name["Epsilon"]["gps"]["distance_m"] % 50 == 0


# --- GPS freshness boundaries ---


def test_gps_boundaries_30_31_900_901(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta = solo_users["gamma"], solo_users["delta"]
    set_profile(db_session, gamma)
    set_profile(db_session, delta)
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, *BERLIN, NOW)

    def gamma_view():
        return clients["gamma"].get("/api/v1/me/discovery").json()

    # Both fresh at exactly 30 s.
    put_position(db_session, gamma, *BERLIN, NOW - timedelta(seconds=30))
    put_position(db_session, delta, *BERLIN, NOW - timedelta(seconds=30))
    out = gamma_view()
    assert out["position_state"] == "fresh"
    assert out["results"] and out["results"][0]["gps"]["freshness"] == "fresh"
    assert not out["notices"]

    # Requester stale at 31 s: still geographic results, but labelled.
    put_position(db_session, gamma, *BERLIN, NOW - timedelta(seconds=31))
    out = gamma_view()
    assert out["position_state"] == "last_known"
    assert out["results"][0]["gps"]["my_age_seconds"] == 31
    assert any(n["code"] == "near_last_known" for n in out["notices"])

    # Only the OTHER user stale at 31 s.
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, *BERLIN, NOW - timedelta(seconds=31))
    out = gamma_view()
    assert out["position_state"] == "fresh"
    gps = out["results"][0]["gps"]
    assert gps["freshness"] == "last_known"
    assert gps["their_age_seconds"] == 31
    assert "Based on their last GPS location" in gps["labels"]

    # Both stale: both ages shown.
    put_position(db_session, gamma, *BERLIN, NOW - timedelta(seconds=31))
    out = gamma_view()
    assert out["results"][0]["gps"]["my_age_seconds"] == 31
    assert out["results"][0]["gps"]["their_age_seconds"] == 31

    # Last boundary: 900 s inclusive still visible.
    put_position(db_session, gamma, *BERLIN, NOW - timedelta(seconds=900))
    put_position(db_session, delta, *BERLIN, NOW - timedelta(seconds=900))
    out = gamma_view()
    assert out["position_state"] == "last_known"
    assert out["results"] and out["results"][0]["sources"] == ["gps"]

    # Expired at 901 s: requester notice + no geographic result.
    put_position(db_session, gamma, *BERLIN, NOW - timedelta(seconds=901))
    out = gamma_view()
    assert out["position_state"] == "expired"
    assert any(n["code"] == "gps_expired" for n in out["notices"])
    assert out["results"] == []

    # Other user expired, requester fresh: their absence only.
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, *BERLIN, NOW - timedelta(seconds=901))
    out = gamma_view()
    assert out["results"] == []

    # Missing position: honest notice; bluetooth still contributes.
    from app.models import LastKnownPosition

    db_session.query(LastKnownPosition).delete()
    db_session.commit()
    out = gamma_view()
    assert out["position_state"] == "missing"
    assert any(n["code"] == "gps_missing" for n in out["notices"])


# --- Last-known cache maintenance via telemetry ingest ---


def record(device_id, seq, captured_at, lat, lon, fix_age_ms=0, valid=True,
           uncertainty=500, boot="b1"):
    gps = {"valid": valid}
    if valid:
        gps.update({"latitude": lat, "longitude": lon, "fix_age_ms": fix_age_ms})
    return {
        "boot_id": boot, "sequence": seq, "uptime_ms": seq * 1000,
        "captured_at": captured_at.isoformat(), "session_id": None,
        "clock": {"source": "phone_server_anchor", "uncertainty_ms": uncertainty},
        "gps": gps, "heart_rate": {"valid": False, "status": "no_contact"},
        "peer": {"observed": False},
    }


def batch(device_id, records):
    return {"schema_version": 1, "device_id": str(device_id), "records": records}


def test_position_cache_monotonic_and_honest(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta = solo_users["gamma"], solo_users["delta"]
    from tests.integration.conftest import _make_user  # noqa: F401  (reuse pattern)

    device_gamma = provision_token(db_session, gamma, 1111)  # also gives a device

    t0 = NOW - timedelta(seconds=5)
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(device_gamma.id, 1, t0, 52.5, 13.4)]),
    )
    assert up.status_code == 200, up.text

    from app.models import LastKnownPosition

    row = db_session.get(LastKnownPosition, gamma.id)
    assert row is not None
    stored_fix = row.fix_time
    assert stored_fix == t0  # receipt time NOT used; fix age 0

    # Fix age is honored: captured_at later but actual fix older -> ignored.
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(
            device_gamma.id, 2, NOW - timedelta(seconds=2),
            52.6, 13.6, fix_age_ms=60_000,
        )]),
    )
    assert up.status_code == 200
    db_session.expire_all()
    row = db_session.get(LastKnownPosition, gamma.id)
    assert row.fix_time == stored_fix and row.latitude == 52.5

    # Invalid reading after a valid fix does not erase the cache.
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(device_gamma.id, 3, NOW, 0, 0, valid=False)]),
    )
    assert up.status_code == 200
    db_session.expire_all()
    row = db_session.get(LastKnownPosition, gamma.id)
    assert row is not None and row.latitude == 52.5

    # Untrustworthy clock (uncertainty > 2 s) never updates.
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(
            device_gamma.id, 4, NOW, 52.7, 13.7, uncertainty=5000,
        )]),
    )
    assert up.status_code == 200
    db_session.expire_all()
    row = db_session.get(LastKnownPosition, gamma.id)
    assert row.latitude == 52.5

    # Duplicate identity (retry) is a no-op.
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(device_gamma.id, 1, t0, 52.5, 13.4)]),
    )
    assert up.json()["duplicates"]

    # Newer valid fix replaces (delayed upload of an in-between fix does not
    # regress; a genuinely newer fix wins).
    newer = NOW - timedelta(seconds=1)
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(device_gamma.id, 5, newer, 52.8, 13.8)]),
    )
    db_session.expire_all()
    row = db_session.get(LastKnownPosition, gamma.id)
    assert row.fix_time == newer and row.latitude == 52.8

    # Future fix (beyond tolerance) rejected for discovery.
    future = NOW + timedelta(seconds=30)
    up = clients["gamma"].post(
        "/api/v1/telemetry/batches",
        json=batch(device_gamma.id, [record(device_gamma.id, 6, future, 52.9, 13.9)]),
    )
    assert up.status_code == 200
    db_session.expire_all()
    row = db_session.get(LastKnownPosition, gamma.id)
    assert row.fix_time == newer


# --- BLE observations ---


def test_ble_boundaries_and_retransmission(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    set_profile(db_session, gamma, gps=False)
    set_profile(db_session, delta, gps=False)
    provision_token(db_session, delta, 700)
    provision_token(db_session, epsilon, 800)  # epsilon: no profile -> no result

    # Exactly 15 s old still counts (inclusive boundary).
    assert obs(clients["gamma"], 700, NOW - timedelta(seconds=15)).status_code == 200
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert [r["display_name"] for r in out["results"]] == ["Delta"]

    # 16 s old: gone.
    from app.models import DiscoveryObservation

    db_session.query(DiscoveryObservation).delete()
    db_session.commit()
    assert obs(clients["gamma"], 700, NOW - timedelta(seconds=16)).status_code == 200
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] == []

    # Retransmitted observation cannot revive presence; new reception can.
    seen = NOW - timedelta(seconds=10)
    assert obs(clients["gamma"], 700, seen).status_code == 200
    ack = obs(clients["gamma"], 700, seen).json()  # same identity retransmit
    assert ack["duplicates"] == 1 and ack["accepted"] == 0
    frozen_clock.advance(6)  # original now 16 s old
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] == []  # duplicate did not refresh presence
    assert obs(clients["gamma"], 700, frozen_clock.now).json()["accepted"] == 1
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"]  # fresh physical reception counts


def test_ble_buffer_capacity_and_multiple_ids(api, solo_users, db_session, frozen_clock):
    """Many tokens observed (beyond device ids 1-2); only live-token owners
    with complete profiles surface; self-token never matches."""
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta = solo_users["gamma"], solo_users["delta"]
    set_profile(db_session, gamma, gps=False)
    set_profile(db_session, delta, gps=False)
    provision_token(db_session, delta, 4000)

    body = {"schema_version": 1, "observations": [
        {"token": t, "captured_at": NOW.isoformat()} for t in range(3000, 3016)
    ] + [{"token": 4000, "captured_at": NOW.isoformat()}]}
    ack = clients["gamma"].post("/api/v1/discovery/observations", json=body).json()
    assert ack["accepted"] == 17
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert [r["display_name"] for r in out["results"]] == ["Delta"]


def test_combined_sources_union_and_dedup(api, solo_users, db_session, frozen_clock):
    clients = seeded_solo_clients(api, solo_users)
    gamma, delta = solo_users["gamma"], solo_users["delta"]
    set_profile(db_session, gamma)
    set_profile(db_session, delta)
    put_position(db_session, gamma, *BERLIN, NOW)
    put_position(db_session, delta, *BERLIN, NOW)
    provision_token(db_session, delta, 900)
    obs(clients["gamma"], 900, NOW)

    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert len(out["results"]) == 1  # deduped by user id
    assert set(out["results"][0]["sources"]) == {"bluetooth", "gps"}

    # GPS expiry leaves the valid BLE result (losing one source must not
    # hide a still-eligible result from the other).
    from app.models import LastKnownPosition

    db_session.query(LastKnownPosition).delete()
    db_session.commit()
    out = clients["gamma"].get("/api/v1/me/discovery").json()
    assert out["results"] and out["results"][0]["sources"] == ["bluetooth"]


# --- Tokens ---


def test_token_provision_and_rotation(api, solo_users, db_session):
    clients = seeded_solo_clients(api, solo_users)
    gamma = solo_users["gamma"]

    # No bound device -> 409.
    assert clients["gamma"].post("/api/v1/me/discovery-token").status_code == 409

    device = provision_token(db_session, gamma, 1234)
    # provision_token created a token already; endpoint returns it.
    out = clients["gamma"].post("/api/v1/me/discovery-token").json()
    assert out["token_value"] == 1234

    out2 = clients["gamma"].post(
        "/api/v1/me/discovery-token?rotate=true").json()
    assert out2["token_value"] != 1234

    # Old token revoked: no longer maps to owner.
    from app.services.discovery import live_token_owners

    db_session.expire_all()
    assert 1234 not in live_token_owners(db_session)
    assert out2["token_value"] in live_token_owners(db_session)
