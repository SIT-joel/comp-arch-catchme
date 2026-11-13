"""Auth, CSRF, /me, device binding, and authorization integration tests."""

import uuid

from tests.integration.conftest import login


def test_login_rejects_bad_password(api, seeded_pair):
    response = api.post("/api/v1/auth/login", json={"username": "alpha", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_returns_user_partner_and_device(api, seeded_pair):
    tokens = login(api, "alpha", "pw-alpha")
    response = api.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {tokens['token']}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "alpha"
    assert body["user"]["level"] == 1
    assert body["partner"]["display_name"] == "Beta"
    assert body["device"]["name"] == "Wearable A"


def test_cookie_flow_requires_csrf_for_state_changes(api, seeded_pair):
    # Login via cookie (web path): response sets cookie + returns csrf token.
    response = api.post("/api/v1/auth/login", json={"username": "alpha", "password": "pw-alpha"})
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    cookie = response.cookies.get("catch_me_session")
    assert cookie

    # GET works with cookie alone.
    assert api.get("/api/v1/me").status_code == 200

    # State-changing request without CSRF header -> 403.
    bad = api.put(
        "/api/v1/me/location-sharing",
        json={"enabled": False},
    )
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "csrf_failed"

    # With CSRF header -> accepted.
    good = api.put(
        "/api/v1/me/location-sharing",
        json={"enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert good.status_code == 204


def test_logout_revokes_session(api, seeded_pair):
    tokens = login(api, "alpha", "pw-alpha")
    headers = {"Authorization": f"Bearer {tokens['token']}"}
    assert api.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert api.get("/api/v1/me", headers=headers).status_code == 401


def test_unauthenticated_requests_rejected(api):
    assert api.get("/api/v1/me").status_code == 401
    assert api.get("/api/v1/rewards").status_code == 401
    assert api.get("/api/v1/sessions").status_code == 401
    assert api.post("/api/v1/telemetry/batches", json={}).status_code == 401
    assert api.get("/api/v1/events").status_code == 401


def test_device_bind_with_one_time_code(api, db_session, seeded_pair):
    # A fresh unbound device seeded directly.
    from app.models import Device
    from app.security import hash_token

    device = Device(
        id=uuid.uuid4(), name="Wearable C", firmware_alias=3,
        pairing_code_hash=hash_token("FRESH-CODE"),
    )
    db_session.add(device)
    db_session.commit()

    tokens = login(api, "beta", "pw-beta")
    headers = {"Authorization": f"Bearer {tokens['token']}"}

    ok = api.post(
        "/api/v1/devices/bind", json={"pairing_code": "FRESH-CODE"}, headers=headers
    )
    assert ok.status_code == 200
    assert ok.json()["device"]["name"] == "Wearable C"

    # One-time: same code cannot bind again.
    replay = api.post(
        "/api/v1/devices/bind", json={"pairing_code": "FRESH-CODE"}, headers=headers
    )
    assert replay.status_code == 404


def test_cannot_read_foreign_device_state(clients):
    response = clients["a"].get(f"/api/v1/devices/{clients['b_device']}/state")
    assert response.status_code == 403
    response = clients["a"].get(f"/api/v1/devices/{uuid.uuid4()}/state")
    assert response.status_code == 404


def test_level_math_boundaries(api, db_session):
    from tests.integration.conftest import _make_user

    for xp, level in ((0, 1), (99, 1), (100, 2), (200, 3), (250, 3)):
        name = f"lvl{xp}"
        _make_user(db_session, name, xp=xp)
    db_session.commit()

    for xp, level in ((0, 1), (99, 1), (100, 2), (200, 3), (250, 3)):
        name = f"lvl{xp}"
        tokens = login(api, name, f"pw-{name}")
        response = api.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {tokens['token']}"}
        )
        body = response.json()
        assert body["user"]["level"] == level, (xp, body["user"])
