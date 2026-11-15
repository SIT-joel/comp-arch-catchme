"""Achievements: the catalog plus the user's unlocked rows. Unlocks are
evaluated server-side at the trigger points (quest completion, pet care,
partnership acceptance) — this route is read-only."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import achievements as achievement_service

router = APIRouter(prefix="/api/v1/achievements", tags=["achievements"])


def serialize(db: Session, user: User) -> dict:
    """The catalog annotated with the user's unlock state (for /me and the
    phone's achievements card)."""
    unlocked = achievement_service.unlocked_map(db, user)
    items = []
    for entry in achievement_service.catalog():
        at = unlocked.get(entry["id"])
        items.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "description": entry["description"],
                "unlocked": at is not None,
                "unlocked_at": at.isoformat() if at else None,
            }
        )
    return items


@router.get("")
def list_achievements(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"achievements": serialize(db, user)}


@router.get("/{user_id}")
def list_for_user(
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Partner-view: another user's unlocked set (names/descriptions are
    catalog-public; only the active partner can read it)."""
    from app.deps import get_pair_partner

    _, partner_id = get_pair_partner(db, user.id)
    if partner_id != user_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Not your partner."},
        )
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "No such user."}
        )
    return {"achievements": serialize(db, target)}
