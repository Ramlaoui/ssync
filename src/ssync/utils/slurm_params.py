"""Helpers to normalize and format SLURM submission parameters.

Centralizes conversion of common aliases, memory/time formatting and
generation of SBATCH directive lines.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SlurmParams:
    """Canonical SLURM submission parameters shared across the codebase.

    Fields mirror the previous definition in `manager.py`. Use
    `to_directives` or `as_dict()` to convert to SBATCH lines.
    """

    job_name: Optional[str] = None
    time_min: Optional[int] = None
    cpus_per_task: Optional[int] = None
    mem_gb: Optional[int] = None
    partition: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    n_tasks_per_node: Optional[int] = None
    gpus_per_node: Optional[int] = None
    gres: Optional[str] = None
    nodes: Optional[int] = None
    constraint: Optional[str] = None
    account: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        """Return a dict suitable for `to_directives` (maps time_min -> time)."""
        d = {
            "job_name": self.job_name,
            "time": self.time_min,
            "cpus_per_task": self.cpus_per_task,
            "mem_gb": self.mem_gb,
            "partition": self.partition,
            "output": self.output,
            "error": self.error,
            "constraint": self.constraint,
            "account": self.account,
            "nodes": self.nodes,
            "ntasks_per_node": self.n_tasks_per_node,
            "gpus_per_node": self.gpus_per_node,
            "gres": self.gres,
        }
        # remove None values
        return {k: v for k, v in d.items() if v is not None}


# Map common alternative names to canonical keys used for SBATCH flags
ALIAS_MAP = {
    "cpus": "cpus_per_task",
    "cpus_per_task": "cpus_per_task",
    "mem": "mem_gb",
    "mem_gb": "mem_gb",
    "time": "time",
    "time_min": "time",
    "partition": "partition",
    "job_name": "job_name",
    "output": "output",
    "error": "error",
    "constraint": "constraint",
    "account": "account",
    "ntasks_per_node": "ntasks_per_node",
    "n_tasks_per_node": "ntasks_per_node",
    "ntasks-per-node": "ntasks_per_node",
    "gpus_per_node": "gpus_per_node",
    "gpus-per-node": "gpus_per_node",
    "gres": "gres",
    "nodes": "nodes",
}


def _is_int_like(v: Any) -> bool:
    try:
        int(v)
        return True
    except Exception:
        return False


def normalize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized dict where aliases are mapped to canonical keys
    and None values are removed.
    """
    out: dict[str, Any] = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        key = ALIAS_MAP.get(k, k)
        out[key] = v
    return out


def format_mem(value: Any) -> str:
    """Format memory values into sbatch-friendly string.

    Accepts integers (interpreted as GB) or strings (passed through if
    they already contain units).
    """
    if value is None:
        return ""
    if isinstance(value, str):
        # If user already provided unit like '4G' or '4096M', leave it
        if any(unit in value.upper() for unit in ("G", "M", "K")):
            return value
        # numeric string
        if _is_int_like(value):
            return f"{int(value)}G"
        return value
    if isinstance(value, (int, float)):
        return f"{int(value)}G"
    # Fallback to string
    return str(value)


def format_time(value: Any) -> str:
    """Format time into HH:MM:SS if integer minutes provided, otherwise
    return original string.
    """
    if value is None:
        return ""
    if _is_int_like(value):
        minutes = int(value)
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}:00"
    # If already a string, assume user provided a valid sbatch time spec
    return str(value)


def to_directives(kwargs: Dict[str, Any]) -> List[str]:
    """Convert a dict of (possibly aliased) slurm params into SBATCH lines.

    Example output: ["#SBATCH --cpus-per-task=4", "#SBATCH --mem=16G"]
    """
    params = normalize_kwargs(kwargs)
    directives: List[str] = []

    if params.get("job_name"):
        directives.append(f"#SBATCH --job-name={params['job_name']}")
    if params.get("cpus_per_task"):
        directives.append(f"#SBATCH --cpus-per-task={params['cpus_per_task']}")
    if params.get("mem_gb"):
        directives.append(f"#SBATCH --mem={format_mem(params['mem_gb'])}")
    if params.get("time"):
        directives.append(f"#SBATCH --time={format_time(params['time'])}")
    if params.get("partition"):
        directives.append(f"#SBATCH --partition={params['partition']}")
    if params.get("output"):
        directives.append(f"#SBATCH --output={params['output']}")
    if params.get("error"):
        directives.append(f"#SBATCH --error={params['error']}")
    if params.get("constraint"):
        directives.append(f"#SBATCH --constraint={params['constraint']}")
    if params.get("account"):
        directives.append(f"#SBATCH --account={params['account']}")
    if params.get("nodes"):
        directives.append(f"#SBATCH --nodes={params['nodes']}")
    if params.get("ntasks_per_node"):
        directives.append(f"#SBATCH --ntasks-per-node={params['ntasks_per_node']}")
    if params.get("gpus_per_node"):
        directives.append(f"#SBATCH --gpus-per-node={params['gpus_per_node']}")
    if params.get("gres"):
        directives.append(f"#SBATCH --gres={params['gres']}")

    return directives
