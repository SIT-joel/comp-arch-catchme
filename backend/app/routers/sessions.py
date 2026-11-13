"""Quest session lifecycle: create, accept, cancel, read."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, get_pair_partner
from app.events import bump_state_version, get_state_version, publish_state_event
from app.models import QuestSession, SessionParticipant, User
from app.schemas import (
    ParticipantOut,
    RaidOutcomeIn,
    SessionCreateIn,
    SessionOut,
    SessionsOut,
)
from app.security import new_session_token

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _pair_users(db: Session, user_id) -> tuple:
    _, partner_id = get_pair_partner(db, user_id)
    if partner_id is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "not_paired", "message": "No paired partner account is configured."},
        )
    return user_id, partner_id


def _non_terminal_session(db: Session, user_a, user_b) -> QuestSession | None:
    return (
        db.query(QuestSession)
        .join(SessionParticipant, SessionParticipant.session_id == QuestSession.id)
        .filter(
            SessionParticipant.user_id.in_((user_a, user_b)),
            QuestSession.state.in_(("pending", "active")),
        )
        .first()
    )


def serialize(db: Session, quest_session: QuestSession, for_user: uuid.UUID) -> SessionOut:
    participants = (
        db.query(SessionParticipant, User)
        .join(User, User.id == SessionParticipant.user_id)
        .filter(SessionParticipant.session_id == quest_session.id)
        .all()
    )
    is_participant = any(row.SessionParticipant.user_id == for_user for row in participants)
    now = datetime.now(timezone.utc)
    expired = False
    if quest_session.state == "pending":
        created = quest_session.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        expired = (now - created).total_seconds() > 300  # invitation expires after 5 min
        if expired and quest_session.state == "pending":
            quest_session.state = "cancelled"
            quest_session.cancelled_at = now
            db.commit()

    geofence = None
    if quest_session.quest_id == "explore" and quest_session.geofence_lat is not None:
        geofence = {
            "latitude": quest_session.geofence_lat,
            "longitude": quest_session.geofence_lon,
            "radius_m": quest_session.geofence_radius_m,
        }

    landmark = None
    if quest_session.quest_id == "raid" and quest_session.landmark_id:
        from app.models import Landmark

        row = db.get(Landmark, quest_session.landmark_id)
        if row is not None:
            landmark = {
                "id": row.id,
                "name": row.name,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "radius_m": row.radius_m,
            }

    raid_outcome = None
    if quest_session.quest_id == "raid" and is_participant:
        from app.models import RaidOutcome

        mine = (
            db.query(RaidOutcome)
            .filter(RaidOutcome.session_id == quest_session.id, RaidOutcome.user_id == for_user)
            .one_or_none()
        )
        raid_outcome = mine.outcome if mine else None

    return SessionOut(
        id=quest_session.id,
        quest_id=quest_session.quest_id,
        demo=quest_session.demo,
        state=quest_session.state,
        created_by=quest_session.created_by,
        created_at=quest_session.created_at,
        activated_at=quest_session.activated_at,
        completed_at=quest_session.completed_at,
        cancelled_at=quest_session.cancelled_at,
        target_ms=quest_session.target_ms,
        progress_ms=quest_session.progress_ms,
        participants=[
            ParticipantOut(
                user_id=row.SessionParticipant.user_id,
                display_name=row.User.display_name,
                accepted=row.SessionParticipant.accepted_at is not None,
            )
            for row in participants
        ],
        token=quest_session.session_token if is_participant and quest_session.state == "active" else None,
        geofence=geofence,
        landmark=landmark,
        raid_outcome=raid_outcome,
    )


def _raid_gate_or_409(db: Session, quest_session: QuestSession) -> None:
    """v2 raid activation gate: both participants need a fresh phone-GPS fix
    inside the landmark radius at accept time. Evaluated on fix time
    (captured_at - fix_age_ms); never clamped."""
    from app.models import Device, Landmark
    from app.services.evidence import haversine_m
    from app.services.evaluation import latest_valid_gps

    settings = get_settings()
    landmark = db.get(Landmark, quest_session.landmark_id)
    now = datetime.now(timezone.utc)
    participants = (
        db.query(SessionParticipant.user_id)
        .filter(SessionParticipant.session_id == quest_session.id)
        .all()
    )
    for (user_id,) in participants:
        device = (
            db.query(Device)
            .filter(Device.owner_user_id == user_id)
            .one_or_none()
        )
        record = latest_valid_gps(db, device.id) if device else None
        if record is None or record.captured_at is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "raid_gate_location",
                    "message": "Both players need a phone GPS fix near the landmark to start the raid.",
                },
            )
        fix_age_ms = record.gps_fix_age_ms or 0
        fix_time = record.captured_at - timedelta(milliseconds=fix_age_ms)
        age_ms = (now - fix_time).total_seconds() * 1000.0
        if age_ms > settings.raid_fix_max_age_ms:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "raid_gate_location",
                    "message": "A player's GPS fix is too old to start the raid (30 s limit).",
                },
            )
        distance = haversine_m(record.gps_lat, record.gps_lon, landmark.latitude, landmark.longitude)
        if distance > settings.raid_radius_m:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "raid_gate_location",
                    "message": f"A player is {int(distance)} m from the landmark (50 m limit).",
                },
            )


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    user_id, partner_id = _pair_users(db, user.id)

    quest = settings.quest_config(body.quest_id)
    if quest is None:
        raise HTTPException(status_code=422, detail={"code": "invalid_quest", "message": "Unknown quest id."})

    if body.quest_id == "explore" and not settings.geofence_configured():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "geofence_not_configured",
                "message": "Explore requires a configured demo geofence (CM_GEOFENCE_LAT/LON).",
            },
        )

    landmark = None
    if body.quest_id == "raid":
        if not body.landmark_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "landmark_required", "message": "A raid session requires a landmark_id."},
            )
        from app.models import Landmark

        landmark = db.get(Landmark, body.landmark_id)
        if landmark is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "landmark_not_found", "message": "No such landmark."},
            )
    elif body.landmark_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "landmark_only_for_raid", "message": "landmark_id applies only to raid sessions."},
        )

    existing = _non_terminal_session(db, user_id, partner_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "session_in_progress",
                "message": "A pending or active quest already exists for this pair.",
            },
        )

    quest_session = QuestSession(
        quest_id=body.quest_id,
        demo=body.demo,
        state="pending",
        created_by=user.id,
        landmark_id=landmark.id if landmark else None,
    )
    db.add(quest_session)
    db.flush()
    db.add(SessionParticipant(session_id=quest_session.id, user_id=user.id, accepted_at=datetime.now(timezone.utc)))
    db.add(SessionParticipant(session_id=quest_session.id, user_id=partner_id, accepted_at=None))

    version = bump_state_version(db)
    db.commit()
    publish_state_event([user_id, partner_id], version, session_id=quest_session.id, kind="session_created")
    return serialize(db, quest_session, user.id)


@router.post("/{session_id}/accept", response_model=SessionOut)
def accept_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    user_id, partner_id = _pair_users(db, user.id)
    quest_session = db.get(QuestSession, session_id)
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})

    participants = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session_id)
        .all()
    )
    if not any(p.user_id == user_id for p in participants):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Only paired participants may accept."},
        )

    if quest_session.state == "pending":
        me = next(p for p in participants if p.user_id == user_id)
        if me.accepted_at is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "already_accepted", "message": "You already accepted this session."},
            )
        me.accepted_at = datetime.now(timezone.utc)

        if all(p.accepted_at is not None for p in participants):
            quest_session.state = "active"
            quest_session.activated_at = datetime.now(timezone.utc)
            quest = settings.quest_config(quest_session.quest_id)
            quest_session.target_ms = (
                quest["demo_duration_ms"] if quest_session.demo else quest["normal_duration_ms"]
            )
            quest_session.session_token = new_session_token()
            if quest_session.quest_id == "together":
                from app.services.interactions import initialize_interaction

                initialize_interaction(db, quest_session, quest_session.activated_at)
            if quest_session.quest_id == "explore":
                quest_session.geofence_lat = settings.geofence_lat
                quest_session.geofence_lon = settings.geofence_lon
                quest_session.geofence_radius_m = settings.geofence_radius_m
            if quest_session.quest_id == "raid":
                _raid_gate_or_409(db, quest_session)
            if quest_session.quest_id == "quiz":
                from app.services.quiz import generate_for_session

                generate_for_session(db, quest_session)
            kind = "session_active"
        else:
            kind = "session_accepted"
        version = bump_state_version(db)
        db.commit()
        publish_state_event([user_id, partner_id], version, session_id=quest_session.id, kind=kind)
    elif quest_session.state in ("active", "completed"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_transition",
                "message": f"Cannot accept a session in state '{quest_session.state}'.",
            },
        )

    return serialize(db, quest_session, user.id)


@router.post("/{session_id}/cancel", response_model=SessionOut)
def cancel_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id, partner_id = _pair_users(db, user.id)
    quest_session = (
        db.query(QuestSession)
        .filter(QuestSession.id == session_id)
        .with_for_update()
        .one_or_none()
    )
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})

    is_participant = (
        db.query(SessionParticipant)
        .filter(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
        .one_or_none()
    )
    if is_participant is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Only participants may cancel."},
        )

    if quest_session.state == "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_transition",
                "message": "Completed sessions are immutable; cancellation is not allowed.",
            },
        )
    if quest_session.state == "cancelled":
        raise HTTPException(
            status_code=409,
            detail={"code": "already_cancelled", "message": "Session is already cancelled."},
        )

    quest_session.state = "cancelled"
    quest_session.cancelled_at = datetime.now(timezone.utc)
    from app.services.interactions import clear_unfinished_interaction

    clear_unfinished_interaction(db, quest_session.id)
    version = bump_state_version(db)
    db.commit()
    publish_state_event([user_id, partner_id], version, session_id=quest_session.id, kind="session_cancelled")
    return serialize(db, quest_session, user.id)


@router.post("/{session_id}/raid/outcome", response_model=SessionOut)
def post_raid_outcome(
    session_id: uuid.UUID,
    body: RaidOutcomeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One board's verified fight report. Completion requires BOTH
    participants' reports; awards require both to report 'win' (a lost raid
    completes honestly with no award). Idempotent per command id and one
    report per reporter."""
    user_id, partner_id = _pair_users(db, user.id)
    quest_session = (
        db.query(QuestSession)
        .filter(QuestSession.id == session_id)
        .with_for_update()
        .one_or_none()
    )
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})
    is_participant = (
        db.query(SessionParticipant)
        .filter(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
        .one_or_none()
    )
    if is_participant is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Only participants may report raid outcomes."},
        )
    if quest_session.quest_id != "raid" or quest_session.state != "active":
        raise HTTPException(
            status_code=409,
            detail={"code": "raid_not_active", "message": "Outcomes are only accepted for active raid sessions."},
        )

    from app.models import RaidOutcome

    # Idempotency mirrors the interaction-command pattern: same command id
    # replays the same result; a reused id with different content is rejected.
    from app.services.interactions import command_start, mark_command_error

    existing_report = (
        db.query(RaidOutcome)
        .filter(RaidOutcome.session_id == session_id, RaidOutcome.user_id == user_id)
        .one_or_none()
    )
    if existing_report is not None:
        if existing_report.command_id != body.command_id or existing_report.outcome != body.outcome:
            raise HTTPException(
                status_code=409,
                detail={"code": "raid_outcome_reported", "message": "This board already reported its outcome."},
            )
        db.commit()  # idempotent replay
        return serialize(db, quest_session, user.id)

    started = body.fight_started_at
    ended = body.fight_ended_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if ended <= started or started < (quest_session.activated_at or started) or ended > now + timedelta(seconds=5):
        command, _ = command_start(
            db, quest_session, user_id, body.command_id,
            {"kind": "raid_outcome", "outcome": body.outcome},
        )
        mark_command_error(command, "raid_outcome_invalid", "Fight times are inconsistent.")
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={"code": "raid_outcome_invalid", "message": "Fight times are inconsistent."},
        )

    command, replay = command_start(
        db, quest_session, user_id, body.command_id,
        {"kind": "raid_outcome", "outcome": body.outcome},
    )
    if replay:
        db.commit()
        return serialize(db, quest_session, user.id)
    db.add(command)
    db.add(
        RaidOutcome(
            session_id=session_id,
            user_id=user_id,
            command_id=body.command_id,
            outcome=body.outcome,
            fight_started_at=started,
            fight_ended_at=ended,
        )
    )
    db.flush()  # sessions use autoflush=False: make this report visible below

    reports = (
        db.query(RaidOutcome)
        .filter(RaidOutcome.session_id == session_id)
        .all()
    )
    if len(reports) < 2:
        version = bump_state_version(db)
        db.commit()
        publish_state_event([user_id, partner_id], version, session_id=session_id, kind="raid_reported")
        return serialize(db, quest_session, user.id)

    # Both reports in: complete. Award only a shared victory.
    # NOTE: complete_and_award early-returns on completed sessions, so the
    # award path must run BEFORE the state flip; it sets state itself.
    both_win = all(r.outcome == "win" for r in reports)
    completed_at = max(r.fight_ended_at for r in reports)
    if both_win:
        from app.services.interactions import complete_and_award

        complete_and_award(db, quest_session, completed_at)
    else:
        quest_session.state = "completed"
        quest_session.completed_at = completed_at
    version = bump_state_version(db)
    db.commit()
    publish_state_event([user_id, partner_id], version, session_id=session_id, kind="session_completed")
    return serialize(db, quest_session, user.id)


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id, partner_id = _pair_users(db, user.id)
    quest_session = db.get(QuestSession, session_id)
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})
    is_participant = (
        db.query(SessionParticipant)
        .filter(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
        .one_or_none()
    )
    if is_participant is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Only participants may view this session."},
        )
    return serialize(db, quest_session, user.id)


