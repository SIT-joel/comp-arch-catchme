"""Idempotent telemetry batch ingestion."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.events import bump_state_version, get_state_version, publish_state_event
from app.models import Device, QuestSession, SessionParticipant, TelemetryRecord, User
from app.schemas import AcceptedIdentity, TelemetryAckOut, TelemetryBatchIn
from app.services.evaluation import evaluate_and_maybe_complete

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.post("/batches", response_model=TelemetryAckOut)
def ingest_batch(
    batch: TelemetryBatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.get(Device, batch.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail={"code": "device_not_found", "message": "Unknown device."})
    if device.owner_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "This device is not bound to your account."},
        )

    # Session authorization: every referenced session must belong to this pair.
    session_ids = {r.session_id for r in batch.records if r.session_id is not None}
    sessions_by_id = {}
    for sid in session_ids:
        qs = db.get(QuestSession, sid)
        if qs is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "unknown_session", "message": f"Session {sid} does not exist."},
            )
        participant = (
            db.query(SessionParticipant)
            .filter(
                SessionParticipant.session_id == sid,
                SessionParticipant.user_id == user.id,
            )
            .one_or_none()
        )
        if participant is None:
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": f"Session {sid} is not yours."},
            )
        sessions_by_id[sid] = qs

    existing = {
        (r.boot_id, r.sequence)
        for r in db.query(TelemetryRecord.boot_id, TelemetryRecord.sequence)
        .filter(
            TelemetryRecord.device_id == batch.device_id,
            TelemetryRecord.boot_id.in_({r.boot_id for r in batch.records}),
        )
        .all()
    }

    accepted: list[AcceptedIdentity] = []
    duplicates: list[AcceptedIdentity] = []
    new_rows: list[TelemetryRecord] = []
    accepted_records: list = []  # pydantic inputs for newly stored rows

    for record in batch.records:
        identity = (record.boot_id, record.sequence)
        if identity in existing:
            duplicates.append(AcceptedIdentity(boot_id=record.boot_id, sequence=record.sequence))
            continue
        existing.add(identity)
        captured_at = record.captured_at
        if captured_at is not None and captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        new_rows.append(
            TelemetryRecord(
                device_id=batch.device_id,
                boot_id=record.boot_id,
                sequence=record.sequence,
                session_id=record.session_id,
                uptime_ms=record.uptime_ms,
                captured_at=captured_at,
                clock_source=record.clock.source,
                clock_uncertainty_ms=record.clock.uncertainty_ms,
                gps_valid=record.gps.valid,
                gps_lat=record.gps.latitude,
                gps_lon=record.gps.longitude,
                gps_fix_age_ms=record.gps.fix_age_ms,
                gps_source=record.gps.source,
                hr_valid=record.heart_rate.valid,
                bpm=record.heart_rate.bpm,
                hr_status=record.heart_rate.status,
                peer_observed=record.peer.observed,
                peer_device_id=record.peer.device_id,
                peer_boot_id=record.peer.boot_id,
                peer_heartbeat_sequence=record.peer.heartbeat_sequence,
                peer_session_token=record.peer.session_token,
                peer_observation_age_ms=record.peer.observation_age_ms,
            )
        )
        accepted.append(AcceptedIdentity(boot_id=record.boot_id, sequence=record.sequence))
        accepted_records.append(record)

    db.add_all(new_rows)
    db.flush()  # evaluation below re-reads records from this transaction

    # Discovery last-known positions: trustworthy valid wearable fixes only
    # (docs/DISCOVERY_PLAN.md). Quest scoring below never reads from this
    # cache; it re-derives evidence from telemetry rows as before.
    from app import clock
    from app.services.discovery import ingest_positions_from_records

    positions_changed = ingest_positions_from_records(
        db, user.id, accepted_records, clock.now_utc()
    )

    # Recompute affected active sessions (progress is derived state).
    touched_active = {
        sid for sid, qs in sessions_by_id.items() if qs.state == "active" and new_rows
    }
    completed_now = []
    for sid in touched_active:
        quest_session = db.get(QuestSession, sid)
        before = quest_session.state
        evaluate_and_maybe_complete(db, quest_session)
        if before == "active" and quest_session.state == "completed":
            completed_now.append(quest_session)

    version = (
        bump_state_version(db) if (new_rows or completed_now or positions_changed) else get_state_version(db)
    )
    db.commit()

    if new_rows or completed_now or positions_changed:
        # Notify both pair members (progress, awards) through SSE.
        from app.deps import get_pair_partner

        _, partner_id = get_pair_partner(db, user.id)
        audience = [user.id] + ([partner_id] if partner_id else [])
        for qs in completed_now:
            publish_state_event(audience, version, session_id=qs.id, kind="session_completed")
        if touched_active - {qs.id for qs in completed_now}:
            publish_state_event(
                audience, version, kind="progress"
            )

    return TelemetryAckOut(
        server_time=datetime.now(timezone.utc),
        accepted=accepted,
        duplicates=duplicates,
        state_version=version,
    )
