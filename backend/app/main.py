"""FastAPI application factory."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
        description="Two-wearable quest prototype backend.",
    )

    # Local development convenience; production serves web + api behind one proxy origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://catchme.12357895.xyz",
        ],
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
    from app.routers import achievements, pets, quiz

    app.include_router(pets.router)
    app.include_router(quiz.router)
    app.include_router(achievements.router)

    # Serve the built React SPA on non-API routes when running outside pytest so
    # the Cloudflare tunnel (routed to :8000) serves BOTH the Web app and API
    # from the same HTTPS origin.
    app_file = Path(__file__).resolve()
    web_dist = next(
        (cand for cand in (app_file.parents[1] / "web" / "dist", app_file.parents[2] / "web" / "dist")
         if (cand / "index.html").is_file()),
        None,
    )
    if "PYTEST_CURRENT_TEST" not in os.environ and web_dist is not None:
        index_html = web_dist / "index.html"
        assets_dir = web_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="web-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Resource not found."})
            target = (web_dist / full_path).resolve()
            if full_path and target.is_file() and str(target).startswith(str(web_dist.resolve())):
                return FileResponse(target)
            return FileResponse(index_html)

    return app


app = create_app()
