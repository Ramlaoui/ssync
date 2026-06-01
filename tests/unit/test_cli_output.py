"""Unit tests for the output CLI command."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from ssync.cli.cli import cli
from ssync.cli.commands import OutputCommand
from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


@pytest.mark.unit
def test_output_prints_stdout_and_auto_detects_host(monkeypatch, tmp_path, capsys):
    hostname = "entalpic"
    slurm_host = _make_slurm_host(hostname)
    calls = {}

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_jobs(self, job_ids=None, **kwargs):
            assert job_ids == ["1234"]
            return [
                JobInfo(
                    job_id="1234",
                    name="demo-job",
                    state=JobState.COMPLETED,
                    hostname=hostname,
                )
            ]

        def get_job_output(self, **kwargs):
            calls["get_job_output"] = kwargs
            return {
                "stdout": "stdout-data\n",
                "stdout_metadata": {"exists": True},
            }

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = OutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[slurm_host],
        verbose=False,
    )

    assert command.execute(job_id="1234") is True

    captured = capsys.readouterr()
    assert captured.out == "stdout-data\n"
    assert captured.err == ""
    assert calls["get_job_output"] == {
        "job_id": "1234",
        "host": hostname,
        "output_type": "stdout",
        "lines": None,
        "max_bytes": None,
        "full_output": False,
        "force_refresh": False,
    }


@pytest.mark.unit
def test_output_prints_requested_stderr_with_query_options(
    monkeypatch, tmp_path, capsys
):
    hostname = "entalpic"
    calls = {}

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_jobs(self, **kwargs):
            raise AssertionError("host auto-detection should not run")

        def get_job_output(self, **kwargs):
            calls["get_job_output"] = kwargs
            return {
                "stderr": "stderr-data",
                "stderr_metadata": {"exists": True},
                "content_truncated": True,
                "content_limit_bytes": 2048,
                "refresh_queued": True,
            }

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = OutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host(hostname)],
        verbose=False,
    )

    assert (
        command.execute(
            job_id="1234",
            host=hostname,
            output_type="stderr",
            lines=5,
            max_bytes=2048,
            force_refresh=True,
        )
        is True
    )

    captured = capsys.readouterr()
    assert captured.out == "stderr-data"
    assert "Output truncated to 2048 bytes" in captured.err
    assert "Output refresh queued" in captured.err
    assert calls["get_job_output"] == {
        "job_id": "1234",
        "host": hostname,
        "output_type": "stderr",
        "lines": 5,
        "max_bytes": 2048,
        "full_output": False,
        "force_refresh": True,
    }


@pytest.mark.unit
def test_output_both_labels_streams_and_warns_for_missing_output(
    monkeypatch, tmp_path, capsys
):
    hostname = "entalpic"

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_job_output(self, **kwargs):
            return {
                "stdout": "stdout-data\n",
                "stdout_metadata": {"exists": True},
                "stderr": None,
                "stderr_metadata": {"exists": False},
            }

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = OutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host(hostname)],
        verbose=False,
    )

    assert (
        command.execute(
            job_id="1234",
            host=hostname,
            output_type="both",
        )
        is True
    )

    captured = capsys.readouterr()
    assert captured.out == "== stdout ==\nstdout-data\n"
    assert "Skipped unavailable output(s) for job 1234: stderr" in captured.err


@pytest.mark.unit
def test_output_fails_when_requested_output_is_unavailable(
    monkeypatch, tmp_path, capsys
):
    hostname = "entalpic"

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_job_output(self, **kwargs):
            return {
                "stdout": None,
                "stdout_metadata": {"exists": False},
            }

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = OutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host(hostname)],
        verbose=False,
    )

    assert command.execute(job_id="1234", host=hostname) is False

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No stdout output available for job 1234 on entalpic" in captured.err


@pytest.mark.unit
def test_output_help_advertises_terminal_output_command():
    result = CliRunner().invoke(cli, ["output", "--help"])

    assert result.exit_code == 0
    assert "Print a Slurm job output file" in result.output
    assert "--stderr" in result.output
    assert "--both" in result.output
    assert "--all" in result.output


@pytest.mark.unit
def test_output_all_requests_full_output(monkeypatch, tmp_path, capsys):
    hostname = "entalpic"
    calls = {}

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_job_output(self, **kwargs):
            calls["get_job_output"] = kwargs
            return {
                "stdout": "full-stdout",
                "stdout_metadata": {"exists": True},
            }

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = OutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[_make_slurm_host(hostname)],
        verbose=False,
    )

    assert command.execute(job_id="1234", host=hostname, full_output=True) is True

    captured = capsys.readouterr()
    assert captured.out == "full-stdout"
    assert calls["get_job_output"] == {
        "job_id": "1234",
        "host": hostname,
        "output_type": "stdout",
        "lines": None,
        "max_bytes": None,
        "full_output": True,
        "force_refresh": False,
    }


@pytest.mark.unit
def test_output_all_rejects_bounded_options():
    runner = CliRunner()

    lines_result = runner.invoke(cli, ["output", "1234", "--all", "--lines", "200"])
    assert lines_result.exit_code == 1
    assert "Cannot use --all and --lines together" in lines_result.output

    bytes_result = runner.invoke(
        cli, ["output", "1234", "--all", "--max-bytes", "2048"]
    )
    assert bytes_result.exit_code == 1
    assert "Cannot use --all and --max-bytes together" in bytes_result.output
