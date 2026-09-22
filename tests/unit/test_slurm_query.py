"""Unit tests for SlurmQuery array-task accounting fallbacks."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
def test_concurrent_username_lookups_are_coalesced():
    query = SlurmQuery()
    started = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    call_count = 0

    class ConcurrentConn:
        user = None

        def run(self, command: str, **kwargs):
            nonlocal call_count
            with state_lock:
                call_count += 1
            started.set()
            release.wait(timeout=2)
            return _FakeResult(stdout="testuser\n")

    conn = ConcurrentConn()
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [
            pool.submit(query.get_username, conn, hostname="cluster.example.com")
            for _ in range(16)
        ]
        assert started.wait(timeout=1)
        time.sleep(0.05)
        release.set()
        usernames = [future.result(timeout=2) for future in futures]

    assert usernames == ["testuser"] * 16
    assert call_count == 1


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


@pytest.mark.unit
def test_get_active_jobs_uses_scontrol_paths_instead_of_squeue_command_field(caplog):
    query = SlurmQuery()

    conn = _FakeConn(
        [
            (
                "squeue -r --format=",
                _FakeResult(
                    stdout=(
                        "139439|clean_tmp|RUNNING|ujv38uq|gpu|1|4|8G|01:00:00|00:15:30||"
                        "/workdir|/workdir/scripts/clean_tmp8849d6wa.slurm|2099-01-01T00:00:00|"
                        "2026-04-23T16:34:47|2026-04-23T16:34:48|default|normal|1000|node001"
                    )
                ),
            ),
            (
                "scontrol show job 139439",
                _FakeResult(
                    stdout=(
                        "JobId=139439 StdOut=/workdir/logs/%x-%j.out "
                        "StdErr=/workdir/logs/%x-%j.err "
                        "Command=/workdir/scripts/clean_tmp8849d6wa.slurm"
                    )
                ),
            ),
        ]
    )

    jobs = query.get_active_jobs(conn, "cluster.example.com", user="ujv38uq")

    assert len(jobs) == 1
    assert jobs[0].stdout_file == "/workdir/logs/clean_tmp-139439.out"
    assert jobs[0].stderr_file == "/workdir/logs/clean_tmp-139439.err"
    assert "suspicious stdout path" not in caplog.text


def _active_squeue_line(
    job_id: str,
    *,
    partition: str,
    qos: str,
    priority: str,
) -> str:
    return "|".join(
        [
            job_id,
            f"job-{job_id}",
            "PENDING",
            "testuser",
            partition,
            "1",
            "4",
            "8G",
            "01:00:00",
            "0:00",
            "Priority",
            "/workdir",
            "/workdir/job.sh",
            "N/A",
            "2026-09-18T12:00:00",
            "N/A",
            "project",
            qos,
            priority,
            "Priority",
        ]
    )


@pytest.mark.unit
def test_get_active_jobs_adds_cached_partition_scoped_priority_positions():
    query = SlurmQuery()
    conn = _FakeConn(
        [
            (
                "squeue -r --format=",
                _FakeResult(
                    stdout="\n".join(
                        [
                            _active_squeue_line(
                                "200", partition="gpu", qos="normal", priority="900"
                            ),
                            _active_squeue_line(
                                "201", partition="cpu", qos="high", priority="1000"
                            ),
                        ]
                    )
                ),
            ),
            (
                "squeue --local --all --states=PENDING",
                _FakeResult(
                    stdout=(
                        "100|gpu|1200\n"
                        "300|cpu|2000\n"
                        "200|gpu|900\n"
                        "101|gpu|800\n"
                        "201|cpu|1000"
                    )
                ),
            ),
        ]
    )

    jobs = query.get_active_jobs(conn, "cluster.example.com", user="testuser")
    query.get_active_jobs(conn, "cluster.example.com", user="testuser")

    gpu_job, cpu_job = jobs
    assert gpu_job.priority == "900"
    assert gpu_job.priority_rank == 2
    assert gpu_job.priority_jobs_ahead == 1
    assert gpu_job.priority_queue_size == 3
    assert gpu_job.priority_percentile == 50.0
    assert gpu_job.priority_scope == "visible_pending_records:partition=gpu"

    assert cpu_job.priority_rank == 2
    assert cpu_job.priority_jobs_ahead == 1
    assert cpu_job.priority_queue_size == 2
    assert cpu_job.priority_percentile == 0.0
    assert (
        sum(
            command.startswith("squeue --local --all --states=PENDING")
            for command in conn.commands
        )
        == 1
    )


@pytest.mark.unit
def test_priority_positions_match_compact_array_records():
    query = SlurmQuery()
    job = query.parser.from_squeue_fields(
        _active_squeue_line(
            "500_4", partition="gpu", qos="normal", priority="700"
        ).split("|"),
        "cluster.example.com",
    )

    query._annotate_priority_positions(
        [job],
        {"gpu": [("400", "900"), ("500_[4-9]", "700")]},
        0.0,
    )

    assert job.priority_rank == 2
    assert job.priority_jobs_ahead == 1
    assert job.priority_queue_size == 2
    assert job.priority_percentile == 0.0
    assert job.priority_snapshot_at == "1970-01-01T00:00:00+00:00"


@pytest.mark.unit
def test_failed_priority_snapshot_is_negative_cached():
    query = SlurmQuery()
    conn = _FakeConn(
        [
            (
                "squeue --local --all --states=PENDING",
                _FakeResult(stdout="", ok=False, exited=1, stderr="controller busy"),
            )
        ]
    )

    first_snapshot, first_timestamp = query._get_priority_snapshot(
        conn, "cluster.example.com"
    )
    second_snapshot, second_timestamp = query._get_priority_snapshot(
        conn, "cluster.example.com"
    )

    assert first_snapshot == second_snapshot == {}
    assert first_timestamp == second_timestamp
    assert len(conn.commands) == 1
