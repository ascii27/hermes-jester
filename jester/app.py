"""Application factory: wires routers, middleware, and error handling."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings, get_settings
from .errors import (
    ConflictError,
    NotFoundError,
    PayloadInvalidError,
    SchemaInvalidError,
)

_ERROR_STATUS = {
    NotFoundError: 404,
    ConflictError: 409,
    PayloadInvalidError: 422,
    SchemaInvalidError: 422,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="hermes-jester")
    app.state.settings = settings

    from .auth_ui import build_oauth, router as auth_router
    from .api import router as api_router
    from .ui import router as ui_router

    app.state.oauth = build_oauth(settings)

    # Signs the UI session cookie (Google login state + flash messages).
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(api_router)
    app.include_router(auth_router)
    app.include_router(ui_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    for exc_type, status in _ERROR_STATUS.items():
        def _make_handler(status_code: int):
            async def handler(_request: Request, exc: Exception):
                return JSONResponse(status_code=status_code, content={"error": str(exc)})

            return handler

        app.add_exception_handler(exc_type, _make_handler(status))

    return app
