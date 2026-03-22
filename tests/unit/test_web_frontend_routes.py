"""Tests for frontend SPA routing from the FastAPI server."""

from fastapi.testclient import TestClient

from ssync.web import app as web_app


def _client() -> TestClient:
    return TestClient(web_app.app, base_url="http://localhost")


def test_resolve_frontend_request_path_for_spa_route():
    resolved = web_app._resolve_frontend_request_path("jobs/12345/entalpic")

    assert resolved is not None
    assert resolved.name == "index.html"


def test_resolve_frontend_request_path_for_real_frontend_file():
    resolved = web_app._resolve_frontend_request_path("sw.js")

    assert resolved is not None
    assert resolved.name == "sw.js"


def test_resolve_frontend_request_path_skips_api_prefix():
    assert web_app._resolve_frontend_request_path("api/status") is None


def test_direct_job_route_serves_frontend_shell():
    client = _client()

    response = client.get("/jobs/12345/entalpic")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!doctype html>" in response.text.lower()


def test_frontend_root_file_served_directly():
    client = _client()

    response = client.get("/sw.js")

    assert response.status_code == 200


def test_unknown_api_route_does_not_fall_back_to_frontend():
    client = _client()

    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
