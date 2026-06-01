"""Unit tests for status output formatting."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ssync.cli.cli import cli
from ssync.cli.commands import StatusCommand
from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


def _make_jobs() -> list[JobInfo]:
    return [
        JobInfo(
            job_id="4993854",
            name="train-model",
            state=JobState.RUNNING,
            hostname="adastra",
            partition="mi300-shared",
            runtime="00:07:07",
            submit_time="2026-05-24T06:00:00",
            stdout_file="/work/slurm-4993854.out",
            stderr_file="/work/slurm-4993854.err",
            work_dir="/work",
        ),
        JobInfo(
            job_id="4993857",
            name="queued-model",
            state=JobState.PENDING,
            hostname="adastra",
            partition="mi300-shared",
            runtime="00:00:00",
            reason="QOSGrpNodeLimit",
            submit_time="2026-05-24T06:01:00",
        ),
    ]


def _install_fake_api(monkeypatch, jobs: list[JobInfo]) -> dict:
    calls = {}

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            calls["config_path"] = config_path
            return True, None

        def get_jobs(self, **kwargs):
            calls["get_jobs"] = kwargs
            return jobs

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)
    return calls


@pytest.mark.unit
def test_status_defaults_to_compact_table(monkeypatch, tmp_path, capsys):
    jobs = _make_jobs()
    _install_fake_api(monkeypatch, jobs)
    command = StatusCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host("adastra")],
    )

    assert command.execute() is True

    output = capsys.readouterr().out
    assert output.startswith("JOB_ID")
    assert "STATE" in output
    assert "HOST" in output
    assert "PARTITION" in output
    assert "4993854" in output
    assert "adastra" in output
    assert "mi300-shared" in output
    assert "QOSGrpNodeLimit" in output
    assert "===" not in output
    assert "Submit Command" not in output


@pytest.mark.unit
def test_status_verbose_keeps_detailed_grouped_output(monkeypatch, tmp_path, capsys):
    _install_fake_api(monkeypatch, _make_jobs())
    command = StatusCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host("adastra")],
    )

    assert command.execute(output_format="verbose") is True

    output = capsys.readouterr().out
    assert "=== adastra ===" in output
    assert "Job 4993854: train-model" in output
    assert "  State: R" in output
    assert "  Output: /work/slurm-4993854.out" in output
    assert not output.lstrip().startswith("JOB_ID")


@pytest.mark.unit
def test_status_json_outputs_flat_job_records(monkeypatch, tmp_path, capsys):
    _install_fake_api(monkeypatch, _make_jobs())
    command = StatusCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host("adastra")],
    )

    assert command.execute(output_format="json") is True

    records = json.loads(capsys.readouterr().out)
    assert records == [
        {
            "job_id": "4993854",
            "state": "R",
            "name": "train-model",
            "host": "adastra",
            "partition": "mi300-shared",
            "runtime": "00:07:07",
            "reason": None,
            "submitted_at": "2026-05-24T06:00:00",
            "user": None,
            "stdout_file": "/work/slurm-4993854.out",
            "stderr_file": "/work/slurm-4993854.err",
            "work_dir": "/work",
        },
        {
            "job_id": "4993857",
            "state": "PD",
            "name": "queued-model",
            "host": "adastra",
            "partition": "mi300-shared",
            "runtime": "00:00:00",
            "reason": "QOSGrpNodeLimit",
            "submitted_at": "2026-05-24T06:01:00",
            "user": None,
            "stdout_file": None,
            "stderr_file": None,
            "work_dir": None,
        },
    ]


@pytest.mark.unit
def test_status_help_advertises_format_not_simple():
    result = CliRunner().invoke(cli, ["status", "--help"])

    assert result.exit_code == 0
    assert "--format" in result.output
    assert "table" in result.output
    assert "json" in result.output
    assert "verbose" in result.output
    assert "--cat-output" not in result.output
    assert "--simple" not in result.output
