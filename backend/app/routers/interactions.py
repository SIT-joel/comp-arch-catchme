"""Participant-authenticated quest PIN interaction endpoints (v2: together only)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.events import bump_state_version, publish_state_event
from app.models import QuestSession, SessionParticipant, User
from app.schemas import InteractionSnapshot, PinRefreshIn, PinSubmitIn
from app.services.interactions import refresh_pin, snapshot, submit_pin

router = APIRouter(prefix="/api/v1/sessions", tags=["session interactions"])


def _load_participant(db: Session, session_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False) -> QuestSession:
    query = db.query(QuestSession).filter(QuestSession.id == session_id)
    if lock:
        query = query.with_for_update()
    quest_session = query.one_or_none()
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})
    participant = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session_id, SessionParticipant.user_id == user_id)
        .one_or_none()
    )
    if participant is None:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Only participants may use this interaction."})
    return quest_session


def _snapshot(db: Session, quest_session: QuestSession, user_id: uuid.UUID) -> InteractionSnapshot:
    data = snapshot(db, quest_session, user_id)
    if data is None:
        raise HTTPException(status_code=409, detail={"code": "interaction_unavailable", "message": "This session uses the legacy quest flow."})
    return InteractionSnapshot(**data)


def _finish_command(
    db: Session,
    quest_session: QuestSession,
    user_id: uuid.UUID,
    changed: bool,
    kind: str = "interaction",
) -> None:
    if not changed:
        db.commit()
        return
    version = bump_state_version(db)
    db.commit()
    participants = [
        row.user_id
        for row in db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == quest_session.id)
        .all()
    ]
    publish_state_event(participants or [user_id], version, session_id=quest_session.id, kind=kind)


@router.get("/{session_id}/interaction", response_model=InteractionSnapshot)
def get_interaction(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quest_session = _load_participant(db, session_id, user.id)
    return _snapshot(db, quest_session, user.id)


@router.post("/{session_id}/interaction/pin/submit", response_model=InteractionSnapshot)
def post_pin(
    session_id: uuid.UUID,
    body: PinSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quest_session = _load_participant(db, session_id, user.id, lock=True)
    changed = submit_pin(db, quest_session, user.id, body.stage, body.pin, body.code_version, body.command_id)
    if quest_session.state == "completed":
        _finish_command(db, quest_session, user.id, changed, "session_completed")
    else:
        _finish_command(db, quest_session, user.id, changed)
    return _snapshot(db, quest_session, user.id)


@router.post("/{session_id}/interaction/pin/refresh", response_model=InteractionSnapshot)
def post_pin_refresh(
    session_id: uuid.UUID,
    body: PinRefreshIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quest_session = _load_participant(db, session_id, user.id, lock=True)
    changed = refresh_pin(db, quest_session, user.id, body.stage, body.command_id)
    _finish_command(db, quest_session, user.id, changed)
    return _snapshot(db, quest_session, user.id)
