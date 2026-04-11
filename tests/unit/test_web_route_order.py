"""Regression tests for web route registration order."""

import importlib
from pathlib import Path

from fastapi import FastAPI

import ssync.web.frontend as frontend_module


def _route_index(app: FastAPI, path: str) -> int:
    for index, route in enumerate(app.router.routes):
        if getattr(route, "path", None) == path:
            return index
    raise AssertionError(f"Route {path} not found")


def test_spa_fallback_is_registered_after_api_routes(monkeypatch):
    original_exists = Path.exists

    def fake_register_frontend_routes(app: FastAPI, frontend_dist):
        @app.get("/")
        async def serve_frontend():
            return {"frontend": True}

        @app.get("/{full_path:path}")
        async def serve_frontend_spa_fallback(full_path: str):
            return {"path": full_path}

        return True

    def fake_exists(path: Path):
        if str(path).endswith("web-frontend/dist"):
            return True
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(
        frontend_module,
        "register_frontend_routes",
        fake_register_frontend_routes,
    )

    import ssync.web.app as app_module

    app_module = importlib.reload(app_module)
    app = app_module.app

    spa_index = _route_index(app, "/{full_path:path}")

    assert _route_index(app, "/health") < spa_index
    assert _route_index(app, "/api/hosts") < spa_index
    assert _route_index(app, "/api/jobs/{job_id}") < spa_index
