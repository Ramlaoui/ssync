"""Tests for frontend SPA routing from the FastAPI server."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ssync.web.frontend import _resolve_frontend_request_path, register_frontend_routes


def _frontend_app(frontend_dist) -> FastAPI:
    app = FastAPI()
    assert register_frontend_routes(app, frontend_dist)
    return app


@pytest.fixture
def frontend_dist(tmp_path):
    frontend_dist = tmp_path / "dist"
    frontend_dist.mkdir()
    (frontend_dist / "assets").mkdir()
    (frontend_dist / "index.html").write_text("<!doctype html><html></html>")
    (frontend_dist / "sw.js").write_text("self.addEventListener('fetch', () => {})")
    return frontend_dist


def test_resolve_frontend_request_path_for_spa_route(frontend_dist):
    resolved = _resolve_frontend_request_path(frontend_dist, "jobs/12345/entalpic")

    assert resolved is not None
    assert resolved.name == "index.html"


def test_resolve_frontend_request_path_for_real_frontend_file(frontend_dist):
    resolved = _resolve_frontend_request_path(frontend_dist, "sw.js")

    assert resolved is not None
    assert resolved.name == "sw.js"


def test_resolve_frontend_request_path_skips_api_prefix(frontend_dist):
    assert _resolve_frontend_request_path(frontend_dist, "api/status") is None


def test_direct_job_route_serves_frontend_shell(frontend_dist):
    client = TestClient(_frontend_app(frontend_dist), base_url="http://localhost")

    response = client.get("/jobs/12345/entalpic")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!doctype html>" in response.text.lower()


def test_frontend_root_file_served_directly(frontend_dist):
    client = TestClient(_frontend_app(frontend_dist), base_url="http://localhost")

    response = client.get("/sw.js")

    assert response.status_code == 200


def test_unknown_api_route_does_not_fall_back_to_frontend(frontend_dist):
    client = TestClient(_frontend_app(frontend_dist), base_url="http://localhost")

    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
