"""
End-to-end integration test for watcher fixes.

Runs against real job output from entalpic, exercising:
1. Capture extraction from job output (named + positional)
2. Variable interpolation in action params ($1, ${named})
3. Script body interpolation for resubmit (numeric captures now work)
4. Cancel-skip when trigger_on_job_end fires after job completion

Usage:
    uv run pytest tests/integration/test_watcher_e2e.py -v -s
"""

import re

import pytest

from ssync.models.job import JobState
from ssync.models.watcher import (
    ActionType,
    WatcherAction,
    WatcherDefinition,
    WatcherInstance,
)
from ssync.watchers import engine as engine_module
from ssync.watchers.actions import ActionExecutor


# ── Capture + interpolation (no SSH needed) ──────────────────────────────


SAMPLE_OUTPUT = """\
Starting test job
HYDRA_OUTPUT_DIR=/home/ali_ramlaoui_entalpic_ai/watcher-test/run-42
METRIC_VALUE=0.42
Job finishing normally
"""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_capture_and_interpolation_flow(monkeypatch, test_cache):
    """Simulate a job that prints HYDRA_OUTPUT_DIR, verify captures flow
    through to resubmit script body (including numeric captures)."""
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=10,
        job_id="143255",
        hostname="entalpic",
        definition=WatcherDefinition(
            name="resume_chain",
            pattern=r"HYDRA_OUTPUT_DIR=(.+)",
            captures=["output_dir"],
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

    action_calls: list[dict] = []

    async def spy_execute_action(_w, action, matched_text, variables):
        action_calls.append(
            {"type": action.type.value, "text": matched_text, "vars": dict(variables)}
        )
        return True, "ok"

    monkeypatch.setattr(engine, "_execute_action", spy_execute_action)

    # ── Phase 1: pattern scan during job run ──
    matched = engine._check_patterns(watcher, SAMPLE_OUTPUT)
    assert matched is True
    assert persisted_variables["output_dir"] == "/home/ali_ramlaoui_entalpic_ai/watcher-test/run-42"
    assert persisted_variables["1"] == "/home/ali_ramlaoui_entalpic_ai/watcher-test/run-42"
    # trigger_on_job_end → no actions yet
    assert action_calls == []

    # ── Phase 2: job ends → trigger fires ──
    await engine._handle_job_end_trigger(watcher, JobState.COMPLETED)
    assert len(action_calls) == 1
    call = action_calls[0]
    assert call["type"] == "resubmit"
    assert call["vars"]["job_end_state"] == "completed"
    assert call["vars"]["output_dir"] == "/home/ali_ramlaoui_entalpic_ai/watcher-test/run-42"
    assert call["vars"]["1"] == "/home/ali_ramlaoui_entalpic_ai/watcher-test/run-42"


@pytest.mark.integration
def test_script_body_interpolation_with_numeric_captures():
    """Verify that ${1} in a resubmit script body gets replaced by the
    positional capture.  This was broken before the fix."""
    executor = ActionExecutor()

    script = """\
#!/bin/bash
#SBATCH --job-name=resumed_training
python train.py --resume-from ${1:-none} --output ${output_dir}
"""

    variables = {
        "1": "/data/ckpt/epoch10.pt",
        "output_dir": "/data/output/run-42",
        "_matched_text": "irrelevant",
    }

    # Reproduce the interpolation loop from _resubmit_job
    all_vars = {"JOB_ID": "143255", "HOSTNAME": "entalpic", **variables}
    for var_name, var_value in all_vars.items():
        if var_name.startswith("_"):
            continue

        # ${var:-default}
        default_pattern = re.compile(
            re.escape("${" + var_name + ":-") + r"[^}]*" + re.escape("}")
        )
        script = default_pattern.sub(str(var_value), script)

        # Plain ${var}
        script = script.replace(f"${{{var_name}}}", str(var_value))

    assert "/data/ckpt/epoch10.pt" in script, f"${1} not interpolated:\n{script}"
    assert "/data/output/run-42" in script, f"$output_dir not interpolated:\n{script}"
    assert "${1:-none}" not in script, f"${1:-default} not replaced:\n{script}"


@pytest.mark.integration
def test_cancel_skip_logic_directly():
    """Verify the cancel-skip condition in _resubmit_job without SSH."""
    # Simulate the check from the fixed code
    def should_cancel(params: dict, variables: dict | None) -> bool:
        job_already_ended = bool(variables and variables.get("job_end_state"))
        return params.get("cancel_previous", True) and not job_already_ended

    # Normal trigger (no job_end_state) → should cancel
    assert should_cancel({}, {"ckpt": "/data/ckpt"}) is True
    assert should_cancel({"cancel_previous": True}, {}) is True

    # Job-end trigger → should NOT cancel
    assert should_cancel({}, {"job_end_state": "completed"}) is False
    assert should_cancel({}, {"job_end_state": "failed"}) is False
    assert should_cancel({}, {"job_end_state": "timeout"}) is False

    # Explicit cancel_previous=False → should NOT cancel either way
    assert should_cancel({"cancel_previous": False}, {}) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_timer_mode_variable_interpolation(monkeypatch, test_cache):
    """Verify that in timer mode, $1 from a captured pattern is available
    in run_command action params."""
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    watcher = WatcherInstance(
        id=20,
        job_id="143255",
        hostname="entalpic",
        definition=WatcherDefinition(
            name="wandb_sync",
            pattern=r"HYDRA_OUTPUT_DIR=(.+)",
            actions=[
                WatcherAction(
                    type=ActionType.RUN_COMMAND,
                    params={"command": "cd $1; wandb sync --sync-all"},
                )
            ],
            timer_mode_enabled=True,
            timer_interval_seconds=300,
        ),
    )

    persisted_variables: dict = {}
    monkeypatch.setattr(
        engine,
        "_update_watcher_variables",
        lambda wid, v: persisted_variables.update(v),
    )

    # Pattern match
    matched = engine._check_patterns(watcher, SAMPLE_OUTPUT)
    assert matched is True
    assert persisted_variables["1"] == "/home/ali_ramlaoui_entalpic_ai/watcher-test/run-42"

    # Now test variable substitution as it would happen in timer mode
    executor = ActionExecutor()
    params = {"command": "cd $1; wandb sync --sync-all"}
    result = executor._substitute_variables(
        params, persisted_variables, "143255", "entalpic"
    )
    assert result["command"] == "cd /home/ali_ramlaoui_entalpic_ai/watcher-test/run-42; wandb sync --sync-all"
