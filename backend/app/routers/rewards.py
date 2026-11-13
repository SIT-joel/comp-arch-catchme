"""Reward catalog, transactional purchases, and transaction history."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.events import bump_state_version, publish_state_event
from app.models import OwnedReward, PointTransaction, Reward, User
from app.schemas import PurchaseIn, PurchaseOut, RewardOut, RewardsOut, TransactionOut, TransactionsOut
from app.services.purchases import purchase_reward

router = APIRouter(prefix="/api/v1", tags=["rewards"])


@router.get("/rewards", response_model=RewardsOut)
def rewards(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    catalog = db.query(Reward).order_by(Reward.price).all()
    owned_ids = {
        row.reward_id
        for row in db.query(OwnedReward)
        .filter(OwnedReward.user_id == user.id)
        .all()
    }
    return RewardsOut(
        points=user.points_balance,
        rewards=[
            RewardOut(
                id=r.id, name=r.name, description=r.description, price=r.price, owned=r.id in owned_ids
            )
            for r in catalog
        ],
    )


@router.post("/purchases", response_model=PurchaseOut, status_code=201)
def purchase(
    body: PurchaseIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    result = purchase_reward(db, user, body.reward_id, idempotency_key)
    version = bump_state_version(db)
    db.commit()
    publish_state_event([user.id], version, kind="purchase")
    return PurchaseOut(
        reward_id=result["reward_id"],
        price=result["price"],
        balance_after=result["balance_after"],
        owned=result["owned"],
    )


@router.get("/transactions", response_model=TransactionsOut)
def transactions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(PointTransaction)
        .filter(PointTransaction.user_id == user.id)
        .order_by(PointTransaction.id.desc())
        .limit(100)
        .all()
    )
    return TransactionsOut(transactions=rows)
