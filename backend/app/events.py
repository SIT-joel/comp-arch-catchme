"""In-memory SSE fan-out plus the DB-backed global state version.

Single-process design (one API worker) per docs/ARCHITECTURE.md. PostgreSQL is
the source of truth: clients that miss an event refetch the canonical snapshot.
"""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

STATE_VERSION_KEY = "state_version"


def get_state_version(db: Session) -> int:
    row = db.execute(
        text("SELECT value FROM app_state WHERE key = :k"), {"k": STATE_VERSION_KEY}
    ).scalar_one_or_none()
    return int(row) if row is not None else 0


def bump_state_version(db: Session) -> int:
    """Increment and return the new version. Call inside the same transaction
    as the state change it describes; publish only after commit."""
    row = db.execute(
        text("SELECT value FROM app_state WHERE key = :k"), {"k": STATE_VERSION_KEY}
    ).scalar_one_or_none()
    if row is None:
        db.execute(
            text("INSERT INTO app_state (key, value) VALUES (:k, :v)"),
            {"k": STATE_VERSION_KEY, "v": 1},
        )
        return 1
    new = int(row) + 1
    db.execute(
        text("UPDATE app_state SET value = :v WHERE key = :k"),
        {"k": STATE_VERSION_KEY, "v": new},
    )
    return new


class EventBus:
    """Fan-out of small JSON events to per-user subscriber queues.

    Subscribers record the event loop that owns their queue; publishers may be
    called from sync endpoint threads, so puts are marshalled onto the owning
    loop with call_soon_threadsafe (asyncio.Queue is not thread-safe).
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, user_ids: list) -> tuple[asyncio.Queue, list[tuple]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        registrations = []
        for uid in user_ids:
            registration = (asyncio.get_running_loop(), queue)
            self._subscribers.setdefault(uid, set()).add(registration)
            registrations.append(registration)
        return queue, registrations

    def unsubscribe(self, registrations: list[tuple]) -> None:
        for registration in registrations:
            # registration may be duplicated across uids; scan all buckets.
            for bucket in self._subscribers.values():
                bucket.discard(registration)
        self._subscribers = {uid: s for uid, s in self._subscribers.items() if s}

    def publish(self, user_ids: list, event: dict) -> None:
        import json

        payload = json.dumps(event, default=str)
        seen: set[int] = set()
        for uid in user_ids:
            for loop, queue in list(self._subscribers.get(uid, ())):
                key = id(queue)
                if key in seen:
                    continue
                seen.add(key)

                def _deliver(q=queue, p=payload):
                    try:
                        q.put_nowait(p)
                    except asyncio.QueueFull:
                        try:
                            q.get_nowait()
                            q.put_nowait(p)
                        except asyncio.QueueEmpty:
                            pass

                try:
                    loop.call_soon_threadsafe(_deliver)
                except RuntimeError:
                    pass  # loop closed; subscriber is gone


bus = EventBus()


def publish_state_event(
    db_user_ids: list,
    state_version: int,
    session_id=None,
    kind: str = "state",
) -> None:
    event = {
        "type": kind,
        "state_version": state_version,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
    if session_id is not None:
        event["session_id"] = str(session_id)
    bus.publish(db_user_ids, event)
