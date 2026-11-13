"""Partnership lifecycle: invitations, transactional acceptance, ending.

Concurrency contract (docs/DISCOVERY_PLAN.md):
- Acceptance locks BOTH user rows in canonical id order, revalidates
  eligibility, and creates the partnership + memberships inside one
  transaction. The partial unique index on partnership_members(user_id)
  WHERE left_at IS NULL is the database-level guarantee of one active
  partnership per user even if application locks are lost.
- Ending cancels the pair's pending/active quest sessions first, then
  closes memberships; awards, balances, transactions and purchases are
  never touched.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.models import (
    DiscoverySetting,
    Partnership,
    PartnershipMember,
    PartnerInvitation,
    QuestSession,
    SessionParticipant,
    User,
    UserInterest,
)


def pair_key(a: uuid.UUID, b: uuid.UUID) -> str:
    lo, hi = sorted((a, b), key=str)
    return f"{lo}:{hi}"


def canonical_user_lock(db: Session, user_ids) -> list[User]:
    """Lock user rows in canonical id order (deadlock avoidance)."""
    ordered = sorted(set(user_ids), key=str)
    return (
        db.query(User)
        .filter(User.id.in_(ordered))
        .with_for_update()
        .all()
    )


def eligibility_problem(
    db: Session, my_user_id: uuid.UUID, their_user_id: uuid.UUID
) -> str | None:
    """Return a machine-readable problem code, or None when both users are
    eligible to partner: unpaired, complete profiles, mutually compatible
    ages, at least one shared interest, and at least one discovery method
    enabled for both."""
    from app.services.discovery import (
        active_member_user_ids,
        ages_compatible,
        profile_complete,
        shared_methods,
        user_interests,
    )

    if my_user_id == their_user_id:
        return "self"
    my_setting = db.get(DiscoverySetting, my_user_id)
    their_setting = db.get(DiscoverySetting, their_user_id)
    my_tags = set(user_interests(db, my_user_id))
    their_tags = set(user_interests(db, their_user_id))

    if not profile_complete(my_setting, len(my_tags)):
        return "profile_incomplete"
    if not profile_complete(their_setting, len(their_tags)):
        return "their_profile_incomplete"
    if not ages_compatible(my_setting, their_setting):
        return "ages_incompatible"
    if not (my_tags & their_tags):
        return "no_shared_interest"
    if not shared_methods(my_setting, their_setting):
        return "no_shared_method"

    partnered = active_member_user_ids(db)
    if my_user_id in partnered:
        return "already_partnered"
    if their_user_id in partnered:
        return "their_already_partnered"
    return None


def create_invitation(
    db: Session, from_user: User, to_user_id: uuid.UUID
) -> PartnerInvitation:
    now = clock.now_utc()
    if db.get(User, to_user_id) is None:
        raise HTTPException(404, {"code": "user_not_found", "message": "No such user."})

    problem = eligibility_problem(db, from_user.id, to_user_id)
    if problem == "self":
        raise HTTPException(422, {"code": "self_invitation", "message": "You cannot invite yourself."})
    if problem == "already_partnered":
        raise HTTPException(409, {"code": "already_partnered", "message": "You already have a partner."})
    if problem == "their_already_partnered":
        raise HTTPException(409, {"code": "their_already_partnered", "message": "That user already has a partner."})
    if problem is not None:
        raise HTTPException(409, {"code": problem, "message": f"Invitation not allowed: {problem}."})

    duplicate = (
        db.query(PartnerInvitation)
        .filter(
            PartnerInvitation.pair_key == pair_key(from_user.id, to_user_id),
            PartnerInvitation.status == "pending",
        )
        .one_or_none()
    )
    if duplicate is not None:
        raise HTTPException(
            409,
            {"code": "duplicate_pending_invitation",
             "message": "A pending invitation already exists for this pair."},
        )

    invitation = PartnerInvitation(
        from_user_id=from_user.id,
        to_user_id=to_user_id,
        pair_key=pair_key(from_user.id, to_user_id),
        status="pending",
        created_at=now,
        expires_at=now + timedelta(seconds=get_settings().invitation_expiry_seconds),
    )
    db.add(invitation)
    return invitation


def expire_stale_invitations(db: Session, now: datetime | None = None) -> int:
    now = now or clock.now_utc()
    stale = (
        db.query(PartnerInvitation)
        .filter(
            PartnerInvitation.status == "pending",
            PartnerInvitation.expires_at < now,
        )
        .all()
    )
    for invitation in stale:
        invitation.status = "expired"
    return len(stale)


def accept_invitation(db: Session, invitation: PartnerInvitation, accepting_user: User) -> Partnership:
    """Transactional, idempotent acceptance.

    Lock order: invitation row, then both user rows in canonical order.
    On retry of an already-accepted invitation whose partnership is still
    active, the existing partnership is returned (idempotent success).
    """
    now = clock.now_utc()

    if invitation.to_user_id != accepting_user.id:
        raise HTTPException(
            403, {"code": "forbidden", "message": "Only the recipient may respond."}
        )

    if invitation.status == "accepted":
        member = (
            db.query(PartnershipMember)
            .filter(
                PartnershipMember.user_id == accepting_user.id,
                PartnershipMember.left_at.is_(None),
            )
            .one_or_none()
        )
        if member is not None:
            partnership = db.get(Partnership, member.partnership_id)
            if partnership is not None and partnership.ended_at is None:
                return partnership  # idempotent retry
        raise HTTPException(
            409,
            {"code": "invalid_transition",
             "message": "Invitation was already accepted; partnership is no longer active."},
        )
    if invitation.status in ("declined", "expired"):
        raise HTTPException(
            409,
            {"code": "invalid_transition",
             "message": f"Invitation is {invitation.status}."},
        )

    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        invitation.status = "expired"
        raise HTTPException(409, {"code": "invitation_expired", "message": "Invitation expired."})

    # Lock both users canonically; revalidate under the lock.
    canonical_user_lock(db, [invitation.from_user_id, invitation.to_user_id])
    problem = eligibility_problem(db, invitation.from_user_id, invitation.to_user_id)
    if problem is not None:
        raise HTTPException(
            409,
            {"code": problem if problem != "self" else "invalid_pair",
             "message": f"Cannot accept: eligibility changed ({problem})."},
        )

    partnership = Partnership(created_at=now)
    db.add(partnership)
    db.flush()
    db.add_all(
        [
            PartnershipMember(partnership_id=partnership.id,
                              user_id=invitation.from_user_id, joined_at=now),
            PartnershipMember(partnership_id=partnership.id,
                              user_id=invitation.to_user_id, joined_at=now),
        ]
    )
    invitation.status = "accepted"
    invitation.responded_at = now
    return partnership


def decline_invitation(db: Session, invitation: PartnerInvitation, responding_user: User) -> None:
    if invitation.to_user_id != responding_user.id:
        raise HTTPException(
            403, {"code": "forbidden", "message": "Only the recipient may respond."}
        )
    if invitation.status != "pending":
        raise HTTPException(
            409,
            {"code": "invalid_transition",
             "message": f"Invitation is {invitation.status}."},
        )
    invitation.status = "declined"
    invitation.responded_at = clock.now_utc()


def end_partnership(db: Session, ending_user: User) -> Partnership:
    """End the caller's active partnership.

    Cancels the pair's pending/active quest sessions first (in the same
    transaction), then closes both memberships. History, awards, balances,
    transactions and purchases are preserved untouched.
    """
    from app.deps import get_pair_partner

    now = clock.now_utc()
    partnership_id, partner_id = get_pair_partner(db, ending_user.id)
    if partnership_id is None or partner_id is None:
        raise HTTPException(
            409, {"code": "not_paired", "message": "You have no active partnership."}
        )

    partnership = (
        db.query(Partnership)
        .filter(Partnership.id == partnership_id)
        .with_for_update()
        .one()
    )
    members = (
        db.query(PartnershipMember)
        .filter(PartnershipMember.partnership_id == partnership_id)
        .with_for_update()
        .all()
    )

    # Cancel any pending/active quest sessions for this pair first.
    open_sessions = (
        db.query(QuestSession)
        .join(SessionParticipant, SessionParticipant.session_id == QuestSession.id)
        .filter(
            SessionParticipant.user_id.in_((ending_user.id, partner_id)),
            QuestSession.state.in_(("pending", "active")),
        )
        .with_for_update()
        .all()
    )
    from app.services.interactions import clear_unfinished_interaction

    for quest_session in open_sessions:
        quest_session.state = "cancelled"
        quest_session.cancelled_at = now
        clear_unfinished_interaction(db, quest_session.id)

    for member in members:
        member.left_at = now
    partnership.ended_at = now
    partnership.ended_by = ending_user.id
    return partnership
