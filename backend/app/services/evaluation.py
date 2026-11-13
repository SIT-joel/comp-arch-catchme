"""Session progress evaluation and awarding.

Progress is recomputed from persisted telemetry for a session on every
ingestion; out-of-order or delayed records therefore converge to the same
final progress without double counting. Completion locks the session row and
grants each participant's award exactly once inside the same transaction.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import (
    Device,
    PointTransaction,
    QuestAward,
    QuestSession,
    SessionInteraction,
    SessionParticipant,
    TelemetryRecord,
    User,
)
from app.services import evidence

RECORD_FIELDS = (
    "captured_at",
    "clock_uncertainty_ms",
    "gps_valid",
    "gps_lat",
    "gps_lon",
    "gps_fix_age_ms",
    "hr_valid",
    "bpm",
    "hr_status",
    "peer_observed",
    "peer_device_id",
    "peer_boot_id",
    "peer_heartbeat_sequence",
    "peer_session_token",
    "peer_observation_age_ms",
)


def _records_as_dicts(db: Session, session_id: uuid.UUID, device_id: uuid.UUID) -> list[dict]:
    rows = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.session_id == session_id, TelemetryRecord.device_id == device_id)
        .all()
    )
    return [{name: getattr(row, name) for name in RECORD_FIELDS} for row in rows]


def session_participant_devices(db: Session, quest_session: QuestSession) -> dict:
    """Map user_id -> device_id for both participants of the session."""
    participants = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == quest_session.id)
        .all()
    )
    devices: dict = {}
    for participant in participants:
        device = (
            db.query(Device)
            .filter(Device.owner_user_id == participant.user_id)
            .one_or_none()
        )
        devices[participant.user_id] = device.id if device else None
    return devices


def evaluate_session(
    db: Session,
    quest_session: QuestSession,
    *,
    not_before: datetime | None = None,
) -> tuple[list, int]:
    """Return (qualifying intervals, total progress ms) for an active session."""
    settings = get_settings()
    devices = session_participant_devices(db, quest_session)
    user_ids = sorted(devices.keys())
    if len(user_ids) != 2:
        return [], 0
    if any(d is None for d in devices.values()):
        return [], 0

    user_a, user_b = user_ids[0], user_ids[1]
    records_a = _records_as_dicts(db, quest_session.id, devices[user_a])
    records_b = _records_as_dicts(db, quest_session.id, devices[user_b])

    kwargs: dict = {
        "records_a": records_a,
        "records_b": records_b,
        "device_a": devices[user_a],
        "device_b": devices[user_b],
        "session_token": quest_session.session_token or "",
        "peer_gap_max_ms": settings.peer_gap_max_ms,
        "clock_uncertainty_max_ms": settings.clock_uncertainty_max_ms,
    }

    if quest_session.quest_id == "together":
        intervals = evidence.together_intervals(**kwargs, not_before=not_before)
    elif quest_session.quest_id == "explore":
        if quest_session.geofence_lat is None or quest_session.geofence_lon is None:
            return [], 0
        intervals = evidence.explore_intervals(
            **kwargs,
            gps_stale_max_ms=settings.gps_stale_max_ms,
            geofence_lat=quest_session.geofence_lat,
            geofence_lon=quest_session.geofence_lon,
            geofence_radius_m=quest_session.geofence_radius_m or settings.geofence_radius_m,
        )
    else:
        # v2: heart_challenge removed; raid progress is outcome-driven, not
        # evidence-interval driven (see routers/sessions.py raid/outcome).
        return [], 0

    return intervals, evidence.total_ms(intervals)


AWARD_POINTS = 100
AWARD_XP = 100


def evaluate_and_maybe_complete(db: Session, quest_session: QuestSession) -> QuestSession:
    """Recompute progress; complete + award when the target is reached.

    Must be called inside the caller's transaction. The session row is locked
    so two concurrent ingestions cannot double-complete.
    """
    from app.events import bump_state_version, publish_state_event

    locked = (
        db.query(QuestSession)
        .filter(QuestSession.id == quest_session.id)
        .with_for_update()
        .one()
    )
    if locked.state != "active" or locked.target_ms is None:
        quest_session.progress_ms = locked.progress_ms
        return locked

    interaction = db.get(SessionInteraction, locked.id)
    if interaction is not None and locked.interaction_version == 1:
        if locked.quest_id == "together":
            if interaction.phase != "timing" or interaction.timing_started_at is None:
                return locked
            intervals, progress_ms = evaluate_session(
                db, locked, not_before=interaction.timing_started_at
            )
            capped = min(progress_ms, locked.target_ms)
            locked.progress_ms = capped
            if capped >= locked.target_ms:
                completion_at = evidence.completion_instant(intervals, locked.target_ms)
                if completion_at is not None:
                    from app.services.interactions import create_pin_stage, now_utc, participant_ids

                    interaction.evidence_completed_at = completion_at
                    interaction.phase = "end_pin"
                    issued_at = now_utc()
                    interaction.phase_started_at = issued_at
                    create_pin_stage(db, locked.id, "end", participant_ids(db, locked.id), issued_at)
            db.flush()
            return locked

        # v2: heart_challenge was removed; no new heart sessions can exist.
        # Legacy heart rows keep serializing read-only and never re-evaluate.
        return locked

    intervals, progress_ms = evaluate_session(db, locked)
    capped = min(progress_ms, locked.target_ms)
    locked.progress_ms = capped

    if capped >= locked.target_ms:
        completion_at = evidence.completion_instant(intervals, locked.target_ms)
        locked.state = "completed"
        locked.completed_at = completion_at or datetime.now(timezone.utc)

        for participant in (
            db.query(SessionParticipant)
            .filter(SessionParticipant.session_id == locked.id)
            .all()
        ):
            award = QuestAward(
                session_id=locked.id, user_id=participant.user_id,
                points=AWARD_POINTS, xp=AWARD_XP,
            )
            db.add(award)
            user = (
                db.query(User)
                .filter(User.id == participant.user_id)
                .with_for_update()
                .one()
            )
            user.points_balance += AWARD_POINTS
            user.lifetime_xp += AWARD_XP
            db.add(
                PointTransaction(
                    user_id=user.id,
                    kind="quest_award",
                    delta=AWARD_POINTS,
                    xp_delta=AWARD_XP,
                    balance_after=user.points_balance,
                    session_id=locked.id,
                )
            )

    db.flush()
    return locked


def latest_valid_gps(db: Session, device_id: uuid.UUID) -> TelemetryRecord | None:
    return (
        db.query(TelemetryRecord)
        .filter(
            TelemetryRecord.device_id == device_id,
            TelemetryRecord.gps_valid.is_(True),
            TelemetryRecord.captured_at.isnot(None),
        )
        .order_by(TelemetryRecord.captured_at.desc())
        .first()
    )


def completion_event_id(session_id: uuid.UUID) -> str:
    """Stable completion ID derived from the awarded session."""
    return f"completion:{session_id}"
