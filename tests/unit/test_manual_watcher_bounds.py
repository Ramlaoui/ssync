import gzip
import io
import tracemalloc
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from ssync.web import admission
from ssync.web.api import watchers as watcher_api
from ssync.web.services import watchers as watcher_service


class OutputCache:
    def __init__(self, stdout, stderr=b""):
        self.outputs = {"stdout": stdout, "stderr": stderr}

    @contextmanager
    def open_job_output(self, job_id, hostname, kind):
        with io.BytesIO(self.outputs[kind]) as source:
            yield source, "gzip", 0


def test_manual_cache_scan_rejects_large_gzip_before_expanding_it(monkeypatch):
    source = gzip.compress(b"x" * (64 * 1024**2), compresslevel=1)
    cache = OutputCache(source, gzip.compress(b""))
    monkeypatch.setattr(watcher_service, "MAX_MANUAL_WATCHER_BYTES", 256 * 1024)
    tracemalloc.start()
    try:
        with pytest.raises(watcher_service.WatcherOutputTooLarge):
            watcher_service.load_cached_watcher_output_text(
                cache=cache, job_id="1", hostname="test", watcher_id=1
            )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 2 * 1024**2


def test_manual_scan_only_decodes_selected_output(monkeypatch):
    text = "READY=café 🌍\n"
    cache = OutputCache(gzip.compress(text.encode()), gzip.compress(b"x" * 10000))
    monkeypatch.setattr(watcher_service, "MAX_MANUAL_WATCHER_BYTES", 64)
    assert watcher_service.load_cached_watcher_output_text(
        cache=cache, job_id="1", hostname="test", watcher_id=1, output_type="stdout"
    ) == (text, "")
    with pytest.raises(watcher_service.WatcherOutputTooLarge):
        watcher_service.load_cached_watcher_output_text(
            cache=cache, job_id="1", hostname="test", watcher_id=1, output_type="both"
        )


def test_remote_manual_scan_caps_read_and_reports_overflow():
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(ok=True, stdout="x" * 17)

    with pytest.raises(watcher_service.WatcherOutputTooLarge):
        watcher_service.read_remote_output(
            SimpleNamespace(run=run), "/logs/job's output", "stdout", 16
        )
    assert len(commands) == 1
    assert commands[0].startswith("head -c 17 -- ")


@pytest.mark.asyncio
async def test_manual_route_rejects_chunked_oversized_body_and_recovers(monkeypatch):
    monkeypatch.setattr(admission, "MAX_MANUAL_WATCHER_BYTES", 32)
    app = FastAPI()
    app.add_middleware(admission.RequestAdmissionMiddleware)

    async def trigger(**kwargs):
        return {"success": True}

    monkeypatch.setattr(watcher_api, "trigger_watcher_manually_payload", trigger)
    monkeypatch.setattr(watcher_api, "get_cache", lambda: None)
    watcher_api.register_watcher_routes(
        app, verify_api_key_dependency=lambda: True, get_slurm_manager=lambda: None
    )

    async def chunks():
        yield b'"' + b"x" * 16
        yield b"x" * 16 + b'"'

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/watchers/1/trigger",
            content=chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        response = await client.post("/api/watchers/1/trigger", json="READY=done")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_manual_output_limit_has_explicit_http_error(monkeypatch):
    app = FastAPI()

    async def oversized(**kwargs):
        raise watcher_service.WatcherOutputTooLarge()

    monkeypatch.setattr(watcher_api, "trigger_watcher_manually_payload", oversized)
    monkeypatch.setattr(watcher_api, "get_cache", lambda: None)
    watcher_api.register_watcher_routes(
        app, verify_api_key_dependency=lambda: True, get_slurm_manager=lambda: None
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/watchers/1/trigger")
    assert response.status_code == 413
    assert "8 MiB" in response.json()["detail"]
