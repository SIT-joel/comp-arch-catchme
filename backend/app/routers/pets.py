"""v2: pet mirror + daily care, landmark catalog (raid)."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user, get_pair_partner
from app.events import bump_state_version, publish_state_event
from app.models import Landmark, Pet, PointTransaction, User
from app.schemas import (
    LandmarkOut,
    LandmarksOut,
    PetCareIn,
    PetSummary,
    PetUpdateIn,
    pet_stage_for_xp,
)

router = APIRouter(prefix="/api/v1", tags=["pet"])


def _partner_id(db: Session, user_id):
    _, partner_id = get_pair_partner(db, user_id)
    return partner_id


def pet_summary(db: Session, user: User) -> PetSummary:
    pet = db.get(Pet, user.id)
    return PetSummary(
        species=pet.species if pet else None,
        name=pet.name if pet else None,
        level=1 + user.lifetime_xp // 100,
        lifetime_xp=user.lifetime_xp,
        evolution_stage=pet_stage_for_xp(user.lifetime_xp),
        care_streak=pet.care_streak if pet else 0,
        cared_today=bool(
            pet and pet.last_care_date == datetime.now(timezone.utc).date().isoformat()
        ),
        last_care_date=pet.last_care_date if pet else None,
    )


@router.get("/me/pet", response_model=PetSummary)
def get_pet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return pet_summary(db, user)


@router.put("/me/pet", response_model=PetSummary)
def update_pet(
    body: PetUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mirror the wearable's bonding choice. Cosmetic only — no XP/points."""
    pet = db.get(Pet, user.id)
    if pet is None:
        pet = Pet(user_id=user.id)
        db.add(pet)
    pet.species = body.species
    pet.name = body.name
    version = bump_state_version(db)
    db.commit()
    partner_id = _partner_id(db, user.id)
    publish_state_event(
        [user.id] + ([partner_id] if partner_id else []), version, kind="pet_changed"
    )
    return pet_summary(db, user)


@router.post("/me/pet/care", response_model=PetSummary)
def pet_care(
    body: PetCareIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Claim the daily care XP: +10 XP at most once per user per calendar day.

    The wearable performs care locally and relays the event through the phone;
    offline days sync later but the server cap is absolute. Idempotent per
    (user, date) via the PointTransaction unique key.
    """
    try:
        care_day = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "date must be YYYY-MM-DD."},
        )
    today = datetime.now(timezone.utc).date()
    if care_day > today:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "care_future_date",
                "message": "Care cannot be claimed for a future date.",
            },
        )
    if (today - care_day).days > 7:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "care_too_old",
                "message": "Care older than 7 days cannot be synced.",
            },
        )

    pet = db.get(Pet, user.id)
    if pet is None:
        pet = Pet(user_id=user.id)
        db.add(pet)

    date_str = care_day.isoformat()
    idempotency_key = f"care:{user.id}:{date_str}"
    existing = (
        db.query(PointTransaction)
        .filter(
            PointTransaction.user_id == user.id,
            PointTransaction.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None or pet.last_care_date == date_str:
        db.commit()  # idempotent replay: same state, no second grant
        return pet_summary(db, user)

    settings = get_settings()
    user = db.query(User).filter(User.id == user.id).with_for_update().one()
    user.lifetime_xp += settings.pet_care_xp
    # Out-of-order backfill must never regress the forward care chain.
    if pet.last_care_date is None or date_str > pet.last_care_date:
        yesterday = (care_day - timedelta(days=1)).isoformat()
        pet.care_streak = pet.care_streak + 1 if pet.last_care_date == yesterday else 1
        pet.last_care_date = date_str
    db.add(
        PointTransaction(
            user_id=user.id,
            kind="pet_care",
            delta=0,
            xp_delta=settings.pet_care_xp,
            balance_after=user.points_balance,
            idempotency_key=idempotency_key,
        )
    )
    version = bump_state_version(db)
    db.commit()
    partner_id = _partner_id(db, user.id)
    publish_state_event(
        [user.id] + ([partner_id] if partner_id else []), version, kind="pet_changed"
    )
    return pet_summary(db, user)


@router.get("/landmarks", response_model=LandmarksOut)
def list_landmarks(db: Session = Depends(get_db)):
    rows = db.query(Landmark).order_by(Landmark.id).all()
    return LandmarksOut(
        landmarks=[
            LandmarkOut(
                id=row.id,
                name=row.name,
                latitude=row.latitude,
                longitude=row.longitude,
                radius_m=row.radius_m,
            )
            for row in rows
        ]
    )
