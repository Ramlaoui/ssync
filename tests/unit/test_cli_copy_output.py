"""Unit tests for the copy-output CLI command."""

from pathlib import Path

import pytest

from ssync.cli.commands import CopyOutputCommand
from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


@pytest.mark.unit
def test_copy_output_writes_available_files_and_auto_detects_host(
    monkeypatch, tmp_path
):
    hostname = "entalpic"
    slurm_host = _make_slurm_host(hostname)

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

        def get_job_output(self, job_id, host, metadata_only=False, force_refresh=False):
            assert job_id == "1234"
            assert host == hostname
            assert metadata_only is True
            assert force_refresh is False
            return {
                "stdout_metadata": {"exists": True},
                "stderr_metadata": {"exists": True},
            }

        def download_job_output(
            self, job_id, host, output_type="stdout", compressed=False, timeout=60
        ):
            assert job_id == "1234"
            assert host == hostname
            assert compressed is False
            return f"job_1234_{output_type}.log", f"{output_type}-data".encode()

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = CopyOutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[slurm_host],
        verbose=False,
    )

    destination = tmp_path / "outputs"
    assert command.execute(job_id="1234", destination=destination) is True

    assert (destination / "job_1234_stdout.log").read_text() == "stdout-data"
    assert (destination / "job_1234_stderr.log").read_text() == "stderr-data"


@pytest.mark.unit
def test_copy_output_refuses_to_overwrite_existing_files(monkeypatch, tmp_path, capsys):
    hostname = "entalpic"
    slurm_host = _make_slurm_host(hostname)

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_job_output(self, job_id, host, metadata_only=False, force_refresh=False):
            return {"stdout_metadata": {"exists": True}, "stderr_metadata": None}

        def download_job_output(
            self, job_id, host, output_type="stdout", compressed=False, timeout=60
        ):
            return "job_1234_stdout.log", b"new-stdout"

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    destination = tmp_path / "outputs"
    destination.mkdir()
    existing_path = destination / "job_1234_stdout.log"
    existing_path.write_text("existing-stdout")

    command = CopyOutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[slurm_host],
        verbose=False,
    )

    assert (
        command.execute(
            job_id="1234",
            host=hostname,
            destination=destination,
            output_type="stdout",
        )
        is False
    )

    captured = capsys.readouterr()
    assert "Refusing to overwrite existing output file(s)" in captured.err
    assert existing_path.read_text() == "existing-stdout"


@pytest.mark.unit
def test_copy_output_fails_when_requested_output_is_unavailable(
    monkeypatch, tmp_path, capsys
):
    hostname = "entalpic"
    slurm_host = _make_slurm_host(hostname)

    class _FakeAPIClient:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_job_output(self, job_id, host, metadata_only=False, force_refresh=False):
            return {
                "stdout_metadata": {"exists": False},
                "stderr_metadata": {"exists": False},
            }

    monkeypatch.setattr("ssync.cli.commands.APIClient", _FakeAPIClient)

    command = CopyOutputCommand(
        config_path=tmp_path / "config.yaml",
        slurm_hosts=[slurm_host],
        verbose=False,
    )

    assert (
        command.execute(
            job_id="1234",
            host=hostname,
            destination=tmp_path / "outputs",
            output_type="stderr",
        )
        is False
    )

    captured = capsys.readouterr()
    assert "No stderr output available for job 1234 on entalpic" in captured.err
