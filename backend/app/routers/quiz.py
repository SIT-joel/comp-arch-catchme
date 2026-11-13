"""'Know Your Partner' quiz endpoints (v2).

The phone drives the surface: it fetches the questions (no correct index),
shows them, relays the wearable's A-D presses as answers, and the server
completes the session when every question is answered. Score display comes
from the recorded answers; the award is the shared exactly-once session
award.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import QuestSession, SessionParticipant, User
from app.schemas import QuizAnswerIn, QuizStateOut
from app.services import quiz as quiz_service

router = APIRouter(prefix="/api/v1", tags=["quiz"])


def _active_session_or_404(db: Session, session_id: uuid.UUID, user: User) -> QuestSession:
    quest_session = db.get(QuestSession, session_id)
    if quest_session is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No such session."})
    participant = (
        db.query(SessionParticipant)
        .filter(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user.id,
        )
        .one_or_none()
    )
    if participant is None:
        raise HTTPException(
            status_code=403, detail={"code": "not_participant", "message": "Not your session."}
        )
    return quest_session


@router.get("/sessions/{session_id}/quiz", response_model=QuizStateOut)
def get_quiz(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quest_session = _active_session_or_404(db, session_id, user)
    return QuizStateOut(**quiz_service.quiz_state(db, quest_session, user.id))


@router.post("/sessions/{session_id}/quiz/answer", response_model=QuizStateOut)
def post_quiz_answer(
    session_id: uuid.UUID,
    body: QuizAnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.choice < 0 or body.choice > 3 or body.question_index < 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "quiz_answer_invalid", "message": "choice must be 0-3, index >= 0."},
        )
    quest_session = _active_session_or_404(db, session_id, user)
    quiz_service.record_answer(db, quest_session, user.id, body.question_index, body.choice)
    db.commit()  # get_db never commits; the award + answers persist here
    return QuizStateOut(**quiz_service.quiz_state(db, quest_session, user.id))
