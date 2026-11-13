"""Version 1 quest interaction state machines and participant-safe snapshots."""

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Device,
    PointTransaction,
    QuestAward,
    QuestSession,
    SessionInteraction,
    SessionInteractionCommand,
    SessionParticipant,
    SessionPin,
    SessionPinHistory,
    TelemetryRecord,
    User,
)

PIN_TTL = timedelta(minutes=5)
PIN_MAX_ATTEMPTS = 5

# v2: heart_challenge was removed; this read-only catalog exists only so
# legacy heart-session snapshots keep resolving prompt text.
_LEGACY_PROMPTS = {
    "truth": [
        ("movie_like", "Have you ever pretended to like a movie?"),
        ("food_combo", "What is your most unusual food combination?"),
        ("new_hobby", "What hobby would you like to try?"),
    ],
    "dare": [
        ("compliment", "Give your partner a sincere compliment."),
        ("pickup_line", "Say your best cheesy pickup line."),
        ("dream_date", "Describe your dream date in three words."),
    ],
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def phase_anchor(db: Session, quest_session: QuestSession, lower_bound: datetime | None = None) -> datetime:
    """Start after the latest accepted sample so phase changes cannot reuse it."""
    latest = (
        db.query(TelemetryRecord.captured_at)
        .filter(
            TelemetryRecord.session_id == quest_session.id,
            TelemetryRecord.captured_at.isnot(None),
        )
        .order_by(TelemetryRecord.captured_at.desc())
        .first()
    )
    candidates = [now_utc()]
    if lower_bound is not None:
        candidates.append(lower_bound)
    if latest and latest[0] is not None:
        # Strictly move beyond the last persisted sample. A point at the exact
        # boundary may already have contributed to the phase being closed.
        candidates.append(latest[0] + timedelta(milliseconds=1))
    return max(candidates)


def _problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def participant_ids(db: Session, session_id: uuid.UUID) -> list[uuid.UUID]:
    return [
        row.user_id
        for row in db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session_id)
        .order_by(SessionParticipant.user_id)
        .all()
    ]


