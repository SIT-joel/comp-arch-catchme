"""Mint a login session for a seeded user directly in the database.

TEST/DEMO TOOL: the second demo user (toma) has no phone connected in the
single-phone bench setup; this mints a server-side session so the partner
invitation flow can be exercised live over the real HTTP API. Not part of
the product; never used by the app or production paths.

Usage: py -3 tools/mint_session.py <username>
Prints a Bearer token (valid for the standard session TTL).
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from app.db import SessionLocal  # noqa: E402
from app.models import LoginSession, User  # noqa: E402
from app.security import hash_token, new_token  # noqa: E402


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else "toma"
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).one_or_none()
    if user is None:
        print(f"no such user: {username}")
        sys.exit(1)
    token = new_token()
    now = datetime.now(timezone.utc)
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_token=new_token(),
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )
    db.commit()
    db.close()
    print(f"{username} {user.id} {token}")


if __name__ == "__main__":
    main()