@router.get("/{session_id}/readings")
def session_readings(
    session_id: uuid.UUID,
    seconds: int = 120,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent heart-rate readings for the live web graph (both participants).

    Honesty rules: invalid readings are returned with valid=false and their
    status; the graph shows gaps instead of interpolating.
    """
    user_id, partner_id = _pair_users(db, user.id)
    quest_session = db.get(QuestSession, session_id)
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})
    is_participant = (
        db.query(SessionParticipant)
        .filter(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
        .one_or_none()
    )
    if is_participant is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Only participants may view this session."},
        )

    from datetime import timedelta

    from app.models import Device, TelemetryRecord

    seconds = max(1, min(seconds, 600))
    cutoff = None
    anchor = quest_session.completed_at or quest_session.cancelled_at
    if anchor is not None:
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        cutoff = anchor  # frozen sessions stop the live window at their end
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)

    owner_by_user = {
        d.owner_user_id: d.id for d in db.query(Device).filter(Device.owner_user_id.in_((user_id, partner_id))).all()
    }

    out = []
    for participant in (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session_id)
        .all()
    ):
        device_id = owner_by_user.get(participant.user_id)
        if device_id is None:
            continue
        rows = (
            db.query(TelemetryRecord)
            .filter(
                TelemetryRecord.device_id == device_id,
                TelemetryRecord.session_id == session_id,
                TelemetryRecord.captured_at.isnot(None),
                TelemetryRecord.captured_at >= cutoff - timedelta(seconds=seconds),
            )
            .order_by(TelemetryRecord.captured_at.asc())
            .limit(1200)
            .all()
        )
        for row in rows:
            captured = row.captured_at
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            out.append(
                {
                    "user_id": str(participant.user_id),
                    "is_self": participant.user_id == user_id,
                    "captured_at": captured.isoformat(),
                    "heart_rate": {
                        "valid": row.hr_valid,
                        "bpm": row.bpm,
                        "status": row.hr_status,
                    },
                    "gps": {"valid": row.gps_valid},
                    "peer": {"observed": row.peer_observed},
                }
            )
    out.sort(key=lambda r: r["captured_at"])
    return {"session_id": str(session_id), "readings": out}


@router.get("", response_model=SessionsOut)
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(QuestSession)
        .join(SessionParticipant, SessionParticipant.session_id == QuestSession.id)
        .filter(SessionParticipant.user_id == user.id)
        .order_by(QuestSession.created_at.desc())
        .limit(50)
        .all()
    )
    return SessionsOut(sessions=[serialize(db, s, user.id) for s in rows])
