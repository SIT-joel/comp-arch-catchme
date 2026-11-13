"""Quest catalog, health, and server time."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import QuestOut, QuestsOut, ServerTimeOut

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "catch-me-api", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/time", response_model=ServerTimeOut)
def server_time():
    now = datetime.now(timezone.utc)
    return ServerTimeOut(server_time=now, unix_ms=int(now.timestamp() * 1000))


@router.get("/quests", response_model=QuestsOut)
def quests():
    settings = get_settings()
    return QuestsOut(
        quests=[
            QuestOut(geofence_configured=settings.geofence_configured(), **q)
            for q in settings.quest_catalog()
        ]
    )
