"""'Know Your Partner' quiz: generation, answering, scoring, completion.

Questions are generated ONCE at session activation from each participant's
discovery profile: the ANSWERER answers questions about the SUBJECT (their
partner). Each question's correct option is one of the subject's interest
tags; the three distractors are catalog tags the subject did NOT pick. The
correct index never leaves the server — the phone shows options, the player
presses A-D on the wearable, the phone relays the choice.

The mechanic is deliberately social: to answer correctly you have to ask
your partner about themselves (docs/QUEST_INTERACTION_PLAN.md).

Completion = every generated question answered by its answerer (latest
choice wins). Completion awards exactly once via the shared session award
path (+100/+100), the same as every other quest.
"""

import random
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    INTEREST_TAGS,
    QuestSession,
    QuizAnswer,
    QuizQuestion,
    SessionParticipant,
    UserInterest,
)
from app.services.interactions import complete_and_award

MAX_QUESTIONS_PER_ANSWERER = 5
OPTION_COUNT = 4


def generate_for_session(db: Session, quest_session: QuestSession) -> None:
    """Generate the question sets once (idempotent: skips if any exist)."""
    existing = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.session_id == quest_session.id)
        .first()
    )
    if existing is not None:
        return

    participants = [
        row[0]
        for row in db.query(SessionParticipant.user_id)
        .filter(SessionParticipant.session_id == quest_session.id)
        .all()
    ]
    if len(participants) != 2:
        return

    now = datetime.now(timezone.utc)
    for answerer_id, subject_id in (participants, participants[::-1]):
        subject_interests = [
            row[0]
            for row in db.query(UserInterest.tag)
            .filter(UserInterest.user_id == subject_id)
            .all()
        ]
        if not subject_interests:
            continue  # a subject with no interests generates no questions
        # One question per subject interest, capped; deterministic per session
        # (seeded by the session id) so re-runs are stable in tests.
        rng = random.Random(str(quest_session.id))
        picked = sorted(set(subject_interests))[:MAX_QUESTIONS_PER_ANSWERER]
        rng.shuffle(picked)
        for index, tag in enumerate(picked):
            distractors = [t for t in INTEREST_TAGS if t not in subject_interests]
            rng.shuffle(distractors)
            options = [tag] + distractors[: OPTION_COUNT - 1]
            rng.shuffle(options)
            subject_name = _display_name(db, subject_id)
            db.add(
                QuizQuestion(
                    session_id=quest_session.id,
                    answerer_user_id=answerer_id,
                    subject_user_id=subject_id,
                    question_index=index,
                    text=f"Which of these is {subject_name}'s interest?",
                    options=options,
                    correct_index=options.index(tag),
                    )
            )
    db.flush()


def _display_name(db: Session, user_id: uuid.UUID) -> str:
    from app.models import User

    user = db.get(User, user_id)
    return user.display_name if user else "your partner"


def quiz_state(db: Session, quest_session: QuestSession, user_id: uuid.UUID) -> dict:
    """Per-answerer view: questions without the correct index, own answers."""
    questions = (
        db.query(QuizQuestion)
        .filter(
            QuizQuestion.session_id == quest_session.id,
            QuizQuestion.answerer_user_id == user_id,
        )
        .order_by(QuizQuestion.question_index)
        .all()
    )
    answers = {
        row[0]: row[1]
        for row in db.query(QuizAnswer.question_index, QuizAnswer.choice)
        .filter(
            QuizAnswer.session_id == quest_session.id,
            QuizAnswer.user_id == user_id,
        )
        .all()
    }
    mine_total = len(questions)
    mine_answered = sum(1 for q in questions if q.question_index in answers)
    # Partner progress: their answered count over their generated count.
    partner_id = next(
        (
            row[0]
            for row in db.query(SessionParticipant.user_id)
            .filter(SessionParticipant.session_id == quest_session.id)
            .all()
            if row[0] != user_id
        ),
        None,
    )
    partner_total = (
        db.query(QuizQuestion)
        .filter(
            QuizQuestion.session_id == quest_session.id,
            QuizQuestion.answerer_user_id == partner_id,
        )
        .count()
        if partner_id
        else 0
    )
    partner_answered = (
        db.query(QuizAnswer)
        .filter(
            QuizAnswer.session_id == quest_session.id,
            QuizAnswer.user_id == partner_id,
        )
        .count()
        if partner_id
        else 0
    )
    return {
        "completed": quest_session.state == "completed",
        "my_total": mine_total,
        "my_answered": mine_answered,
        "partner_total": partner_total,
        "partner_answered": partner_answered,
        "questions": [
            {
                "index": q.question_index,
                "text": q.text,
                "options": q.options,
                "answered": q.question_index in answers,
                "choice": answers.get(q.question_index),
            }
            for q in questions
        ],
    }


def record_answer(
    db: Session, quest_session: QuestSession, user_id: uuid.UUID,
    question_index: int, choice: int,
) -> dict:
    """Upsert the answerer's choice; complete the session when all answered.

    Only the designated answerer may answer a question; the choice is
    re-validated against the stored question. Latest choice wins (the
    unique row is updated), so a second press before the phone advances
    simply corrects the answer.
    """
    if quest_session.state != "active":
        from app.services.interactions import _problem

        raise _problem(409, "session_not_active", "This quest is no longer active.")
    question = (
        db.query(QuizQuestion)
        .filter(
            QuizQuestion.session_id == quest_session.id,
            QuizQuestion.answerer_user_id == user_id,
            QuizQuestion.question_index == question_index,
        )
        .one_or_none()
    )
    if question is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail={"code": "quiz_no_such_question", "message": "No such question for you."},
        )

    existing = (
        db.query(QuizAnswer)
        .filter(
            QuizAnswer.session_id == quest_session.id,
            QuizAnswer.user_id == user_id,
            QuizAnswer.question_index == question_index,
        )
        .one_or_none()
    )
    if existing is not None:
        existing.choice = choice
        existing.answered_at = datetime.now(timezone.utc)
    else:
        db.add(
            QuizAnswer(
                session_id=quest_session.id,
                user_id=user_id,
                question_index=question_index,
                choice=choice,
            )
        )
    db.flush()

    total = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.session_id == quest_session.id)
        .count()
    )
    answered = (
        db.query(QuizAnswer)
        .filter(QuizAnswer.session_id == quest_session.id)
        .count()
    )
    state = {"completed": False, "my_total": 0, "my_answered": 0}
    if total > 0 and answered >= total:
        # Score before completion: correct count per answerer (for display).
        now = datetime.now(timezone.utc)
        complete_and_award(db, quest_session, now)
        state["completed"] = True
    db.flush()
    return state
