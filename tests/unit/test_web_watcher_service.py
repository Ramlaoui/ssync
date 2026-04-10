from types import SimpleNamespace

import pytest

import ssync.watchers as watchers_pkg
from ssync.models.job import JobState
from ssync.web.services import watchers as watcher_service


class DummySlurmManager:
    def get_job_info(self, _host, _job_id):
        return SimpleNamespace(state=JobState.RUNNING)

    def get_host_by_name(self, host):
        return host


@pytest.mark.unit
def test_create_watcher_allows_job_end_trigger_without_pattern(monkeypatch, test_cache):
    monkeypatch.setattr(watcher_service, "start_watcher_task", lambda *args: None)

    watcher = watcher_service.create_watcher(
        cache=test_cache,
        watcher_config={
            "job_id": "12345",
            "hostname": "cluster",
            "name": "job-end-resubmit",
            "trigger_on_job_end": True,
            "actions": [{"type": "resubmit", "params": {"reason": "failed"}}],
        },
        get_slurm_manager=DummySlurmManager,
    )

    assert watcher["pattern"] == ""
    assert watcher["trigger_on_job_end"] is True
    assert watcher["trigger_job_states"] == ["completed", "failed", "timeout"]


@pytest.mark.unit
def test_update_watcher_can_switch_to_job_end_trigger_without_pattern(
    monkeypatch, test_cache
):
    monkeypatch.setattr(watcher_service, "start_watcher_task", lambda *args: None)

    created = watcher_service.create_watcher(
        cache=test_cache,
        watcher_config={
            "job_id": "12345",
            "hostname": "cluster",
            "name": "error-monitor",
            "pattern": "ERROR",
            "actions": [{"type": "log_event"}],
        },
        get_slurm_manager=DummySlurmManager,
    )

    updated = watcher_service.update_watcher(
        cache=test_cache,
        watcher_id=created["id"],
        watcher_update={
            "pattern": "",
            "trigger_on_job_end": True,
        },
    )

    assert updated["pattern"] == ""
    assert updated["trigger_on_job_end"] is True
    assert updated["trigger_job_states"] == ["completed", "failed", "timeout"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attach_watchers_builds_job_end_trigger_definitions(monkeypatch):
    captured = {}

    class DummyWatcherEngine:
        async def start_watchers_for_job(self, job_id, host, watchers):
            captured["job_id"] = job_id
            captured["host"] = host
            captured["watchers"] = watchers
            return [101]

    monkeypatch.setattr(
        watchers_pkg,
        "get_watcher_engine",
        lambda: DummyWatcherEngine(),
    )

    payload = await watcher_service.attach_watchers_to_job_payload(
        get_slurm_manager=DummySlurmManager,
        job_id="12345",
        host="cluster",
        watchers=[
            {
                "name": "job-end-resubmit",
                "trigger_on_job_end": True,
                "actions": [{"type": "resubmit"}],
            }
        ],
    )

    watcher_def = captured["watchers"][0]

    assert payload["watcher_ids"] == [101]
    assert captured["job_id"] == "12345"
    assert captured["host"] == "cluster"
    assert watcher_def.pattern == ""
    assert watcher_def.trigger_on_job_end is True
    assert watcher_def.trigger_job_states == ["completed", "failed", "timeout"]
    assert watcher_def.actions[0].type.value == "resubmit"
