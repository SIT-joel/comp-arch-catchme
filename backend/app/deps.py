"""FastAPI dependencies: authentication (bearer token or session cookie) and CSRF."""

import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LoginSession, User

SESSION_COOKIE = "catch_me_session"


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def _resolve_login_session(db: Session, token: str) -> LoginSession | None:
    from app.security import hash_token

    login = (
        db.query(LoginSession)
        .filter(LoginSession.token_hash == hash_token(token))
        .one_or_none()
    )
    if login is None:
        return None
    if login.revoked_at is not None:
        return None
    expires = login.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    return login


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer_token(request)
    used_cookie = False
    if token is None:
        token = request.cookies.get(SESSION_COOKIE)
        used_cookie = token is not None
    if not token:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Sign in required."})

    login = _resolve_login_session(db, token)
    if login is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_session", "message": "Session is invalid or expired."},
        )

    # CSRF: cookie-authenticated state-changing requests must echo the CSRF token.
    if used_cookie and request.method not in ("GET", "HEAD", "OPTIONS"):
        header_token = request.headers.get("x-csrf-token", "")
        if header_token != login.csrf_token:
            raise HTTPException(
                status_code=403,
                detail={"code": "csrf_failed", "message": "Missing or invalid CSRF token."},
            )

    user = db.get(User, login.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "User missing."})
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def get_pair_partner(db: Session, user_id: uuid.UUID) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Return (partnership_id, partner_user_id) for the user's ACTIVE
    partnership, or (None, None) when unpaired. Ended partnerships are
    history and never match here."""
    from app.models import Partnership, PartnershipMember

    mine = (
        db.query(PartnershipMember, Partnership)
        .join(Partnership, Partnership.id == PartnershipMember.partnership_id)
        .filter(
            PartnershipMember.user_id == user_id,
            PartnershipMember.left_at.is_(None),
            Partnership.ended_at.is_(None),
        )
        .all()
    )
    if len(mine) != 1:
        # 0 = unpaired; >1 is impossible (partial unique index on user_id).
        return None, None
    partnership_id = mine[0][1].id
    others = (
        db.query(PartnershipMember.user_id)
        .filter(
            PartnershipMember.partnership_id == partnership_id,
            PartnershipMember.user_id != user_id,
            PartnershipMember.left_at.is_(None),
        )
        .all()
    )
    if len(others) != 1:
        return None, None
    return partnership_id, others[0][0]
