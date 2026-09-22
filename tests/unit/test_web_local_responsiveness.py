"""Regression tests for local web work staying off the asyncio event loop."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from ssync.web.api import catalog as catalog_api
from ssync.web.api import local_fs as local_fs_api
from ssync.web.api import notifications as notifications_api
from ssync.web.api import watchers as watchers_api
from ssync.web.models import NotificationPreferencesPatch


def _endpoint(app: FastAPI, path: str, method: str):
    for route in app.routes:
        if route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Missing {method} {path} route")


async def _assert_blocking_work_is_off_loop(task, started, release, call_thread):
    assert await asyncio.wait_for(asyncio.to_thread(started.wait, 1), timeout=1)
    assert call_thread["ident"] != threading.get_ident()

    loop_responsive = asyncio.Event()
    asyncio.get_running_loop().call_soon(loop_responsive.set)
    await asyncio.wait_for(loop_responsive.wait(), timeout=0.2)
    assert not task.done()

    release.set()
    return await asyncio.wait_for(task, timeout=1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_discovery_does_not_block_event_loop(monkeypatch, tmp_path):
    started = threading.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    call_thread = {}

    def blocking_discovery(**_kwargs):
        call_thread["ident"] = threading.get_ident()
        loop.call_soon_threadsafe(started.set)
        assert release.wait(1)
        return SimpleNamespace(
            warnings=[],
            to_dict=lambda: {
                "repo_root": str(tmp_path),
                "include_user_config": False,
                "roots": [],
                "hosts": [],
                "recipes": [],
                "workflows": [],
                "partitions": [],
                "envs": [],
                "watchers": [],
                "host_profiles": [],
                "warnings": [],
            },
        )

    monkeypatch.setattr(catalog_api, "discover_launch_catalog", blocking_discovery)
    app = FastAPI()
    catalog_api.register_catalog_routes(
        app,
        verify_api_key_dependency=lambda: True,
        get_slurm_manager=lambda: SimpleNamespace(slurm_hosts=[]),
    )
    route = _endpoint(app, "/api/launch-catalog", "GET")
    task = asyncio.create_task(
        route(
            repo_root=str(tmp_path),
            include_user_config=False,
            force_refresh=True,
            _authenticated=True,
        )
    )

    response = await _assert_blocking_work_is_off_loop(
        task, started, release, call_thread
    )
    assert response.cached is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_listing_does_not_block_event_loop(monkeypatch, tmp_path):
    started = threading.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    call_thread = {}
    original = local_fs_api._list_local_path

    def blocking_listing(**kwargs):
        call_thread["ident"] = threading.get_ident()
        loop.call_soon_threadsafe(started.set)
        assert release.wait(1)
        return original(**kwargs)

    monkeypatch.setattr(local_fs_api, "_list_local_path", blocking_listing)
    app = FastAPI()
    local_fs_api.register_local_fs_routes(app, verify_api_key_dependency=lambda: True)
    route = _endpoint(app, "/api/local/list", "GET")
    task = asyncio.create_task(
        route(
            path=str(tmp_path),
            limit=10,
            show_hidden=False,
            dirs_only=False,
            _authenticated=True,
        )
    )

    response = await _assert_blocking_work_is_off_loop(
        task, started, release, call_thread
    )
    assert response["path"] == str(tmp_path)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watcher_db_read_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    call_thread = {}

    def blocking_read(**_kwargs):
        call_thread["ident"] = threading.get_ident()
        loop.call_soon_threadsafe(started.set)
        assert release.wait(1)
        return {"watchers": [], "count": 0}

    monkeypatch.setattr(watchers_api, "get_job_watchers_payload", blocking_read)
    app = FastAPI()
    watchers_api.register_watcher_routes(
        app,
        verify_api_key_dependency=lambda: True,
        get_slurm_manager=lambda: SimpleNamespace(),
    )
    route = _endpoint(app, "/api/jobs/{job_id}/watchers", "GET")
    task = asyncio.create_task(route(job_id="100", host=None, _authenticated=True))

    response = await _assert_blocking_work_is_off_loop(
        task, started, release, call_thread
    )
    assert response == {"watchers": [], "count": 0}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notification_preferences_write_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    call_thread = {}

    class BlockingCache:
        def get_notification_preferences(self, **_kwargs):
            return {
                "enabled": True,
                "allowed_states": None,
                "muted_job_ids": [],
                "muted_hosts": [],
                "muted_job_name_patterns": [],
                "allowed_users": [],
            }

        def upsert_notification_preferences(self, **_kwargs):
            call_thread["ident"] = threading.get_ident()
            loop.call_soon_threadsafe(started.set)
            assert release.wait(1)

    monkeypatch.setattr(notifications_api, "get_cache", lambda: BlockingCache())
    app = FastAPI()
    notifications_api.register_notification_routes(
        app,
        get_api_key_dependency=lambda: "secret",
        verify_api_key_dependency=lambda: True,
        notification_settings=SimpleNamespace(apns_bundle_id=None),
    )
    route = _endpoint(app, "/api/notifications/preferences", "PATCH")
    task = asyncio.create_task(
        route(
            payload=NotificationPreferencesPatch(enabled=False),
            api_key="secret",
        )
    )

    response = await _assert_blocking_work_is_off_loop(
        task, started, release, call_thread
    )
    assert response.enabled is False
