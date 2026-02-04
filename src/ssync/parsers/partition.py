from __future__ import annotations

from typing import Dict, List, Optional

from ..models.partition import PartitionResources

_GPU_SENTINELS = {"n/a", "na", "-", "(null)", "none", ""}


class PartitionParser:
    """Parse and aggregate partition resource data from sinfo output."""

    @staticmethod
    def normalize_partition_name(name: str) -> str:
        if not name:
            return ""
        normalized = name.strip()
        # Default partition is marked with a trailing '*'
        if normalized.endswith("*"):
            normalized = normalized.rstrip("*")
        if normalized.endswith("!"):
            normalized = normalized.rstrip("!")
        return normalized

    @staticmethod
    def normalize_state(state: str) -> str:
        if not state:
            return ""
        normalized = state.strip().lower()
        return normalized.rstrip("+*")

    @staticmethod
    def _parse_int(value: Optional[str]) -> int:
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def parse_cpu_state(cls, value: Optional[str]) -> tuple[int, int, int, int]:
        """Parse CPU state string in alloc/idle/other/total format."""
        if not value:
            return 0, 0, 0, 0

        parts = value.strip().split("/")
        if len(parts) != 4:
            return 0, 0, 0, 0

        alloc = cls._parse_int(parts[0])
        idle = cls._parse_int(parts[1])
        other = cls._parse_int(parts[2])
        total = cls._parse_int(parts[3])
        return alloc, idle, other, total

    @staticmethod
    def parse_gres(value: Optional[str]) -> Dict[str, int]:
        """Parse GRES string into per-node GPU counts by type."""
        if not value:
            return {}

        normalized = value.strip()
        if normalized.lower() in _GPU_SENTINELS:
            return {}

        entries = {}
        for raw in normalized.split(","):
            token = raw.strip()
            if not token:
                continue

            # Remove parentheses (e.g., gpu:V100:4(S:0-3))
            token = token.split("(", 1)[0].strip()
            if not token:
                continue

            parts = token.split(":")
            if not parts or parts[0].lower() != "gpu":
                continue

            if len(parts) == 2:
                gpu_type = "gpu"
                count_str = parts[1]
            else:
                gpu_type = ":".join(parts[1:-1]) or "gpu"
                count_str = parts[-1]

            if not count_str.isdigit():
                continue

            entries[gpu_type] = entries.get(gpu_type, 0) + int(count_str)

        return entries

    @classmethod
    def parse_sinfo_output(
        cls, output: str, fields: List[str]
    ) -> List[PartitionResources]:
        """Parse sinfo output into aggregated partition resources."""
        partitions: Dict[str, PartitionResources] = {}

        for line in output.splitlines():
            if not line.strip():
                continue

            parts = line.split("|")
            if len(parts) < len(fields):
                continue

            row = {fields[i]: parts[i] for i in range(len(fields))}
            raw_name = row.get("partition", "")
            name = cls.normalize_partition_name(raw_name)
            if not name:
                continue

            partition = partitions.get(name)
            if not partition:
                partition = PartitionResources(name=name)
                partitions[name] = partition

            availability = row.get("availability")
            if availability and partition.availability is None:
                partition.availability = availability.strip()

            state = cls.normalize_state(row.get("state", ""))
            if state:
                partition.states.add(state)

            nodes = cls._parse_int(row.get("nodes"))
            partition.add_nodes(nodes)

            if "cpus" in row:
                alloc, idle, other, total = cls.parse_cpu_state(row.get("cpus"))
                partition.add_cpus(alloc, idle, other, total)

            if "gres" in row:
                gres = cls.parse_gres(row.get("gres"))
                gres_used = (
                    cls.parse_gres(row.get("gres_used"))
                    if "gres_used" in row
                    else None
                )
                partition.add_gres(nodes, gres, gres_used)

        return list(partitions.values())
