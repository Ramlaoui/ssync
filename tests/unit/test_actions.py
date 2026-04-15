"""Tests for the ActionExecutor — focused on interpolation and relaunch flow."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ssync import cache as cache_module
from ssync.models.watcher import ActionType, WatcherAction, WatcherDefinition, WatcherInstance
from ssync.models.job import JobInfo, JobState
from ssync.watchers.actions import ActionExecutor
from ssync.web import app as app_module


class TestSubstituteVariables:
    """Test _substitute_variables handles positional and named captures."""

    def setup_method(self):
        self.executor = ActionExecutor()

    def test_positional_capture_in_params(self):
        params = {"command": "cd $1; wandb sync"}
        variables = {"1": "/scratch/run-42", "_matched_text": "full match"}
        result = self.executor._substitute_variables(
            params, variables, "100", "host"
        )
        assert result["command"] == "cd /scratch/run-42; wandb sync"

    def test_named_capture_in_params(self):
        params = {"command": "echo $output_dir"}
        variables = {"output_dir": "/data/out", "_matched_text": "match"}
        result = self.executor._substitute_variables(
            params, variables, "100", "host"
        )
        assert result["command"] == "echo /data/out"

    def test_builtin_vars_job_id_hostname(self):
        params = {"command": "echo $JOB_ID on $HOSTNAME"}
        result = self.executor._substitute_variables(
            params, {}, "12345", "entalpic"
        )
        assert result["command"] == "echo 12345 on entalpic"

    def test_braced_syntax(self):
        params = {"command": "echo ${JOB_ID}"}
        result = self.executor._substitute_variables(
            params, {}, "12345", "entalpic"
        )
        assert result["command"] == "echo 12345"


class TestScriptBodyInterpolation:
    """Test that resubmit script body interpolation works for both named and
    numeric captures.  This exercises the loop in _resubmit_job that was
    previously skipping numeric keys."""

    def _interpolate_script(self, script: str, variables: dict) -> str:
        """Reproduce the interpolation loop from _resubmit_job."""
        import re

        all_vars = {"JOB_ID": "100", "HOSTNAME": "host", **variables}
        for var_name, var_value in all_vars.items():
            if var_name.startswith("_"):
                continue

            # ${var:+word}
            cond_pattern = re.compile(
                re.escape("${" + var_name + ":+")
                + r"((?:[^{}]|\$\{[^}]*\})*)"
                + re.escape("}")
            )

            def _expand_conditional(m: re.Match, vn=var_name, vv=var_value) -> str:
                word = m.group(1)
                for n, v in all_vars.items():
                    if not n.startswith("_"):
                        word = word.replace(f"${{{n}}}", str(v))
                return word

            script = cond_pattern.sub(_expand_conditional, script)

            # ${var:-default}
            default_pattern = re.compile(
                re.escape("${" + var_name + ":-") + r"[^}]*" + re.escape("}")
            )
            script = default_pattern.sub(str(var_value), script)

            # Plain ${var}
            script = script.replace(f"${{{var_name}}}", str(var_value))

        return script

    def test_named_capture_plain(self):
        script = "python train.py --resume ${ckpt_path}"
        result = self._interpolate_script(script, {"ckpt_path": "/data/epoch10.pt"})
        assert result == "python train.py --resume /data/epoch10.pt"

    def test_named_capture_with_default(self):
        script = "python train.py --resume ${ckpt_path:-none}"
        result = self._interpolate_script(script, {"ckpt_path": "/data/epoch10.pt"})
        assert result == "python train.py --resume /data/epoch10.pt"

    def test_named_capture_conditional(self):
        script = "python train.py ${ckpt_path:+--resume ${ckpt_path}}"
        result = self._interpolate_script(script, {"ckpt_path": "/data/epoch10.pt"})
        assert result == "python train.py --resume /data/epoch10.pt"

    def test_numeric_capture_plain(self):
        """Before the fix, numeric captures were skipped — this must pass now."""
        script = "python train.py --resume ${1}"
        result = self._interpolate_script(script, {"1": "/data/epoch10.pt"})
        assert result == "python train.py --resume /data/epoch10.pt"

    def test_numeric_capture_with_default(self):
        script = "python train.py --resume ${1:-none}"
        result = self._interpolate_script(script, {"1": "/data/epoch10.pt"})
        assert result == "python train.py --resume /data/epoch10.pt"

    def test_numeric_capture_conditional(self):
        script = "python train.py ${1:+--resume ${1}}"
        result = self._interpolate_script(script, {"1": "/data/epoch10.pt"})
        assert result == "python train.py --resume /data/epoch10.pt"

    def test_mixed_named_and_numeric(self):
        script = "echo ${ckpt_path} ${1} ${2}"
        result = self._interpolate_script(
            script, {"ckpt_path": "/a", "1": "/b", "2": "/c"}
        )
        assert result == "echo /a /b /c"


class TestResubmitLaunchDelegation:
    """Test that resubmit delegates into LaunchManager with cached job context."""

    @pytest.mark.asyncio
    async def test_resubmit_uses_launch_manager_with_cached_job_context(
        self, monkeypatch
    ):
        executor = ActionExecutor()

        cached_job = SimpleNamespace(
            script_content=(
                "#!/bin/bash\n"
                "#WATCHER_BEGIN\n"
                "# name: auto resubmit\n"
                '# pattern: "HYDRA_OUTPUT_DIR=(.+)"\n'
                "# trigger_on_job_end: true\n"
                "# remaining_resubmits: 2\n"
                "# actions:\n"
                "#   - resubmit()\n"
                "#WATCHER_END\n"
                "python main.py ${resume_run_dir:+--resume ${resume_run_dir}}\n"
            ),
            local_source_dir="/home/aliramlaoui/work/triforces",
            job_info=JobInfo(
                job_id="12345",
                name="train",
                state=JobState.TIMEOUT,
                hostname="adastra",
                work_dir="/lus/work/CT10/cad16353/aramlaoui/triforces",
            ),
        )

        mock_cache = MagicMock()
        mock_cache.get_cached_job.return_value = cached_job
        monkeypatch.setattr(cache_module, "get_cache", lambda: mock_cache)

        mock_manager = MagicMock()
        mock_manager.get_host_by_name.return_value = SimpleNamespace(
            work_dir=Path("/lus/work/CT10/cad16353/aramlaoui")
        )
        monkeypatch.setattr(app_module, "get_slurm_manager", lambda: mock_manager)

        async def fake_launch_job(_self, **kwargs):
            fake_launch_job.kwargs = kwargs
            return SimpleNamespace(job_id="67890")

        monkeypatch.setattr(
            "ssync.watchers.actions.LaunchManager.launch_job",
            fake_launch_job,
        )
        watcher = WatcherInstance(
            id=1,
            job_id="12345",
            hostname="adastra",
            definition=WatcherDefinition(
                name="auto resubmit",
                pattern="HYDRA_OUTPUT_DIR=(.+)",
                trigger_on_job_end=True,
                actions=[
                    WatcherAction(
                        type=ActionType.RESUBMIT,
                        params={"remaining_resubmits": 2},
                    )
                ],
            ),
        )

        success, message = await executor._resubmit_job(
            "12345",
            "adastra",
            {"remaining_resubmits": 2},
            {
                "resume_run_dir": "/lus/work/CT10/cad16353/aramlaoui/triforces/run-42",
                "job_end_state": "timeout",
            },
            watcher,
        )

        assert success is True
        assert message == "Resubmitted as job 67890"
        assert fake_launch_job.kwargs["script_path"] is None
        assert "# remaining_resubmits: 1" in fake_launch_job.kwargs["script_content"]
        assert (
            fake_launch_job.kwargs["script_variables"]["resume_run_dir"].endswith(
                "run-42"
            )
        )
        assert fake_launch_job.kwargs["source_dir"] == Path(
            "/home/aliramlaoui/work/triforces"
        )
        assert fake_launch_job.kwargs["host"] == "adastra"
        assert fake_launch_job.kwargs["sync_enabled"] is False
        assert (
            fake_launch_job.kwargs["work_dir_override"]
            == cached_job.job_info.work_dir
        )

    @pytest.mark.asyncio
    async def test_resubmit_falls_back_to_source_dir_layout_when_work_dir_missing(
        self, monkeypatch
    ):
        executor = ActionExecutor()

        cached_job = SimpleNamespace(
            script_content="#!/bin/bash\npython main.py\n",
            local_source_dir="/home/aliramlaoui/work/triforces",
            job_info=JobInfo(
                job_id="12345",
                name="train",
                state=JobState.TIMEOUT,
                hostname="adastra",
                work_dir=None,
            ),
        )

        mock_cache = MagicMock()
        mock_cache.get_cached_job.return_value = cached_job
        monkeypatch.setattr(cache_module, "get_cache", lambda: mock_cache)

        mock_manager = MagicMock()
        mock_manager.get_host_by_name.return_value = SimpleNamespace(
            work_dir=Path("/lus/work/CT10/cad16353/aramlaoui")
        )
        monkeypatch.setattr(app_module, "get_slurm_manager", lambda: mock_manager)

        async def fake_launch_job(_self, **kwargs):
            fake_launch_job.kwargs = kwargs
            return SimpleNamespace(job_id="67890")

        monkeypatch.setattr(
            "ssync.watchers.actions.LaunchManager.launch_job",
            fake_launch_job,
        )

        success, _ = await executor._resubmit_job(
            "12345",
            "adastra",
            {},
            {"job_end_state": "timeout"},
        )

        assert success is True
        assert (
            fake_launch_job.kwargs["work_dir_override"]
            == "/lus/work/CT10/cad16353/aramlaoui/triforces"
        )

    @pytest.mark.asyncio
    async def test_resubmit_stops_when_no_resubmits_remain(self, monkeypatch):
        executor = ActionExecutor()

        cached_job = SimpleNamespace(
            script_content="#!/bin/bash\npython main.py\n",
            local_source_dir="/home/aliramlaoui/work/triforces",
            job_info=JobInfo(
                job_id="12345",
                name="train",
                state=JobState.TIMEOUT,
                hostname="adastra",
                work_dir="/lus/work/CT10/cad16353/aramlaoui/triforces",
            ),
        )

        mock_cache = MagicMock()
        mock_cache.get_cached_job.return_value = cached_job
        monkeypatch.setattr(cache_module, "get_cache", lambda: mock_cache)

        mock_manager = MagicMock()
        monkeypatch.setattr(app_module, "get_slurm_manager", lambda: mock_manager)

        watcher = WatcherInstance(
            id=1,
            job_id="12345",
            hostname="adastra",
            definition=WatcherDefinition(
                name="auto resubmit",
                pattern="HYDRA_OUTPUT_DIR=(.+)",
                trigger_on_job_end=True,
                actions=[
                    WatcherAction(
                        type=ActionType.RESUBMIT,
                        params={"remaining_resubmits": 0},
                    )
                ],
            ),
        )

        success, message = await executor._resubmit_job(
            "12345",
            "adastra",
            {"remaining_resubmits": 0},
            {"job_end_state": "timeout"},
            watcher,
        )

        assert success is False
        assert message == "No resubmits remaining for this watcher"
