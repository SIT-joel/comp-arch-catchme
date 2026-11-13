"""Integration test fixtures.

Requires PostgreSQL at CM_TEST_DATABASE_URL (default localhost:5433 test DB).
If unreachable, integration tests SKIP with an explicit message — running them
only on SQLite would not establish PostgreSQL transaction/constraint behavior.
"""

import os
import uuid

import pytest

TEST_DB_URL = os.environ.get(
    "CM_TEST_DATABASE_URL",
    "postgresql+psycopg://catch_me:catch_me@127.0.0.1:5433/catch_me_test",
)

# Must be set before importing app modules (engine binds at import time).
os.environ["CM_DATABASE_URL"] = TEST_DB_URL

try:
    from sqlalchemy import create_engine, text

    _probe = create_engine(TEST_DB_URL)
    with _probe.connect() as _conn:
        _conn.execute(text("SELECT 1"))
    _probe.dispose()
    POSTGRES_AVAILABLE = True
    POSTGRES_REASON = ""
except Exception as exc:  # noqa: BLE001
    POSTGRES_AVAILABLE = False
    POSTGRES_REASON = f"PostgreSQL test DB unreachable at {TEST_DB_URL}: {exc}"

if not POSTGRES_AVAILABLE:
    pytest.skip(POSTGRES_REASON, allow_module_level=True)


@pytest.fixture(scope="session", autouse=True)
def db_engine():
    from app.db import engine
    from app.models import AppState, Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Mirror what backend/seed.py produces so tests cover the seeded shape too.
    with engine.begin() as conn:
        conn.execute(AppState.__table__.insert(), {"key": "state_version", "value": 0})
        # v2: raid landmarks (same placeholder set as seed.py).
        from app.models import Landmark

        for lid, name, lat, lon in [
            ("landmark_a", "Clock Tower Plaza", 34.985833, 135.758766),
            ("landmark_b", "Riverside Gate", 34.985200, 135.760100),
            ("landmark_c", "Old Bridge", 34.984500, 135.761500),
        ]:
            conn.execute(
                Landmark.__table__.insert(),
                {"id": lid, "name": name, "latitude": lat, "longitude": lon, "radius_m": 50.0},
            )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    """API handlers commit through their own sessions; wipe rows after each
    test so tests stay independent."""
    from app.db import engine
    from app.models import Base

    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in ("app_state", "landmarks"):
                continue  # seeded reference data survives across tests
            conn.execute(table.delete())


@pytest.fixture()
def db_session():
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def _make_user(db, username: str, xp: int = 0, points: int = 0):
    from app.models import User
    from app.security import hash_password

    user = User(
        id=uuid.uuid4(),
        username=username,
        display_name=username.title(),
        password_hash=hash_password(f"pw-{username}"),
        points_balance=points,
        lifetime_xp=xp,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture(autouse=True)
def seed_rewards(db_session):
    from app.models import Reward

    for rid, name, description, price in [
        ("first_spark", "First Spark", "Complete your first shared quest together.", 50),
        ("adventure_pair", "Adventure Pair", "Finish an outdoor geofence visit together.", 100),
        ("heart_duo", "Heart Duo", "Complete a heart challenge with valid readings on both wearables.", 200),
    ]:
        if db_session.get(Reward, rid) is None:
            db_session.add(Reward(id=rid, name=name, description=description, price=price))
    db_session.commit()


@pytest.fixture()
def seeded_pair(db_session):
    """Two partnered users with passwords pw-<username>, plus their devices."""
    from app.models import Device, Partnership, PartnershipMember
    from app.security import hash_token

    user_a = _make_user(db_session, "alpha")
    user_b = _make_user(db_session, "beta")
    a, b = sorted((user_a, user_b), key=lambda u: u.id)
    partnership = Partnership(id=uuid.uuid4())
    db_session.add(partnership)
    db_session.flush()
    db_session.add_all(
        [
            PartnershipMember(partnership_id=partnership.id, user_id=a.id),
            PartnershipMember(partnership_id=partnership.id, user_id=b.id),
        ]
    )

    device_a = Device(
        id=uuid.uuid4(),
        name="Wearable A",
        firmware_alias=1,
        owner_user_id=user_a.id,
        pairing_code_hash=hash_token("PAIR-A"),
    )
    device_b = Device(
        id=uuid.uuid4(),
        name="Wearable B",
        firmware_alias=2,
        owner_user_id=user_b.id,
        pairing_code_hash=hash_token("PAIR-B"),
    )
    db_session.add_all([device_a, device_b])
    db_session.commit()

    return {
        "a": {"user": user_a, "device": device_a, "password": "pw-alpha"},
        "b": {"user": user_b, "device": device_b, "password": "pw-beta"},
    }


@pytest.fixture()
def api():
    """Starlette TestClient bound to the FastAPI app (in-process, sync)."""
    from starlette.testclient import TestClient

    from app.main import app

    client = TestClient(app, base_url="http://testserver")
    try:
        yield client
    finally:
        client.close()


def login(client, username: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def clients(api, seeded_pair):
    """Two API clients (one per user) using bearer tokens, with device ids."""
    from starlette.testclient import TestClient

    from app.main import app as fastapi_app

    client_a = TestClient(
        fastapi_app,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {login(api, 'alpha', 'pw-alpha')['token']}"},
    )
    client_b = TestClient(
        fastapi_app,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {login(api, 'beta', 'pw-beta')['token']}"},
    )
    try:
        yield {
            "a": client_a,
            "b": client_b,
            "a_device": seeded_pair["a"]["device"].id,
            "b_device": seeded_pair["b"]["device"].id,
            "a_user": seeded_pair["a"]["user"].id,
            "b_user": seeded_pair["b"]["user"].id,
        }
    finally:
        client_a.close()
        client_b.close()


class FrozenClock:
    """Pins app.clock.now_utc so freshness boundaries are tested exactly."""

    def __init__(self, start):
        from datetime import datetime, timezone

        self.now = start or datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        from datetime import timedelta

        self.now = self.now + timedelta(seconds=seconds)

    def set(self, moment):
        self.now = moment


@pytest.fixture()
def frozen_clock(monkeypatch):
    import app.clock as clock_mod

    fake = FrozenClock(None)
    monkeypatch.setattr(clock_mod, "now_utc", fake)
    return fake


@pytest.fixture()
def solo_users(db_session):
    """Three UNPAIRED users (gamma/delta/epsilon) for discovery tests."""
    users = {name: _make_user(db_session, name) for name in ("gamma", "delta", "epsilon")}
    db_session.commit()
    return users


def set_profile(db, user, *, age=25, pref_min=18, pref_max=99,
                interests=("gaming", "music"), radius=500,
                ble=True, gps=True):
    """Directly persist a complete discovery profile (no HTTP round trip)."""
    from app.models import DiscoverySetting, UserInterest

    setting = db.get(DiscoverySetting, user.id)
    if setting is None:
        setting = DiscoverySetting(user_id=user.id)
        db.add(setting)
    setting.age = age
    setting.pref_min_age = pref_min
    setting.pref_max_age = pref_max
    setting.discovery_radius_m = radius
    setting.bluetooth_enabled = ble
    setting.gps_enabled = gps
    db.query(UserInterest).filter(UserInterest.user_id == user.id).delete()
    for tag in interests:
        db.add(UserInterest(user_id=user.id, tag=tag))
    db.commit()
    return setting


def login_as(api, username, password):
    return login(api, username, password)["token"]
