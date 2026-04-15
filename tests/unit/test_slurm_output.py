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
                    "JobId=123 JobName=test NumNodes=2 NumCPUs=16 BatchHost=node001 "
                    "NodeList=node[001-002] TRES=cpu=16,gres/gpu:a100=4 "
                    "Gres=gpu:a100:4 TresPerNode=gres:gpu:a100:2\n"
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

        if command == "scontrol show hostnames 'node[001-002]'":
            return _FakeResult(ok=True, stdout="node001\nnode002\n")

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
    def test_scontrol_metadata_includes_node_and_gpu_details(self):
        output = SlurmOutput()
        conn = _FakeConn()

        details = output.get_job_metadata_from_scontrol(
            conn=conn,
            job_id="123",
            hostname="cluster.example.com",
        )

        assert details.batch_host == "node001"
        assert details.node_list == "node[001-002]"
        assert details.num_nodes == "2"
        assert details.num_cpus == "16"
        assert details.tres == "cpu=16,gres/gpu:a100=4"
        assert details.gres == "gpu:a100:4"
        assert details.tres_per_node == "gres:gpu:a100:2"
        assert details.stdout_path == "/work/slurm-123.out"
        assert details.stderr_path == "/work/slurm-123.err"

    @pytest.mark.unit
    def test_resolve_node_hostnames_expands_node_list(self):
        output = SlurmOutput()
        conn = _FakeConn()

        hostnames = output.resolve_node_hostnames(conn, "node[001-002]")

        assert hostnames == ["node001", "node002"]

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
