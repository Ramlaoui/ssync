import pytest

from ssync.models.job import JobState
from ssync.models.watcher import ActionType, WatcherAction, WatcherDefinition, WatcherInstance
from ssync.watchers import engine as engine_module


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_end_watcher_captures_during_run_and_executes_once_on_terminal_state(
    monkeypatch, test_cache
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=1,
        job_id="12345",
        hostname="cluster",
        definition=WatcherDefinition(
            name="resume",
            pattern=r"HYDRA_OUTPUT_DIR=(.+)",
            captures=["resume_run_dir"],
            actions=[WatcherAction(type=ActionType.RESUBMIT, params={})],
            trigger_on_job_end=True,
            trigger_job_states=["completed", "failed", "timeout"],
        ),
    )

    persisted_variables = {}
    trigger_counts = []
    executed_actions = []

    monkeypatch.setattr(
        engine,
        "_update_watcher_variables",
        lambda watcher_id, variables: persisted_variables.update(variables),
    )
    monkeypatch.setattr(
        engine,
        "_get_watcher_variables",
        lambda watcher_id: dict(persisted_variables),
    )
    monkeypatch.setattr(
        engine,
        "_update_watcher_trigger_count",
        lambda watcher_id, count: trigger_counts.append((watcher_id, count)),
    )

    async def fake_execute_action(watcher_arg, action, matched_text, captured_vars):
        executed_actions.append((action.type.value, matched_text, dict(captured_vars)))
        return True, "ok"

    monkeypatch.setattr(engine, "_execute_action", fake_execute_action)

    matches_found = engine._check_patterns(
        watcher,
        "HYDRA_OUTPUT_DIR=/scratch/run-123\n",
    )
    assert matches_found is True
    assert persisted_variables["resume_run_dir"] == "/scratch/run-123"
    assert executed_actions == []

    triggered = await engine._handle_job_end_trigger(watcher, JobState.FAILED)
    assert triggered is True
    assert len(executed_actions) == 1
    assert executed_actions[0][0] == "resubmit"
    assert executed_actions[0][2]["resume_run_dir"] == "/scratch/run-123"
    assert executed_actions[0][2]["job_end_state"] == "failed"
    assert trigger_counts == [(1, 1)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_end_watcher_skips_cancelled_by_default(monkeypatch, test_cache):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=2,
        job_id="12346",
        hostname="cluster",
        definition=WatcherDefinition(
            name="notify",
            actions=[WatcherAction(type=ActionType.LOG_EVENT, params={})],
            trigger_on_job_end=True,
        ),
    )

    executed_actions = []

    monkeypatch.setattr(engine, "_get_watcher_variables", lambda watcher_id: {})
    monkeypatch.setattr(engine, "_update_watcher_trigger_count", lambda watcher_id, count: None)

    async def fake_execute_action(watcher_arg, action, matched_text, captured_vars):
        executed_actions.append((action.type.value, matched_text, dict(captured_vars)))
        return True, "ok"

    monkeypatch.setattr(engine, "_execute_action", fake_execute_action)

    triggered = await engine._handle_job_end_trigger(watcher, JobState.CANCELLED)
    assert triggered is False
    assert executed_actions == []
