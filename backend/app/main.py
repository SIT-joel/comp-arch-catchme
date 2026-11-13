"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import (
    auth,
    devices,
    discovery,
    events,
    interactions,
    me,
    partnerships,
    quests,
    rewards,
    sessions,
    telemetry,
)


def _error(status: int, code: str, message: str, fields=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return JSONResponse(status_code=status, content=body)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Catch Me API",
        version="0.1.0",
        description="Two-wearable quest prototype backend. Contract: docs/INTERFACES.md.",
    )

    # Local development convenience; production serves web + api behind one proxy origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = sorted({str(err.get("loc", ())[-1]) for err in exc.errors()})
        return _error(422, "validation_error", "Invalid request payload.", fields)

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return _error(404, "not_found", "Resource not found.")

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return _error(exc.status_code, detail.get("code", "error"), detail.get("message", ""))

    app.include_router(quests.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(devices.router)
    app.include_router(sessions.router)
    app.include_router(interactions.router)
    app.include_router(telemetry.router)
    app.include_router(events.router)
    app.include_router(rewards.router)
    app.include_router(discovery.router)
    app.include_router(partnerships.router)
    from app.routers import pets, quiz

    app.include_router(pets.router)
    app.include_router(quiz.router)

    return app


app = create_app()
