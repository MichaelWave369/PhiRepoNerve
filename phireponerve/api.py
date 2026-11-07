"""Loopback-only read-only API and dashboard. Do not expose private data publicly."""

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

from .store import FleetStore


def create_app(db_path):
    store = FleetStore(db_path)
    app = FastAPI(title="Phi RepoNerve", version="0.1.0", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/")
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def health():
        return {"service": "phireponerve", "status": "ok", "scope": "local-read-only"}

    @app.get("/api/summary")
    def summary():
        return store.summary()

    @app.get("/api/repos")
    def repos(limit: int = Query(100, ge=1, le=500),
              offset: int = Query(0, ge=0), q: str = Query("", max_length=120)):
        return {"items": store.repositories(limit=limit, offset=offset, query=q),
                "limit": limit, "offset": offset}

    @app.get("/api/events")
    def events(limit: int = Query(50, ge=1, le=200),
               offset: int = Query(0, ge=0)):
        return {"items": store.events(limit=limit, offset=offset),
                "limit": limit, "offset": offset}

    return app
