"""/me: own profile, partner summary, device; location-sharing toggle."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_pair_partner
from app.models import Device, User
from app.schemas import DeviceSummary, LocationSharingIn, MeOut, PartnerSummary, user_summary

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, partner_id = get_pair_partner(db, user.id)
    partner = None
    if partner_id:
        partner_user = db.get(User, partner_id)
        if partner_user:
            partner = PartnerSummary(
                id=partner_user.id,
                display_name=partner_user.display_name,
                level=1 + partner_user.lifetime_xp // 100,
                location_sharing=partner_user.location_sharing,
            )
    device = db.query(Device).filter(Device.owner_user_id == user.id).one_or_none()
    from app.routers.pets import pet_summary

    return MeOut(
        user=user_summary(user),
        partner=partner,
        device=DeviceSummary(
            id=device.id,
            name=device.name,
            firmware_alias=device.firmware_alias,
            claimed_at=device.claimed_at,
        )
        if device
        else None,
        pet=pet_summary(db, user),
    )


@router.put("/location-sharing", status_code=204)
def set_location_sharing(
    body: LocationSharingIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.events import bump_state_version, publish_state_event

    user.location_sharing = body.enabled
    version = bump_state_version(db)
    db.commit()
    _, partner_id = get_pair_partner(db, user.id)
    publish_state_event([user.id] + ([partner_id] if partner_id else []), version, kind="sharing_changed")
    return None
