import pytest

from ssync.models.job import JobState
from ssync.models.watcher import (
    ActionType,
    WatcherAction,
    WatcherDefinition,
    WatcherInstance,
    WatcherState,
)
from ssync.watchers import engine as engine_module
from ssync.watchers.engine import JobEndHandlingResult


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

    async def fake_execute_action(_watcher_arg, action, matched_text, captured_vars):
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
    assert triggered == JobEndHandlingResult.COMPLETE
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
    monkeypatch.setattr(
        engine, "_update_watcher_trigger_count", lambda watcher_id, count: None
    )

    async def fake_execute_action(_watcher_arg, action, matched_text, captured_vars):
        executed_actions.append((action.type.value, matched_text, dict(captured_vars)))
        return True, "ok"

    monkeypatch.setattr(engine, "_execute_action", fake_execute_action)

    triggered = await engine._handle_job_end_trigger(watcher, JobState.CANCELLED)
    assert triggered == JobEndHandlingResult.COMPLETE
    assert executed_actions == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_end_resubmit_passes_job_end_state_to_action(
    monkeypatch, test_cache
):
    """Verify that _handle_job_end_trigger injects 'job_end_state' into the
    variables dict passed to _execute_action.  The action executor uses this
    signal to skip cancelling an already-terminal job."""
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=3,
        job_id="99999",
        hostname="cluster",
        definition=WatcherDefinition(
            name="resubmit_on_end",
            pattern=r"CKPT=(.+)",
            captures=["ckpt_path"],
            actions=[WatcherAction(type=ActionType.RESUBMIT, params={})],
            trigger_on_job_end=True,
            trigger_job_states=["completed", "failed", "timeout"],
        ),
    )

    persisted_variables: dict = {}
    monkeypatch.setattr(
        engine,
        "_update_watcher_variables",
        lambda wid, v: persisted_variables.update(v),
    )
    monkeypatch.setattr(
        engine, "_get_watcher_variables", lambda wid: dict(persisted_variables)
    )
    monkeypatch.setattr(
        engine, "_update_watcher_trigger_count", lambda wid, c: None
    )

    captured_action_vars: list[dict] = []

    async def spy_execute_action(_w, action, matched_text, variables):
        captured_action_vars.append(dict(variables))
        return True, "ok"

    monkeypatch.setattr(engine, "_execute_action", spy_execute_action)

    # Simulate a pattern match during the run
    engine._check_patterns(watcher, "CKPT=/data/epoch10.pt\n")
    assert persisted_variables["ckpt_path"] == "/data/epoch10.pt"

    # Trigger the job-end handler
    await engine._handle_job_end_trigger(watcher, JobState.COMPLETED)

    assert len(captured_action_vars) == 1
    assert captured_action_vars[0]["job_end_state"] == "completed"
    assert captured_action_vars[0]["ckpt_path"] == "/data/epoch10.pt"


