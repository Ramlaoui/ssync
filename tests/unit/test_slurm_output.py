"""Unit tests for slurm/output.py."""

import pytest

from ssync.slurm.output import SlurmOutput


class _FakeResult:
    def __init__(self, ok: bool, stdout: str = "", stderr: str = "", exited: int = 0):
        self.ok = ok
        self.stdout = stdout
        self.stderr = stderr
        self.exited = exited


class _FakeConn:
    def __init__(self):
        self.calls = []

    def run(self, command: str, **kwargs):
        self.calls.append(command)

        if command == "scontrol show job 123 456":
            return _FakeResult(
                ok=False,
                stderr="too many arguments for keyword:show",
                exited=1,
            )

        if command == "scontrol show job 123":
            return _FakeResult(
                ok=True,
                stdout=(
                    "JobId=123 JobName=test\n"
                    "   Command=/work/scripts/job_123.slurm\n"
                    "   StdOut=/work/slurm-%j.out StdErr=/work/slurm-%j.err\n"
                ),
            )

        if command == "scontrol show job 456":
            return _FakeResult(
                ok=True,
                stdout=(
                    "JobId=456 JobName=test2\n"
                    "   Command=/work/scripts/job_456.slurm\n"
                    "   StdOut=/work/slurm-%j.out StdErr=/work/slurm-%j.err\n"
                ),
            )

        return _FakeResult(ok=False, stderr="unexpected command", exited=1)


class TestSlurmOutput:
    @pytest.mark.unit
    def test_batch_falls_back_to_single_job_queries(self):
        output = SlurmOutput()
        conn = _FakeConn()

        details = output.get_job_details_from_scontrol_batch(
            conn=conn,
            job_ids=["123", "456"],
            hostname="cluster.example.com",
        )

        assert details["123"][0] == "/work/slurm-123.out"
        assert details["123"][1] == "/work/slurm-123.err"
        assert details["123"][2] == "/work/scripts/job_123.slurm"

        assert details["456"][0] == "/work/slurm-456.out"
        assert details["456"][1] == "/work/slurm-456.err"
        assert details["456"][2] == "/work/scripts/job_456.slurm"

        assert conn.calls[0] == "scontrol show job 123 456"
        assert "scontrol show job 123" in conn.calls
        assert "scontrol show job 456" in conn.calls

    @pytest.mark.unit
    def test_batch_respects_single_job_fallback_cap(self):
        output = SlurmOutput()
        conn = _FakeConn()

        details = output.get_job_details_from_scontrol_batch(
            conn=conn,
            job_ids=["123", "456"],
            hostname="cluster.example.com",
            max_single_job_fallbacks=1,
        )

        assert details["123"][0] == "/work/slurm-123.out"
        assert "456" not in details
        assert conn.calls[0] == "scontrol show job 123 456"
        assert "scontrol show job 123" in conn.calls
        assert "scontrol show job 456" not in conn.calls
