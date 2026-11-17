"""Achievements (15 Nov): friend-journey milestones evaluated against data
the backend already stores — quests completed, quiz accuracy, care streaks,
levels, balances. The catalog lives here in code; unlocks are idempotent
rows in user_achievements (unique per user + achievement).

check_and_unlock(db, user) is called at the natural trigger points: quest
completion, pet care, and partnership acceptance. It returns the newly
unlocked catalog entries so callers can surface them.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    Pet,
    QuizAnswer,
    QuizQuestion,
    QuestSession,
    SessionParticipant,
    UserAchievement,
)


def catalog() -> list[dict]:
    """The achievement catalog: id, name, description — stable ids (the
    user_achievements rows reference them)."""
    return [
        {"id": "new_friend", "name": "New Friend",
         "description": "Form your first partnership."},
        {"id": "together_1", "name": "First Meeting",
         "description": "Complete your first Together session."},
        {"id": "together_3", "name": "Regulars",
         "description": "Complete three Together sessions."},
        {"id": "explorer_1", "name": "Explorer",
         "description": "Complete your first Outdoor Visit."},
        {"id": "quiz_1", "name": "Icebreaker",
         "description": "Complete your first Know-Your-Partner quiz."},
        {"id": "quiz_ace", "name": "Mind Reader",
         "description": "Answer every quiz question correctly in one quiz."},
        {"id": "care_streak_3", "name": "Caring Friend",
         "description": "Keep a 3-day pet care streak."},
        {"id": "level_5", "name": "Rising Star",
         "description": "Reach level 5."},
        {"id": "level_10", "name": "Social Legend",
         "description": "Reach level 10."},
        {"id": "points_200", "name": "Saver",
         "description": "Hold 200 points at once."},
    ]


def _completed_count(db: Session, user_id, quest_id: str) -> int:
    return (
        db.query(QuestSession)
        .join(SessionParticipant, SessionParticipant.session_id == QuestSession.id)
        .filter(
            SessionParticipant.user_id == user_id,
            QuestSession.quest_id == quest_id,
            QuestSession.state == "completed",
        )
        .count()
    )


def _condition_met(db: Session, user, achievement_id: str) -> bool:
    if achievement_id == "new_friend":
        # Any partnership row (active or ended) counts: forming the
        # partnership is the milestone.
        from app.models import PartnershipMember

        return (
            db.query(PartnershipMember)
            .filter(PartnershipMember.user_id == user.id)
            .first()
            is not None
        )
    if achievement_id == "together_1":
        return _completed_count(db, user.id, "together") >= 1
    if achievement_id == "together_3":
        return _completed_count(db, user.id, "together") >= 3
    if achievement_id == "explorer_1":
        return _completed_count(db, user.id, "explore") >= 1
    if achievement_id == "quiz_1":
        return _completed_count(db, user.id, "quiz") >= 1
    if achievement_id == "quiz_ace":
        # A completed quiz where every one of the user's answers matched the
        # generated correct index.
        rows = (
            db.query(QuizAnswer, QuizQuestion, QuestSession)
            .join(
                QuizQuestion,
                QuizQuestion.session_id == QuizAnswer.session_id,
            )
            .join(
                QuestSession,
                QuestSession.id == QuizAnswer.session_id,
            )
            .filter(
                QuizAnswer.user_id == user.id,
                QuizQuestion.answerer_user_id == user.id,
                QuizQuestion.question_index == QuizAnswer.question_index,
                QuestSession.state == "completed",
            )
            .all()
        )
        if not rows:
            return False
        sessions = {}
        for answer, question, _session in rows:
            sessions.setdefault(answer.session_id, []).append(
                answer.choice == question.correct_index
            )
        return any(all(v for v in marks) and len(marks) >= 1 for marks in sessions.values())
    if achievement_id == "care_streak_3":
        pet = db.get(Pet, user.id)
        return pet is not None and pet.care_streak >= 3
    if achievement_id == "level_5":
        return user.lifetime_xp >= 400
    if achievement_id == "level_10":
        return user.lifetime_xp >= 900
    if achievement_id == "points_200":
        return user.points_balance >= 200
    return False


def check_and_unlock(db: Session, user) -> list[dict]:
    """Evaluate every catalog condition for the user; insert idempotent
    rows for the newly met ones. Returns the newly unlocked catalog
    entries (callers surface them). Safe to call inside the caller's
    transaction; flushes the inserts."""
    existing = {
        row.achievement_id
        for row in db.query(UserAchievement)
        .filter(UserAchievement.user_id == user.id)
        .all()
    }
    newly: list[dict] = []
    for entry in catalog():
        if entry["id"] in existing:
            continue
        if not _condition_met(db, user, entry["id"]):
            continue
        db.add(
            UserAchievement(
                user_id=user.id,
                achievement_id=entry["id"],
                unlocked_at=datetime.now(timezone.utc),
            )
        )
        newly.append(entry)
    if newly:
        db.flush()
    return newly


def unlocked_map(db: Session, user) -> dict[str, datetime]:
    """The user's unlocked achievement id -> timestamp (for serialization)."""
    rows = (
        db.query(UserAchievement)
        .filter(UserAchievement.user_id == user.id)
        .all()
    )
    return {row.achievement_id: row.unlocked_at for row in rows}