@pytest.mark.unit
def test_placeholder_capture_does_not_overwrite_valid_value(monkeypatch, test_cache):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=4,
        job_id="10000",
        hostname="cluster",
        definition=WatcherDefinition(
            name="resume",
            pattern=r"HYDRA_OUTPUT_DIR=(.+)",
            captures=["resume_run_dir"],
            actions=[WatcherAction(type=ActionType.RESUBMIT, params={})],
            trigger_on_job_end=True,
        ),
    )
    watcher.variables["resume_run_dir"] = "/scratch/run-123"

    persisted_variables = {}
    monkeypatch.setattr(
        engine,
        "_update_watcher_variables",
        lambda watcher_id, variables: persisted_variables.update(variables),
    )

    engine._check_patterns(watcher, 'HYDRA_OUTPUT_DIR=(.+)"\n')

    assert watcher.variables["resume_run_dir"] == "/scratch/run-123"
    assert persisted_variables == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_end_resubmit_retries_until_success(monkeypatch, test_cache):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=5,
        job_id="10001",
        hostname="cluster",
        definition=WatcherDefinition(
            name="resume",
            actions=[
                WatcherAction(type=ActionType.LOG_EVENT, params={}),
                WatcherAction(type=ActionType.RESUBMIT, params={}),
            ],
            trigger_on_job_end=True,
        ),
    )

    persisted_variables = {}
    trigger_counts = []
    monkeypatch.setattr(
        engine,
        "_update_watcher_variables",
        lambda watcher_id, variables: persisted_variables.update(variables),
    )
    monkeypatch.setattr(
        engine, "_get_watcher_variables", lambda watcher_id: dict(persisted_variables)
    )
    monkeypatch.setattr(
        engine,
        "_update_watcher_trigger_count",
        lambda watcher_id, count: trigger_counts.append((watcher_id, count)),
    )

    executed = []
    resubmit_results = iter(
        [
            (False, "Failed to submit job to cluster"),
            (True, "Resubmitted as job 10002"),
        ]
    )

    async def fake_execute_action(_watcher_arg, action, matched_text, captured_vars):
        executed.append((action.type.value, matched_text, dict(captured_vars)))
        if action.type == ActionType.LOG_EVENT:
            return True, "logged"
        return next(resubmit_results)

    monkeypatch.setattr(engine, "_execute_action", fake_execute_action)

    first = await engine._handle_job_end_trigger(watcher, JobState.TIMEOUT)
    second = await engine._handle_job_end_trigger(watcher, JobState.TIMEOUT)

    assert first == JobEndHandlingResult.RETRY_PENDING
    assert second == JobEndHandlingResult.COMPLETE
    assert [call[0] for call in executed] == ["log_event", "resubmit", "resubmit"]
    assert trigger_counts == [(5, 1)]
    assert persisted_variables["__ssync_job_end_action_success_0"] == "1"
    assert persisted_variables["__ssync_job_end_action_success_1"] == "1"
    assert persisted_variables["__ssync_job_end_completed"] == "1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_monitor_watcher_retries_terminal_resubmit_until_success(
    monkeypatch, test_cache
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher_state = {"value": WatcherState.ACTIVE}
    watcher = WatcherInstance(
        id=6,
        job_id="10002",
        hostname="cluster",
        definition=WatcherDefinition(
            name="resume",
            interval_seconds=7,
            actions=[WatcherAction(type=ActionType.RESUBMIT, params={})],
            trigger_on_job_end=True,
        ),
        state=WatcherState.ACTIVE,
    )
    job_info = engine_module.JobInfo(
        job_id="10002",
        name="train",
        state=JobState.TIMEOUT,
        hostname="cluster",
    )

    def fake_get_watcher(_watcher_id):
        watcher.state = watcher_state["value"]
        return watcher

    async def fake_get_job_info(_job_id, _hostname):
        return job_info

    retry_results = iter(
        [
            JobEndHandlingResult.RETRY_PENDING,
            JobEndHandlingResult.COMPLETE,
        ]
    )

    async def fake_handle_job_end(_watcher, _state):
        return next(retry_results)

    async def fake_get_new_output(*_args, **_kwargs):
        return None

    sleeps = []
    completed_states = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    def fake_update_state(_watcher_id, state):
        completed_states.append(state)
        watcher_state["value"] = state

    monkeypatch.setattr(engine, "_get_watcher", fake_get_watcher)
    monkeypatch.setattr(engine, "_get_job_info", fake_get_job_info)
    monkeypatch.setattr(engine, "_get_new_output", fake_get_new_output)
    monkeypatch.setattr(engine, "_handle_job_end_trigger", fake_handle_job_end)
    monkeypatch.setattr(engine, "_update_watcher_last_check", lambda watcher_id: None)
    monkeypatch.setattr(engine, "_update_watcher_state", fake_update_state)
    monkeypatch.setattr(engine_module.asyncio, "sleep", fake_sleep)

    await engine._monitor_watcher(watcher.id, watcher.job_id, watcher.hostname)

    assert sleeps == [5, 7]
    assert completed_states == [WatcherState.COMPLETED]
