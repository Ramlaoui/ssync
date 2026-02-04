"""Unit tests for partition parser."""

import pytest

from ssync.parsers.partition import PartitionParser


class TestPartitionParserCpuState:
    @pytest.mark.unit
    def test_parse_cpu_state_valid(self):
        alloc, idle, other, total = PartitionParser.parse_cpu_state("2/6/0/8")
        assert (alloc, idle, other, total) == (2, 6, 0, 8)

    @pytest.mark.unit
    def test_parse_cpu_state_invalid(self):
        alloc, idle, other, total = PartitionParser.parse_cpu_state("bad")
        assert (alloc, idle, other, total) == (0, 0, 0, 0)


class TestPartitionParserGres:
    @pytest.mark.unit
    def test_parse_gres_single_type(self):
        gres = PartitionParser.parse_gres("gpu:4")
        assert gres == {"gpu": 4}

    @pytest.mark.unit
    def test_parse_gres_multi_type(self):
        gres = PartitionParser.parse_gres("gpu:V100:4,gpu:RTX:2")
        assert gres == {"V100": 4, "RTX": 2}

    @pytest.mark.unit
    def test_parse_gres_with_suffix(self):
        gres = PartitionParser.parse_gres("gpu:A100:8(S:0-7)")
        assert gres == {"A100": 8}

    @pytest.mark.unit
    def test_parse_gres_empty(self):
        gres = PartitionParser.parse_gres("N/A")
        assert gres == {}


class TestPartitionParserSinfoOutput:
    @pytest.mark.unit
    def test_parse_sinfo_output_aggregates_partition(self):
        output = "\n".join(
            [
                "gpu*|up|2|mix|8/8/0/16|gpu:V100:4|gpu:V100:2",
                "gpu|up|1|idle|0/16/0/16|gpu:V100:4|gpu:V100:0",
                "cpu|up|4|idle|0/64/0/64|N/A|N/A",
            ]
        )
        fields = [
            "partition",
            "availability",
            "nodes",
            "state",
            "cpus",
            "gres",
            "gres_used",
        ]

        partitions = PartitionParser.parse_sinfo_output(output, fields)
        by_name = {p.name: p for p in partitions}

        assert set(by_name.keys()) == {"gpu", "cpu"}

        gpu = by_name["gpu"]
        assert gpu.nodes_total == 3
        assert gpu.cpus_alloc == 8
        assert gpu.cpus_idle == 24
        assert gpu.cpus_total == 32
        assert gpu.gpus_total == 12
        assert gpu.gpus_used == 4
        assert gpu.gpus_idle == 8
        assert "mix" in gpu.states
        assert "idle" in gpu.states

        cpu = by_name["cpu"]
        assert cpu.nodes_total == 4
        assert cpu.cpus_alloc == 0
        assert cpu.cpus_idle == 64
        assert cpu.cpus_total == 64
        assert cpu.gpus_total == 0

    @pytest.mark.unit
    def test_parse_sinfo_output_without_gres_used(self):
        output = "gpu|up|1|alloc|4/0/0/4|gpu:V100:4"
        fields = ["partition", "availability", "nodes", "state", "cpus", "gres"]

        partitions = PartitionParser.parse_sinfo_output(output, fields)
        assert len(partitions) == 1
        gpu = partitions[0]
        assert gpu.gpus_total == 4
        assert gpu.gpus_used is None
