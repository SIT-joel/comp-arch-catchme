"""Authentication: login/logout with bearer tokens (Android) and a
Secure/HttpOnly/SameSite cookie session (web/SSE) backed by the same store."""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import SESSION_COOKIE, get_current_user
from app.models import LoginSession, User
from app.schemas import LoginIn, LoginOut, user_summary
from app.security import hash_token, new_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _login_response(db: Session, response: Response, user: User) -> LoginOut:
    settings = get_settings()
    token = new_token()
    csrf_token = hashlib.sha256(new_token().encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
    )
    db.commit()

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
    summary = user_summary(user)
    return LoginOut(user=summary, token=token, csrf_token=csrf_token, expires_at=expires_at)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip()).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Username or password is incorrect."},
        )
    return _login_response(db, response, user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if token:
        login = (
            db.query(LoginSession)
            .filter(LoginSession.token_hash == hash_token(token))
            .one_or_none()
        )
        if login and login.revoked_at is None:
            login.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie(SESSION_COOKIE)
    return None
