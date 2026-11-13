"""Idempotent database seed: two matched users, their pair, two preprovisioned
wearables, and the three cosmetic badges.

Passwords and device pairing codes are NOT hardcoded: they come from
CM_SEED_* environment variables, or are generated randomly and printed once
to the console for local development. Never commit real credentials.
"""

import os
import sys
import uuid

sys.path.insert(0, ".")

from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AppState,
    Base,
    Device,
    Landmark,
    Partnership,
    PartnershipMember,
    Reward,
    User,
)
from app.security import hash_password, hash_token, new_token  # noqa: E402

NAMESPACE = uuid.UUID("ba5eba11-0000-4000-8000-000000000001")

REWARDS = [
    ("first_spark", "First Spark", "Complete your first shared quest together.", 50),
    ("adventure_pair", "Adventure Pair", "Finish an outdoor geofence visit together.", 100),
    ("heart_duo", "Heart Duo", "Complete a heart challenge with valid readings on both wearables.", 200),
]


def stable_uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


def gen_password() -> str:
    return new_token()[:16]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    user_specs = []
    printed = []
    for suffix, default_name in (("a", "miya"), ("b", "toma")):
        username = os.environ.get(f"CM_SEED_USER_{suffix.upper()}", default_name)
        display = os.environ.get(f"CM_SEED_DISPLAY_{suffix.upper()}", username.title())
        password = os.environ.get(f"CM_SEED_PASSWORD_{suffix.upper()}")
        if not password:
            password = gen_password()
            printed.append(f"generated password for '{username}': {password}")
        user_specs.append((username, display, password, stable_uuid(f"user-{suffix}")))

    users = {}
    for username, display, password, uid in user_specs:
        user = db.get(User, uid)
        if user is None:
            user = User(
                id=uid,
                username=username,
                display_name=display,
                password_hash=hash_password(password),
            )
            db.add(user)
        users[username] = user

    user_a, user_b = sorted(users.values(), key=lambda u: u.id)  # canonical pairing order
    db.flush()  # users must exist before the partnership's foreign keys resolve
    partnership_id = stable_uuid("pairing")
    if db.get(Partnership, partnership_id) is None and user_a.id != user_b.id:
        db.add(Partnership(id=partnership_id))
        db.flush()
        db.add_all(
            [
                PartnershipMember(partnership_id=partnership_id, user_id=user_a.id),
                PartnershipMember(partnership_id=partnership_id, user_id=user_b.id),
            ]
        )

    for index, (username, display, _pw, _uid) in enumerate(user_specs, start=1):
        alias = index
        device_id = stable_uuid(f"device-{'a' if index == 1 else 'b'}")
        device = db.get(Device, device_id)
        code = os.environ.get(f"CM_SEED_PAIRING_CODE_{'A' if index == 1 else 'B'}")
        if not code:
            code = new_token()[:12]
            printed.append(f"generated pairing code for '{username}' wearable: {code}")
        if device is None:
            db.add(
                Device(
                    id=device_id,
                    name=f"Wearable {index}",
                    firmware_alias=alias,
                    pairing_code_hash=hash_token(code),
                )
            )
        elif device.pairing_code_hash is not None and device.owner_user_id is None:
            device.pairing_code_hash = hash_token(code)  # rotate unclaimed dev code

    for rid, name, description, price in REWARDS:
        if db.get(Reward, rid) is None:
            db.add(Reward(id=rid, name=name, description=description, price=price))

    # v2 raid landmarks. PLACEHOLDER coordinates (Kyoto station plaza area)
    # until the user supplies the real demo destinations; radius 50 m.
    LANDMARKS = [
        ("landmark_a", "Clock Tower Plaza", 34.985833, 135.758766),
        ("landmark_b", "Riverside Gate", 34.985200, 135.760100),
        ("landmark_c", "Old Bridge", 34.984500, 135.761500),
    ]
    for lid, name, lat, lon in LANDMARKS:
        if db.get(Landmark, lid) is None:
            db.add(Landmark(id=lid, name=name, latitude=lat, longitude=lon, radius_m=50.0))

    state = db.get(AppState, "state_version")
    if state is None:
        db.add(AppState(key="state_version", value=0))

    db.commit()
    db.close()

    print("Seed complete: users", [u.username for u in users.values()],
          "+ pair + 2 devices + 3 rewards + landmarks.")
    if printed:
        print("NOTE (local dev only, not stored anywhere):")
        for line in printed:
            print(" ", line)


if __name__ == "__main__":
    main()
