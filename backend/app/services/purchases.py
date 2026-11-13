"""Transactional badge purchases with per-user idempotency."""

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import OwnedReward, PointTransaction, Reward, User


def purchase_reward(db: Session, user: User, reward_id: str, idempotency_key: str) -> dict:
    """Purchase a cosmetic badge. Returns a dict describing the outcome.

    Guarantees:
    - Concurrent requests can never overspend: the user row is locked and the
      balance check happens inside the transaction.
    - Repeating the same Idempotency-Key returns the stored outcome instead of
      double-debiting.
    - One-time ownership: (user_id, reward_id) is unique.
    """
    existing = (
        db.query(PointTransaction)
        .filter(
            PointTransaction.user_id == user.id,
            PointTransaction.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        reward = db.get(Reward, existing.reward_id)
        return {
            "reward_id": existing.reward_id,
            "price": -existing.delta,
            "balance_after": existing.balance_after,
            "owned": True,
            "idempotent_replay": True,
        }

    reward = db.get(Reward, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail={"code": "reward_not_found", "message": "Unknown reward."})

    already_owned = (
        db.query(OwnedReward)
        .filter(OwnedReward.user_id == user.id, OwnedReward.reward_id == reward.id)
        .one_or_none()
    )
    if already_owned is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "already_owned", "message": "This badge is already owned (one-time purchase)."},
        )

    locked_user = db.query(User).filter(User.id == user.id).with_for_update().one()
    if locked_user.points_balance < reward.price:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "insufficient_points",
                "message": f"Need {reward.price} points, balance is {locked_user.points_balance}.",
            },
        )

    locked_user.points_balance -= reward.price
    db.add(OwnedReward(user_id=locked_user.id, reward_id=reward.id))
    tx = PointTransaction(
        user_id=locked_user.id,
        kind="purchase",
        delta=-reward.price,
        xp_delta=0,  # spending points never reduces XP
        balance_after=locked_user.points_balance,
        reward_id=reward.id,
        idempotency_key=idempotency_key,
    )
    db.add(tx)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race on ownership or idempotency; surface as conflict.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "purchase_conflict", "message": "Purchase raced with another request."},
        )

    return {
        "reward_id": reward.id,
        "price": reward.price,
        "balance_after": locked_user.points_balance,
        "owned": True,
        "idempotent_replay": False,
    }
