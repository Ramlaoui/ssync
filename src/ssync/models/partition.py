from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


def _normalize_used_count(
    used_raw: int, per_node: int, nodes: int, total: int
) -> int:
    """Normalize used GPU counts to total allocation for the partition line.

    Heuristic: if used_raw looks like a per-node count, scale by node count.
    If it exceeds total capacity, cap at total.
    """
    if nodes <= 1:
        return min(used_raw, total) if total else used_raw

    if used_raw <= per_node:
        used_total = used_raw * nodes
    else:
        used_total = used_raw

    if total and used_total > total:
        return total
    return used_total


@dataclass
class PartitionResources:
    """Aggregated resource state for a Slurm partition."""

    name: str
    availability: Optional[str] = None
    states: Set[str] = field(default_factory=set)

    nodes_total: int = 0

    cpus_alloc: int = 0
    cpus_idle: int = 0
    cpus_other: int = 0
    cpus_total: int = 0

    gpus_total: Optional[int] = None
    gpus_used: Optional[int] = None
    gpu_types: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add_nodes(self, nodes: int) -> None:
        if nodes is None:
            return
        self.nodes_total += nodes

    def add_cpus(self, alloc: int, idle: int, other: int, total: int) -> None:
        self.cpus_alloc += alloc
        self.cpus_idle += idle
        self.cpus_other += other
        self.cpus_total += total

    def add_gres(
        self,
        nodes: int,
        gres: Dict[str, int],
        gres_used: Optional[Dict[str, int]] = None,
    ) -> None:
        if gres is None:
            return

        if self.gpus_total is None:
            self.gpus_total = 0
        if gres_used is not None and self.gpus_used is None:
            self.gpus_used = 0

        for gpu_type, per_node in gres.items():
            if per_node is None:
                continue

            total = per_node * max(nodes, 1) if nodes else per_node
            self.gpus_total += total

            type_entry = self.gpu_types.setdefault(gpu_type, {"total": 0, "used": 0})
            type_entry["total"] += total

            if gres_used is not None:
                used_raw = gres_used.get(gpu_type, 0)
                used_total = _normalize_used_count(used_raw, per_node, nodes, total)
                if self.gpus_used is None:
                    self.gpus_used = 0
                self.gpus_used += used_total
                type_entry["used"] += used_total

    @property
    def gpus_idle(self) -> Optional[int]:
        if self.gpus_total is None:
            return None
        if self.gpus_used is None:
            return None
        return max(self.gpus_total - self.gpus_used, 0)

    @property
    def state_summary(self) -> str:
        return ", ".join(sorted(self.states))
