"""Nearby discovery: profile eligibility, durable last-known GPS positions,
BLE observation presence, and combined results (docs/DISCOVERY_PLAN.md).

Honesty rules encoded here:
- Actual fix time is captured_at - gps_fix_age_ms; upload receipt time is
  never used as fix time.
- Positions classify fresh (<= 30 s), last_known (<= 900 s), expired; age
  is recomputed at read time from the stored fix_time.
- Invalid/no-fix records never erase a stored position; older, repeated or
  delayed records never replace or rejuvenate a newer fix.
- Distances shown to clients are rounded to the nearest 50 m; filtering
  uses the unrounded value.
- BLE presence requires a physical observation no older than 15 s at query
  time; retransmitted (duplicate-identity) observations cannot revive it.
- Quest scoring never reads from this module: discovery data can never
  satisfy explore or grant points (quest boundary in DISCOVERY_PLAN.md).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    INTEREST_TAGS,
    Device,
    DiscoveryObservation,
    DiscoverySetting,
    DiscoveryToken,
    LastKnownPosition,
    Partnership,
    PartnershipMember,
    User,
    UserInterest,
)

# --- Classification helpers (pure; testable at exact boundaries) ---


def classify_position(fix_time: datetime, now: datetime) -> str:
    """fresh <= 30 s inclusive; last_known <= 900 s inclusive; expired beyond."""
    settings = get_settings()
    if fix_time.tzinfo is None:
        fix_time = fix_time.replace(tzinfo=timezone.utc)
    age = (now - fix_time).total_seconds()
    if age <= settings.discovery_fresh_seconds:
        return "fresh"
    if age <= settings.discovery_expiry_seconds:
        return "last_known"
    return "expired"


def age_seconds(fix_time: datetime, now: datetime) -> int:
    if fix_time.tzinfo is None:
        fix_time = fix_time.replace(tzinfo=timezone.utc)
    return max(0, int((now - fix_time).total_seconds()))


def round_distance_50(meters: float) -> int:
    """Distance shown to clients: nearest 50 m (approximate by design)."""
    return int(round(meters / 50.0) * 50)


def profile_complete(setting: DiscoverySetting | None, interest_count: int) -> bool:
    return (
        setting is not None
        and setting.age is not None
        and setting.pref_min_age is not None
        and setting.pref_max_age is not None
        and interest_count > 0
    )


def ages_compatible(
    my: DiscoverySetting, their: DiscoverySetting
) -> bool:
    """Both users' age preferences must include the other's age."""
    return (
        their.pref_min_age is not None
        and their.pref_max_age is not None
        and my.pref_min_age is not None
        and my.pref_max_age is not None
        and my.age is not None
        and their.age is not None
        and their.pref_min_age <= my.age <= their.pref_max_age
        and my.pref_min_age <= their.age <= my.pref_max_age
    )


def shared_methods(my: DiscoverySetting, their: DiscoverySetting) -> list[str]:
    """Discovery methods enabled for BOTH users."""
    out = []
    if my.bluetooth_enabled and their.bluetooth_enabled:
        out.append("bluetooth")
    if my.gps_enabled and their.gps_enabled:
        out.append("gps")
    return out


# --- Last-known position maintenance (called from telemetry ingest) ---


def record_fix_time(record) -> datetime | None:
    """Actual fix time for a telemetry record, or None when untrustworthy.

    Trustworthy-clock rule: capture time present and uncertainty at most
    the configured maximum (2 s). The fix age is subtracted so a delayed
    upload keeps its original classification.
    """
    settings = get_settings()
    captured_at = record.captured_at
    if captured_at is None:
        return None
    uncertainty = record.clock.uncertainty_ms
    if uncertainty is None or uncertainty > settings.clock_uncertainty_max_ms:
        return None
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    age_ms = record.gps.fix_age_ms or 0
    return captured_at - timedelta(milliseconds=age_ms)


def update_last_known_position(
    db: Session, user_id: uuid.UUID, latitude: float, longitude: float,
    fix_time: datetime, now: datetime,
) -> bool:
    """Store a trustworthy valid fix; monotonic in fix_time.

    Returns True when the stored position changed. Future fixes beyond the
    clock-uncertainty tolerance are rejected until the timeline resolves.
    Never erases or refreshes an existing row with a non-newer fix.
    """
    settings = get_settings()
    if fix_time.tzinfo is None:
        fix_time = fix_time.replace(tzinfo=timezone.utc)
    tolerance = timedelta(milliseconds=settings.clock_uncertainty_max_ms)
    if fix_time > now + tolerance:
        return False  # future/unknown-time fix: reject for discovery

    row = db.get(LastKnownPosition, user_id)
    if row is not None:
        stored = row.fix_time
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        if fix_time <= stored:
            return False  # older/repeated/delayed: keep the newer fix
        row.latitude = latitude
        row.longitude = longitude
        row.fix_time = fix_time
        row.updated_at = now
    else:
        db.add(
            LastKnownPosition(
                user_id=user_id, latitude=latitude, longitude=longitude,
                fix_time=fix_time, updated_at=now,
            )
        )
    return True


def ingest_positions_from_records(db: Session, owner_user_id, records, now: datetime) -> int:
    """Apply the update rule to newly accepted telemetry records."""
    changed = 0
    for record in records:
        if not record.gps.valid:
            continue  # invalid reading must not erase the last valid position
        fix_time = record_fix_time(record)
        if fix_time is None:
            continue
        if record.gps.latitude is None or record.gps.longitude is None:
            continue
        if update_last_known_position(
            db, owner_user_id, record.gps.latitude, record.gps.longitude,
            fix_time, now,
        ):
            changed += 1
    return changed


# --- BLE observation presence ---


def ble_visible_tokens(db: Session, observer_user_id: uuid.UUID, now: datetime) -> dict[int, datetime]:
    """Map token_value -> latest qualifying observation time (<= 15 s old)."""
    settings = get_settings()
    cutoff = now - timedelta(seconds=settings.discovery_ble_observation_seconds)
    rows = (
        db.query(DiscoveryObservation)
        .filter(
            DiscoveryObservation.observer_user_id == observer_user_id,
            DiscoveryObservation.captured_at >= cutoff,
        )
        .all()
    )
    latest: dict[int, datetime] = {}
    for row in rows:
        captured = row.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        if row.observed_token not in latest or captured > latest[row.observed_token]:
            latest[row.observed_token] = captured
    return latest


def live_token_owners(db: Session) -> dict[int, uuid.UUID]:
    """Map live (non-revoked) discovery token -> owning user id."""
    rows = (
        db.query(DiscoveryToken, Device)
        .join(Device, Device.id == DiscoveryToken.device_id)
        .filter(DiscoveryToken.revoked_at.is_(None))
        .all()
    )
    return {token.token_value: device.owner_user_id for token, device in rows if device.owner_user_id}


def active_member_user_ids(db: Session) -> set[uuid.UUID]:
    rows = (
        db.query(PartnershipMember.user_id)
        .join(Partnership, Partnership.id == PartnershipMember.partnership_id)
        .filter(PartnershipMember.left_at.is_(None), Partnership.ended_at.is_(None))
        .all()
    )
    return {r[0] for r in rows}


# --- Combined discovery query ---


def _candidate_rows(db: Session, requesting_user_id: uuid.UUID) -> list[tuple[User, DiscoverySetting, list[str]]]:
    """Users with complete profiles, excluding self and actively partnered."""
    settings_rows = db.query(DiscoverySetting).filter(
        DiscoverySetting.age.isnot(None),
        DiscoverySetting.pref_min_age.isnot(None),
        DiscoverySetting.pref_max_age.isnot(None),
    ).all()
    interest_rows = db.query(UserInterest).all()
    interests_by_user: dict[uuid.UUID, set[str]] = {}
    for row in interest_rows:
        interests_by_user.setdefault(row.user_id, set()).add(row.tag)

    partnered = active_member_user_ids(db)
    users = {u.id: u for u in db.query(User).all()}

    out = []
    for setting in settings_rows:
        uid = setting.user_id
        if uid == requesting_user_id or uid in partnered:
            continue
        tags = interests_by_user.get(uid, set())
        if not tags:  # incomplete profile: no interests chosen
            continue
        user = users.get(uid)
        if user is None:
            continue
        out.append((user, setting, sorted(tags)))
    return out


def discovery_snapshot(db: Session, requesting_user_id: uuid.UUID, now: datetime) -> dict:
    """Assemble the combined Bluetooth + GPS discovery result list."""
    settings = get_settings()

    my_setting = db.get(DiscoverySetting, requesting_user_id)
    my_interests = {
        row.tag
        for row in db.query(UserInterest)
        .filter(UserInterest.user_id == requesting_user_id)
        .all()
    }
    notices: list[dict] = []

    _, partner_id = _active_partner_of(db, requesting_user_id)
    if not profile_complete(my_setting, len(my_interests)):
        return _snapshot(
            now, "missing", [{"code": "profile_incomplete",
                              "message": "Complete your discovery profile to see nearby people."}],
            [],
        )
    if partner_id is not None:
        return _snapshot(
            now, "missing", [{"code": "partnered",
                              "message": "You already have a partner; end the partnership to rediscover."}],
            [],
        )

    # Requester position state drives both filtering and notices.
    my_pos = db.get(LastKnownPosition, requesting_user_id)
    my_state = "missing"
    my_age = None
    if my_pos is not None:
        my_state = classify_position(my_pos.fix_time, now)
        my_age = age_seconds(my_pos.fix_time, now)
    if my_state == "last_known":
        notices.append({
            "code": "near_last_known",
            "message": "Near your last GPS location",
            "age_seconds": my_age,
        })
    elif my_state == "expired":
        notices.append({
            "code": "gps_expired",
            "message": "GPS location expired\u2014go outdoors to refresh.",
            "age_seconds": my_age,
        })
    elif my_state == "missing":
        notices.append({
            "code": "gps_missing",
            "message": "Waiting for wearable GPS fix.",
        })

    ble_tokens = ble_visible_tokens(db, requesting_user_id, now)
    token_owner = live_token_owners(db)

    results: dict[uuid.UUID, dict] = {}
    for user, setting, tags in _candidate_rows(db, requesting_user_id):
        if not ages_compatible(my_setting, setting):
            continue
        shared = sorted(my_interests & set(tags))
        if not shared:
            continue
        methods = shared_methods(my_setting, setting)
        if not methods:
            continue

        entry = {
            "user_id": user.id,
            "display_name": user.display_name,
            "shared_interests": shared,
            "shared_count": len(shared),
            "sources": [],
            "bluetooth": None,
            "gps": None,
        }

        if "bluetooth" in methods:
            # Which live tokens seen by my device belong to this user?
            seen_at = None
            for token, observed_at in ble_tokens.items():
                if token_owner.get(token) == user.id:
                    if seen_at is None or observed_at > seen_at:
                        seen_at = observed_at
            if seen_at is not None:
                entry["sources"].append("bluetooth")
                entry["bluetooth"] = {
                    "label": "Detected nearby",
                    "observed_at": seen_at,
                }

        if "gps" in methods and my_state in ("fresh", "last_known") and my_pos is not None:
            their_pos = db.get(LastKnownPosition, user.id)
            if their_pos is not None:
                their_state = classify_position(their_pos.fix_time, now)
                if their_state in ("fresh", "last_known"):
                    from app.services.evidence import haversine_m

                    distance = haversine_m(
                        my_pos.latitude, my_pos.longitude,
                        their_pos.latitude, their_pos.longitude,
                    )
                    if distance <= my_setting.discovery_radius_m:
                        labels = []
                        their_age = age_seconds(their_pos.fix_time, now)
                        if their_state == "last_known":
                            labels.append("Based on their last GPS location")
                        entry["sources"].append("gps")
                        entry["gps"] = {
                            "distance_m": round_distance_50(distance),
                            "freshness": their_state,
                            "my_age_seconds": my_age if my_state == "last_known" else None,
                            "their_age_seconds": their_age if their_state == "last_known" else None,
                            "labels": labels,
                        }

        if entry["sources"]:
            results[user.id] = entry

    # Rank: shared-interest count desc, then display name, then user id.
    ordered = sorted(
        results.values(),
        key=lambda e: (-e["shared_count"], e["display_name"], str(e["user_id"])),
    )
    return _snapshot(now, my_state, notices, ordered)


def _snapshot(now: datetime, position_state: str, notices: list, results: list) -> dict:
    return {
        "generated_at": now,
        "position_state": position_state,
        "notices": notices,
        "results": results,
    }


def _active_partner_of(db: Session, user_id: uuid.UUID):
    from app.deps import get_pair_partner

    return get_pair_partner(db, user_id)


# --- Interest catalog ---


def interest_catalog() -> tuple[str, ...]:
    return INTEREST_TAGS


def user_interests(db: Session, user_id: uuid.UUID) -> list[str]:
    return sorted(
        row.tag
        for row in db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
    )
