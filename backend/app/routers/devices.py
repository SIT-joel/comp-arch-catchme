"""Device binding and phone-to-device state relay."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_pair_partner
from app.models import Device, QuestSession, SessionParticipant, User
from app.schemas import (
    BindIn,
    BindOut,
    CompletionEvent,
    DeviceStateOut,
    DeviceSummary,
    InteractionSnapshot,
    PartnerPosition,
    SessionBrief,
)
from app.security import hash_token
from app.services import evidence
from app.services.evaluation import completion_event_id, latest_valid_gps
from app.services.interactions import snapshot as interaction_snapshot
from app.events import get_state_version

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("/bind", response_model=BindOut)
def bind_device(
    body: BindIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bind a preprovisioned wearable using its one-time pairing credential."""
    device = (
        db.query(Device)
        .filter(Device.pairing_code_hash == hash_token(body.pairing_code.strip()))
        .one_or_none()
    )
    if device is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "invalid_pairing_code", "message": "Unknown or already-used pairing code."},
        )
    if device.owner_user_id is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "device_already_bound", "message": "Device is already bound to an account."},
        )
    device.owner_user_id = user.id
    device.pairing_code_hash = None  # one-time credential
    device.claimed_at = datetime.now(timezone.utc)
    db.commit()
    return BindOut(
        device=DeviceSummary(
            id=device.id,
            name=device.name,
            firmware_alias=device.firmware_alias,
            claimed_at=device.claimed_at,
        )
    )


def _session_brief(quest_session: QuestSession, db: Session, user_id: uuid.UUID) -> SessionBrief:
    return SessionBrief(
        session_id=quest_session.id,
        quest_id=quest_session.quest_id,
        demo=quest_session.demo,
        state=quest_session.state,
        token=quest_session.session_token,
        target_ms=quest_session.target_ms,
        progress_ms=quest_session.progress_ms,
        interaction=interaction_snapshot(db, quest_session, user_id),
    )


@router.get("/{device_id}/state", response_model=DeviceStateOut)
def device_state(
    device_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authorized session/partner summary for the phone to relay to the wearable."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such device."})
    if device.owner_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "This device belongs to another user."},
        )

    _, partner_id = get_pair_partner(db, user.id)
    partner_alias = None
    partner_position = None
    partner_distance_m = None
    partner_device_id = None

    if partner_id:
        partner_device = db.query(Device).filter(Device.owner_user_id == partner_id).one_or_none()
        if partner_device:
            partner_alias = partner_device.firmware_alias
            partner_device_id = partner_device.id
        partner_user = db.get(User, partner_id)
        if partner_user and partner_user.location_sharing and partner_device_id:
            gps = latest_valid_gps(db, partner_device_id)
            if gps is not None:
                now = datetime.now(timezone.utc)
                age_ms = int((now - gps.captured_at).total_seconds() * 1000) if gps.captured_at else None
                partner_position = PartnerPosition(
                    latitude=gps.gps_lat,
                    longitude=gps.gps_lon,
                    captured_at=gps.captured_at,
                    age_ms=age_ms,
                    sharing_enabled=True,
                )
        # Distance between the two wearables' latest valid fixes, if both exist.
        own_gps = latest_valid_gps(db, device_id)
        if own_gps is not None and partner_position is not None and own_gps.captured_at is not None:
            partner_distance_m = round(
                evidence.haversine_m(
                    own_gps.gps_lat, own_gps.gps_lon,
                    partner_position.latitude, partner_position.longitude,
                ),
                1,
            )

    # Current non-terminal session of this user (one active shared quest per pair).
    participation = (
        db.query(SessionParticipant, QuestSession)
        .join(QuestSession, QuestSession.id == SessionParticipant.session_id)
        .filter(
            SessionParticipant.user_id == user.id,
            QuestSession.state.in_(("pending", "active")),
        )
        .order_by(QuestSession.created_at.desc())
        .first()
    )
    brief = _session_brief(participation.QuestSession, db, user.id) if participation else None

    completion = None
    if participation is None:
        finished = (
            db.query(QuestSession)
            .join(SessionParticipant, SessionParticipant.session_id == QuestSession.id)
            .filter(
                SessionParticipant.user_id == user.id,
                QuestSession.state == "completed",
            )
            .order_by(QuestSession.completed_at.desc())
            .first()
        )
        if finished is not None:
            finished_interaction = interaction_snapshot(db, finished, user.id)
            completion = CompletionEvent(
                completion_event_id=completion_event_id(finished.id),
                session_id=finished.id,
                interaction=(
                    InteractionSnapshot(**finished_interaction)
                    if finished_interaction is not None
                    else None
                ),
            )

    return DeviceStateOut(
        state_version=get_state_version(db),
        session=brief,
        partner_alias=partner_alias,
        partner_device_id=partner_device_id,
        partner_position=partner_position,
        partner_distance_m=partner_distance_m,
        completion=completion,
        server_time=datetime.now(timezone.utc),
    )
