"""Unit tests for SlurmQuery array-task accounting fallbacks."""

import pytest

from ssync.models.job import JobState
from ssync.slurm.query import SlurmQuery


class _FakeResult:
    def __init__(self, stdout="", ok=True, exited=0, stderr=""):
        self.stdout = stdout
        self.ok = ok
        self.exited = exited
        self.stderr = stderr


class _FakeConn:
    def __init__(self, command_results):
        self.command_results = command_results
        self.commands = []

    def run(self, command: str, **kwargs):
        self.commands.append(command)
        for match_text, result in self.command_results:
            if match_text in command:
                return result
        return _FakeResult(stdout="", ok=False, exited=1)


@pytest.mark.unit
def test_get_job_final_state_falls_back_to_array_query_for_task(monkeypatch):
    query = SlurmQuery()
    monkeypatch.setattr(
        query,
        "get_available_sacct_fields",
        lambda conn, hostname: ["JobID", "JobName", "State", "User"],
    )

    conn = _FakeConn(
        [
            ("--jobs=5001_0", _FakeResult(stdout="", ok=True)),
            (
                "--jobs=5001 --array",
                _FakeResult(
                    stdout=(
                        "5001_[0-1]|array-job|COMPLETED|testuser\n"
                        "5001_0|array-job|FAILED|testuser\n"
                        "5001_1|array-job|COMPLETED|testuser"
                    )
                ),
            ),
        ]
    )

    job = query.get_job_final_state(conn, "cluster.example.com", "5001_0")

    assert job is not None
    assert job.job_id == "5001_0"
    assert job.state == JobState.FAILED
    assert any("--jobs=5001 --array" in command for command in conn.commands)


@pytest.mark.unit
def test_get_job_final_state_builds_clean_array_parent_from_task_rows(monkeypatch):
    query = SlurmQuery()
    monkeypatch.setattr(
        query,
        "get_available_sacct_fields",
        lambda conn, hostname: [
            "JobID",
            "JobName",
            "State",
            "User",
            "Partition",
            "AllocNodes",
            "AllocCPUS",
            "ReqMem",
            "Timelimit",
            "Elapsed",
            "Submit",
            "SubmitLine",
            "Start",
            "End",
            "WorkDir",
            "StdOut",
            "StdErr",
            "NodeList",
        ],
    )

    conn = _FakeConn(
        [
            (
                "--jobs=7001",
                _FakeResult(
                    stdout=(
                        "7001_0|array-job|FAILED|testuser|gpu|1|8|64G|1-00:00:00|00:17:41|"
                        "2026-03-27T03:31:28|sbatch array.sh|2026-03-27T04:41:30|"
                        "2026-03-27T04:59:11|/workdir|/workdir/slurm-7001_0.out|"
                        "/workdir/slurm-7001_0.err|node001\n"
                        "7001_1|array-job|COMPLETED|testuser|gpu|1|8|64G|1-00:00:00|00:10:00|"
                        "2026-03-27T03:31:28|sbatch array.sh|2026-03-27T05:00:00|"
                        "2026-03-27T05:10:00|/workdir|/workdir/slurm-7001_1.out|"
                        "/workdir/slurm-7001_1.err|node001"
                    )
                ),
            ),
        ]
    )

    job = query.get_job_final_state(conn, "cluster.example.com", "7001_[0-1]")

    assert job is not None
    assert job.job_id == "7001_[0-1]"
    assert job.array_job_id == "7001"
    assert job.array_task_id == "[0-1]"
    assert job.state == JobState.FAILED
    assert job.name == "array-job"
    assert job.user == "testuser"
    assert job.partition == "gpu"
    assert job.stdout_file is None
    assert job.stderr_file is None
    assert job.start_time is None
    assert job.end_time is None
    assert job.runtime is None
    assert job.node_list is None


@pytest.mark.unit
def test_get_job_details_uses_array_query_to_match_specific_task(monkeypatch):
    query = SlurmQuery()
    monkeypatch.setattr(query, "get_username", lambda conn, hostname=None: "testuser")
    monkeypatch.setattr(
        query,
        "get_available_sacct_fields",
        lambda conn, hostname: ["JobID", "JobName", "State", "User"],
    )
    monkeypatch.setattr(
        query.output,
        "get_job_output_files",
        lambda conn, job_id, hostname: (None, None),
    )

    conn = _FakeConn(
        [
            ("squeue -r --user testuser -j 6001_0", _FakeResult(stdout="", ok=True)),
            ("--jobs=6001_0", _FakeResult(stdout="", ok=True)),
            (
                "--jobs=6001 --array",
                _FakeResult(
                    stdout=(
                        "6001_[0-1]|array-job|COMPLETED|testuser\n"
                        "6001_0|array-job|FAILED|testuser\n"
                        "6001_1|array-job|COMPLETED|testuser"
                    )
                ),
            ),
        ]
    )

    job = query.get_job_details(conn, "6001_0", "cluster.example.com")

    assert job is not None
    assert job.job_id == "6001_0"
    assert job.state == JobState.FAILED
    assert any("--jobs=6001 --array" in command for command in conn.commands)
