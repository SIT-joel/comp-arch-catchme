"""Authenticated SSE state-change notifications."""

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_pair_partner
from app.events import bus, get_state_version
from app.models import User

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("")
async def events(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, partner_id = get_pair_partner(db, user.id)
    audience = [user.id] + ([partner_id] if partner_id else [])
    state_version = get_state_version(db)
    db.close()

    queue, registrations = bus.subscribe(audience)

    async def stream():
        try:
            hello = (
                "event: hello\ndata: "
                + f'{{"state_version": {state_version}}}\n\n'
            )
            yield hello
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: state\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(registrations)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
