"""Frontend asset serving and SPA fallback registration."""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_FRONTEND_RESERVED_PREFIXES = (
    "api",
    "assets",
    "docs",
    "redoc",
    "ws",
    "health",
)


def _resolve_frontend_request_path(frontend_dist: Path, full_path: str) -> Optional[Path]:
    """Resolve a frontend deep-link or static file request."""
    normalized = full_path.strip("/")
    if not normalized:
        return frontend_dist / "index.html"

    first_segment = normalized.split("/", 1)[0]
    if first_segment in _FRONTEND_RESERVED_PREFIXES or normalized == "openapi.json":
        return None

    requested_path = (frontend_dist / normalized).resolve()
    try:
        requested_path.relative_to(frontend_dist.resolve())
    except ValueError:
        return None

    if requested_path.is_file():
        return requested_path

    if requested_path.suffix:
        return None

    return frontend_dist / "index.html"


def register_frontend_routes(app: FastAPI, frontend_dist: Path) -> bool:
    """Register static asset and SPA routes when the frontend build exists."""
    if not frontend_dist.exists():
        return False

    app.mount(
        "/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets"
    )

    @app.get("/", response_class=FileResponse)
    async def serve_frontend():
        """Serve the frontend application."""
        return FileResponse(str(frontend_dist / "index.html"))

    @app.get("/favicon.ico", response_class=FileResponse)
    async def serve_favicon():
        """Serve favicon."""
        return FileResponse(str(frontend_dist / "favicon.ico"))

    @app.get("/favicon.svg", response_class=FileResponse)
    async def serve_favicon_svg():
        """Serve SVG favicon."""
        return FileResponse(str(frontend_dist / "favicon.svg"))

    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_frontend_spa_fallback(full_path: str):
        """Serve SPA routes and root-level frontend files on direct navigation."""
        resolved_path = _resolve_frontend_request_path(frontend_dist, full_path)
        if resolved_path is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(str(resolved_path))

    return True
