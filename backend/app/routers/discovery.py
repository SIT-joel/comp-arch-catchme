"""Nearby discovery endpoints (docs/DISCOVERY_PLAN.md).

- Profile editing and per-method opt-in switches (both off by default).
- Durable last-known wearable GPS positions power geographic results;
  phone location is never involved.
- Phones upload direct wearable scan observations; phones also relay the
  device's opaque discovery token, provisioned here.
- Clients poll GET /me/discovery every ~5 s while the screen is open (the
  poll drives expiry even without new SSE events).
"""

import random
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.events import bump_state_version, publish_state_event
from app.models import (
    Device,
    DiscoveryObservation,
    DiscoverySetting,
    DiscoveryToken,
    User,
    UserInterest,
)
from app.schemas import (
    DiscoveryOut,
    DiscoveryProfileIn,
    DiscoveryProfileOut,
    DiscoverySettingsIn,
    DiscoveryTokenOut,
    ObservationAckOut,
    ObservationBatchIn,
)
from app.services import discovery as discovery_service

router = APIRouter(prefix="/api/v1", tags=["discovery"])


def _serialize_profile(db: Session, user: User) -> DiscoveryProfileOut:
    setting = db.get(DiscoverySetting, user.id)
    interests = discovery_service.user_interests(db, user.id)
    if setting is None:
        return DiscoveryProfileOut(
            display_name=user.display_name,
            interests=[],
            radius_m=get_settings().discovery_radius_default_m,
            bluetooth_enabled=False,
            gps_enabled=False,
            complete=False,
        )
    return DiscoveryProfileOut(
        display_name=user.display_name,
        age=setting.age,
        pref_min_age=setting.pref_min_age,
        pref_max_age=setting.pref_max_age,
        interests=interests,
        radius_m=setting.discovery_radius_m,
        bluetooth_enabled=setting.bluetooth_enabled,
        gps_enabled=setting.gps_enabled,
        complete=discovery_service.profile_complete(setting, len(interests)),
    )


@router.get("/me/discovery-profile", response_model=DiscoveryProfileOut)
def get_discovery_profile(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return _serialize_profile(db, user)


@router.put("/me/discovery-profile", response_model=DiscoveryProfileOut)
def put_discovery_profile(
    body: DiscoveryProfileIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit display name + discovery profile fields atomically."""
    user.display_name = body.display_name.strip() or user.display_name
    setting = db.get(DiscoverySetting, user.id)
    if setting is None:
        setting = DiscoverySetting(user_id=user.id)
        db.add(setting)
    setting.age = body.age
    setting.pref_min_age = body.pref_min_age
    setting.pref_max_age = body.pref_max_age
    setting.discovery_radius_m = body.radius_m
    setting.updated_at = clock.now_utc()

    db.query(UserInterest).filter(UserInterest.user_id == user.id).delete()
    db.add_all(
        [UserInterest(user_id=user.id, tag=tag) for tag in sorted(set(body.interests))]
    )

    version = bump_state_version(db)
    db.commit()
    publish_state_event([user.id], version, kind="profile_changed")
    db.refresh(user)
    return _serialize_profile(db, user)


@router.put("/me/discovery-settings", response_model=DiscoveryProfileOut)
def put_discovery_settings(
    body: DiscoverySettingsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Flip the separate Bluetooth/GPS discovery opt-ins.

    The server suppresses an opted-out user immediately on every query,
    regardless of device connectivity; the phone relays the change to the
    wearable's radio on its next link.
    """
    setting = db.get(DiscoverySetting, user.id)
    if setting is None:
        setting = DiscoverySetting(user_id=user.id)
        db.add(setting)
    setting.bluetooth_enabled = body.bluetooth_enabled
    setting.gps_enabled = body.gps_enabled
    setting.updated_at = clock.now_utc()

    version = bump_state_version(db)
    db.commit()
    publish_state_event([user.id], version, kind="discovery_settings_changed")
    return _serialize_profile(db, user)


@router.get("/me/discovery", response_model=DiscoveryOut)
def get_discovery(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    snapshot = discovery_service.discovery_snapshot(db, user.id, clock.now_utc())
    return DiscoveryOut(**snapshot)


@router.post("/me/discovery-token", response_model=DiscoveryTokenOut)
def provision_discovery_token(
    rotate: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the bound wearable's live discovery token, creating one if
    absent. rotate=true invalidates the previous value (also done on device
    unbind/reassignment). Provisioned only through this authenticated link.
    """
    device = db.query(Device).filter(Device.owner_user_id == user.id).one_or_none()
    if device is None:
        raise HTTPException(
            409,
            {"code": "no_device", "message": "Bind your wearable before provisioning a discovery token."},
        )

    now = clock.now_utc()
    current = (
        db.query(DiscoveryToken)
        .filter(DiscoveryToken.device_id == device.id, DiscoveryToken.revoked_at.is_(None))
        .one_or_none()
    )
    if current is not None and not rotate:
        return DiscoveryTokenOut(token_value=current.token_value, device_id=device.id)
    if current is not None:
        current.revoked_at = now

    taken = {row[0] for row in db.query(DiscoveryToken.token_value).all()}
    if len(taken) >= 65536:
        raise HTTPException(503, {"code": "token_exhausted", "message": "Token space exhausted."})
    value = random.randint(0, 65535)
    while value in taken:
        value = random.randint(0, 65535)

    token = DiscoveryToken(device_id=device.id, token_value=value, created_at=now)
    db.add(token)
    db.commit()
    return DiscoveryTokenOut(token_value=value, device_id=device.id)


@router.post("/discovery/observations", response_model=ObservationAckOut)
def upload_observations(
    body: ObservationBatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Idempotent upload of direct wearable scan observations.

    Identity is (observer, token, captured_at): a retransmitted observation
    is a duplicate and cannot refresh presence; only a new physical
    reception (new captured_at) can. Old rows are pruned past a generous
    window; presence itself is derived at query time from the 15 s rule.
    """
    now = clock.now_utc()
    settings = get_settings()

    existing = {
        (row[0], row[1])
        for row in db.query(DiscoveryObservation.observed_token, DiscoveryObservation.captured_at)
        .filter(
            DiscoveryObservation.observer_user_id == user.id,
            DiscoveryObservation.observed_token.in_({o.token for o in body.observations}),
        )
        .all()
    }

    accepted = 0
    duplicates = 0
    for observation in body.observations:
        captured = observation.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        identity = (observation.token, captured)
        if identity in existing:
            duplicates += 1
            continue
        existing.add(identity)
        db.add(
            DiscoveryObservation(
                observer_user_id=user.id,
                observed_token=observation.token,
                captured_at=captured,
            )
        )
        accepted += 1

    # Bound the table: discovery presence only reads the last 15 s.
    db.query(DiscoveryObservation).filter(
        DiscoveryObservation.captured_at
        < now - timedelta(seconds=settings.discovery_expiry_seconds)
    ).delete(synchronize_session=False)

    db.commit()
    return ObservationAckOut(accepted=accepted, duplicates=duplicates)
