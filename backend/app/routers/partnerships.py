"""Partner invitations and partnership lifecycle (docs/DISCOVERY_PLAN.md).

Partner invitation acceptance is separate from quest-session acceptance.
Either partner may end the partnership; the pair's pending/active quests
are cancelled first inside the same transaction. Seeded partnerships are
only ever ended explicitly through DELETE /me/partnership.
"""

import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import clock
from app.db import get_db
from app.deps import get_current_user, get_pair_partner
from app.events import bump_state_version, publish_state_event
from app.models import Partnership, PartnershipMember, PartnerInvitation, User
from app.schemas import (
    InvitationCreateIn,
    InvitationOut,
    InvitationsOut,
    PartnershipOut,
    PartnerSummary,
)
from app.services import partnerships as service

router = APIRouter(prefix="/api/v1", tags=["partnerships"])


def _invitation_out(db: Session, invitation: PartnerInvitation) -> InvitationOut:
    from_name = db.get(User, invitation.from_user_id).display_name
    to_name = db.get(User, invitation.to_user_id).display_name
    return InvitationOut(
        id=invitation.id,
        from_user_id=invitation.from_user_id,
        from_name=from_name,
        to_user_id=invitation.to_user_id,
        to_name=to_name,
        status=invitation.status,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        responded_at=invitation.responded_at,
    )


@router.post("/invitations", status_code=201, response_model=InvitationOut)
def create_invitation(
    body: InvitationCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitation = service.create_invitation(db, user, body.to_user_id)
    version = bump_state_version(db)
    db.commit()
    publish_state_event([user.id, body.to_user_id], version, kind="invitation_created")
    db.refresh(invitation)
    return _invitation_out(db, invitation)


@router.get("/invitations", response_model=InvitationsOut)
def list_invitations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    service.expire_stale_invitations(db)
    db.commit()

    rows = (
        db.query(PartnerInvitation)
        .filter(
            (PartnerInvitation.from_user_id == user.id)
            | (PartnerInvitation.to_user_id == user.id),
            PartnerInvitation.status == "pending",
        )
        .order_by(PartnerInvitation.created_at.desc())
        .all()
    )
    incoming = [_invitation_out(db, i) for i in rows if i.to_user_id == user.id]
    outgoing = [_invitation_out(db, i) for i in rows if i.from_user_id == user.id]
    return InvitationsOut(incoming=incoming, outgoing=outgoing)


@router.post("/invitations/{invitation_id}/accept", response_model=PartnershipOut)
def accept_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitation = (
        db.query(PartnerInvitation)
        .filter(PartnerInvitation.id == invitation_id)
        .with_for_update()
        .one_or_none()
    )
    if invitation is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such invitation."})

    partnership = service.accept_invitation(db, invitation, user)
    version = bump_state_version(db)
    db.commit()
    publish_state_event(
        [invitation.from_user_id, invitation.to_user_id], version,
        kind="partnership_started",
    )
    return _partnership_out(db, partnership.id, user.id)


@router.post("/invitations/{invitation_id}/decline", response_model=InvitationOut)
def decline_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitation = (
        db.query(PartnerInvitation)
        .filter(PartnerInvitation.id == invitation_id)
        .with_for_update()
        .one_or_none()
    )
    if invitation is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such invitation."})

    service.decline_invitation(db, invitation, user)
    version = bump_state_version(db)
    db.commit()
    publish_state_event(
        [invitation.from_user_id, invitation.to_user_id], version,
        kind="invitation_declined",
    )
    db.refresh(invitation)
    return _invitation_out(db, invitation)


def _partnership_out(db: Session, partnership_id: uuid.UUID, for_user: uuid.UUID) -> PartnershipOut:
    partnership = db.get(Partnership, partnership_id)
    members = (
        db.query(PartnershipMember)
        .filter(PartnershipMember.partnership_id == partnership_id)
        .all()
    )
    partner_summary = None
    for member in members:
        if member.user_id != for_user:
            partner_user = db.get(User, member.user_id)
            if partner_user is not None:
                partner_summary = PartnerSummary(
                    id=partner_user.id,
                    display_name=partner_user.display_name,
                    level=1 + partner_user.lifetime_xp // 100,
                    location_sharing=partner_user.location_sharing,
                )
    return PartnershipOut(
        id=partnership.id,
        since=partnership.created_at,
        ended_at=partnership.ended_at,
        ended_by=partnership.ended_by,
        partner=partner_summary,
    )


@router.get("/me/partnership", response_model=PartnershipOut)
def my_partnership(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    partnership_id, _ = get_pair_partner(db, user.id)
    if partnership_id is None:
        raise HTTPException(
            404, {"code": "not_paired", "message": "No active partnership."}
        )
    return _partnership_out(db, partnership_id, user.id)


@router.delete("/me/partnership", response_model=PartnershipOut)
def end_partnership(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    partnership = service.end_partnership(db, user)
    member_ids = [
        m.user_id
        for m in db.query(PartnershipMember)
        .filter(PartnershipMember.partnership_id == partnership.id)
        .all()
    ]
    version = bump_state_version(db)
    db.commit()
    publish_state_event(member_ids, version, kind="partnership_ended")
    return _partnership_out(db, partnership.id, user.id)