def partner_id_for(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    ids = participant_ids(db, session_id)
    if user_id not in ids or len(ids) != 2:
        raise _problem(403, "forbidden", "Only session participants may use this interaction.")
    return next(other for other in ids if other != user_id)


def _current_stage(interaction: SessionInteraction) -> str | None:
    if interaction.phase == "start_pin":
        return "start"
    if interaction.phase == "end_pin":
        return "end"
    return None


def _issue_code(db: Session, session_id: uuid.UUID, created_at: datetime) -> str:
    used = {
        row.display_code
        for row in db.query(SessionPinHistory.display_code)
        .filter(SessionPinHistory.session_id == session_id)
        .all()
    }
    # There are only 10,000 possible codes. A session uses four plus occasional
    # replacements; the bounded loop fails closed rather than reusing a code.
    for _ in range(10_000):
        code = f"{secrets.randbelow(10_000):04d}"
        if code not in used:
            db.add(SessionPinHistory(session_id=session_id, display_code=code, created_at=created_at))
            db.flush()  # a second code issued in this transaction must see this one
            return code
    raise _problem(503, "pin_pool_exhausted", "Could not issue a new code. Please retry.")


def create_pin_stage(db: Session, session_id: uuid.UUID, stage: str, users: list[uuid.UUID], at: datetime) -> None:
    for user_id in users:
        code = _issue_code(db, session_id, at)
        db.add(
            SessionPin(
                session_id=session_id,
                stage=stage,
                owner_user_id=user_id,
                code_version=1,
                display_code=code,
                failed_attempts=0,
                confirmed_at=None,
                expires_at=at + PIN_TTL,
                updated_at=at,
            )
        )


def initialize_interaction(db: Session, quest_session: QuestSession, at: datetime | None = None) -> None:
    """Freeze v1 for a newly accepted session; historical sessions remain NULL.

    v2: only together uses the interaction machine. Raid sessions stay on the
    outcome-command path; heart_challenge is removed entirely."""
    at = at or now_utc()
    users = participant_ids(db, quest_session.id)
    if len(users) != 2:
        raise _problem(409, "invalid_participants", "A shared quest requires exactly two participants.")

    if quest_session.quest_id != "together":
        return

    quest_session.interaction_version = 1
    db.add(
        SessionInteraction(
            session_id=quest_session.id,
            version=1,
            phase="start_pin",
            phase_started_at=None,
            timing_started_at=None,
            completed_evidence_ms=0,
            round_index=0,
            active_user_id=None,
            results={},
        )
    )
    create_pin_stage(db, quest_session.id, "start", users, at)


def interaction_for_update(db: Session, session_id: uuid.UUID) -> SessionInteraction:
    row = (
        db.query(SessionInteraction)
        .filter(SessionInteraction.session_id == session_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise _problem(409, "interaction_unavailable", "This session uses the legacy quest flow.")
    return row


def snapshot(db: Session, quest_session: QuestSession, user_id: uuid.UUID) -> dict | None:
    interaction = db.get(SessionInteraction, quest_session.id)
    if interaction is None:
        return None
    partner = partner_id_for(db, quest_session.id, user_id)
    stage = _current_stage(interaction)
    own = partner_pin = None
    if stage is not None:
        own = db.get(SessionPin, (quest_session.id, stage, user_id))
        partner_pin = db.get(SessionPin, (quest_session.id, stage, partner))

    prompt = None
    if interaction.prompt_kind and interaction.prompt_id:
        prompt = next(
            (text for key, text in _LEGACY_PROMPTS.get(interaction.prompt_kind, []) if key == interaction.prompt_id),
            None,
        )
    results = dict(interaction.results or {})
    baseline = results.get("baseline", {})
    deltas = {}
    for round_result in results.get("rounds", {}).values():
        for uid, bpm in round_result.items():
            if uid in baseline:
                deltas.setdefault(uid, []).append(int(bpm) - int(baseline[uid]))
    if deltas:
        results["bpm_changes"] = deltas

    return {
        "session_id": quest_session.id,
        "quest_id": quest_session.quest_id,
        "version": interaction.version,
        "phase": interaction.phase,
        "phase_started_at": interaction.phase_started_at,
        "timing_started_at": interaction.timing_started_at,
        "progress_ms": quest_session.progress_ms,
        "target_ms": quest_session.target_ms or 0,
        "completed_evidence_ms": interaction.completed_evidence_ms,
        "stage": stage,
        "own_code": own.display_code if own else None,
        "own_code_version": own.code_version if own else None,
        "own_code_expires_at": own.expires_at if own else None,
        "own_code_confirmed_by_partner": bool(own and own.confirmed_at),
        "partner_code_version": partner_pin.code_version if partner_pin else None,
        "partner_code_expires_at": partner_pin.expires_at if partner_pin else None,
        "partner_code_confirmed_by_me": bool(partner_pin and partner_pin.confirmed_at),
        "round_index": interaction.round_index,
        "active_user_id": interaction.active_user_id,
        "prompt_kind": interaction.prompt_kind,
        "prompt_id": interaction.prompt_id,
        "prompt": prompt,
        "results": results,
    }


def command_start(
    db: Session,
    quest_session: QuestSession,
    user_id: uuid.UUID,
    command_id: uuid.UUID,
    body: dict,
) -> tuple[SessionInteractionCommand | None, bool]:
    """Return (existing row, replay); raise on key reuse with other content."""
    serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
    secret = (quest_session.session_token or str(quest_session.id)).encode("utf-8")
    digest = hmac.new(secret, serialized.encode("utf-8"), hashlib.sha256).hexdigest()
    existing = db.get(SessionInteractionCommand, (quest_session.id, user_id, command_id))
    if existing:
        if existing.request_hash != digest:
            raise _problem(409, "command_id_reused", "This command ID was already used for a different request.")
        if existing.result_code:
            raise _problem(409, existing.result_code, existing.result_message or "The command was rejected.")
        return existing, True
    return (
        SessionInteractionCommand(
            session_id=quest_session.id,
            user_id=user_id,
            command_id=command_id,
            request_hash=digest,
            created_at=now_utc(),
        ),
        False,
    )


def mark_command_error(command: SessionInteractionCommand, code: str, message: str) -> None:
    command.result_code = code
    command.result_message = message[:160]


def _pin_error(
    db: Session,
    command: SessionInteractionCommand,
    status: int,
    code: str,
    message: str,
) -> None:
    mark_command_error(command, code, message)
    db.add(command)
    db.commit()  # failed PIN attempts are state and must persist
    raise _problem(status, code, message)


def submit_pin(
    db: Session,
    quest_session: QuestSession,
    user_id: uuid.UUID,
    stage: str,
    pin: str,
    code_version: int,
    command_id: uuid.UUID,
) -> bool:
    command, replay = command_start(
        db, quest_session, user_id, command_id,
        {"kind": "pin_submit", "stage": stage, "pin": pin, "code_version": code_version},
    )
    if replay:
        return False
    interaction = interaction_for_update(db, quest_session.id)
    if quest_session.state != "active" or _current_stage(interaction) != stage:
        raise _problem(409, "wrong_pin_stage", "That PIN stage is not active.")
    partner = partner_id_for(db, quest_session.id, user_id)
    target = (
        db.query(SessionPin)
        .filter(
            SessionPin.session_id == quest_session.id,
            SessionPin.stage == stage,
            SessionPin.owner_user_id == partner,
        )
        .with_for_update()
        .one_or_none()
    )
    if target is None:
        raise _problem(409, "pin_missing", "Ask your partner to refresh their code.")
    at = now_utc()
    if target.code_version != code_version or target.expires_at <= at:
        _pin_error(db, command, 409, "pin_expired", "That code expired or changed. Ask your partner to refresh it.")
    if target.confirmed_at is not None:
        db.add(command)
        return False  # accepted retry after the same code was confirmed
    if target.failed_attempts >= PIN_MAX_ATTEMPTS:
        _pin_error(db, command, 429, "pin_attempt_limit", "Ask your partner to refresh their code.")
    if not secrets.compare_digest(target.display_code, pin):
        target.failed_attempts += 1
        _pin_error(db, command, 422, "pin_incorrect", "That code did not match. Check with your partner and try again.")

    target.confirmed_at = at
    db.add(command)
    db.flush()
    pins = (
        db.query(SessionPin)
        .filter(SessionPin.session_id == quest_session.id, SessionPin.stage == stage)
        .all()
    )
    if len(pins) == 2 and all(p.confirmed_at is not None and p.expires_at > at for p in pins):
        if stage == "start":
            interaction.phase = "timing"
            anchor = phase_anchor(db, quest_session, at)
            interaction.timing_started_at = anchor
            interaction.phase_started_at = anchor
            db.query(SessionPin).filter(
                SessionPin.session_id == quest_session.id,
                SessionPin.stage == "start",
            ).delete(synchronize_session=False)
            # Keep issued values until completion to guarantee start/end codes differ.
        else:
            interaction.phase = "summary"
            interaction.phase_started_at = at
            complete_and_award(db, quest_session, at)
    return True


def refresh_pin(
    db: Session,
    quest_session: QuestSession,
    user_id: uuid.UUID,
    stage: str,
    command_id: uuid.UUID,
) -> bool:
    command, replay = command_start(
        db, quest_session, user_id, command_id, {"kind": "pin_refresh", "stage": stage}
    )
    if replay:
        return False
    interaction = interaction_for_update(db, quest_session.id)
    if quest_session.state != "active" or _current_stage(interaction) != stage:
        raise _problem(409, "wrong_pin_stage", "That PIN stage is not active.")
    own = (
        db.query(SessionPin)
        .filter(
            SessionPin.session_id == quest_session.id,
            SessionPin.stage == stage,
            SessionPin.owner_user_id == user_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if own is None:
        raise _problem(409, "pin_missing", "This PIN stage is no longer available.")
    at = now_utc()
    own.display_code = _issue_code(db, quest_session.id, at)
    own.code_version += 1
    own.failed_attempts = 0
    own.confirmed_at = None
    own.expires_at = at + PIN_TTL
    own.updated_at = at
    db.add(command)
    return True


def complete_and_award(db: Session, quest_session: QuestSession, at: datetime) -> QuestSession:
    """Complete once and award both users within the caller's transaction."""
    locked = (
        db.query(QuestSession)
        .filter(QuestSession.id == quest_session.id)
        .with_for_update()
        .one()
    )
    if locked.state == "completed":
        return locked
    if locked.state != "active":
        raise _problem(409, "session_not_active", "This quest is no longer active.")
    locked.state = "completed"
    locked.completed_at = at
    for participant in (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == locked.id)
        .all()
    ):
        exists = (
            db.query(QuestAward)
            .filter(QuestAward.session_id == locked.id, QuestAward.user_id == participant.user_id)
            .one_or_none()
        )
        if exists:
            continue
        award = QuestAward(session_id=locked.id, user_id=participant.user_id, points=100, xp=100)
        db.add(award)
        account = (
            db.query(User)
            .filter(User.id == participant.user_id)
            .with_for_update()
            .one()
        )
        account.points_balance += 100
        account.lifetime_xp += 100
        db.add(
            PointTransaction(
                user_id=account.id,
                kind="quest_award",
                delta=100,
                xp_delta=100,
                balance_after=account.points_balance,
                session_id=locked.id,
            )
        )
    db.query(SessionPin).filter(SessionPin.session_id == locked.id).delete(synchronize_session=False)
    db.query(SessionPinHistory).filter(SessionPinHistory.session_id == locked.id).delete(synchronize_session=False)
    db.flush()
    return locked


def clear_unfinished_interaction(db: Session, session_id: uuid.UUID) -> None:
    """Drop PINs and command payload identity for a cancelled unfinished flow."""
    db.query(SessionPin).filter(SessionPin.session_id == session_id).delete(synchronize_session=False)
    db.query(SessionPinHistory).filter(SessionPinHistory.session_id == session_id).delete(synchronize_session=False)
    db.query(SessionInteractionCommand).filter(
        SessionInteractionCommand.session_id == session_id
    ).delete(synchronize_session=False)
    db.query(SessionInteraction).filter(
        SessionInteraction.session_id == session_id,
        SessionInteraction.phase != "summary",
    ).delete(synchronize_session=False)


