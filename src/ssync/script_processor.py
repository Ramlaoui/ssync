"""Script preprocessing for SLURM job submission."""

import re
from pathlib import Path
from typing import Optional, Union

from .utils.slurm_params import SlurmParams, to_directives


class ScriptProcessor:
    """Processes shell and SLURM scripts for job submission."""

    @staticmethod
    def is_slurm_script(script_path: Path) -> bool:
        """Check if script contains SLURM directives."""
        try:
            content = script_path.read_text()
            # Look for SLURM directives like #SBATCH
            return bool(re.search(r"#SBATCH\s+", content))
        except Exception:
            return False

    @staticmethod
    def ensure_shebang(content: str) -> str:
        """Ensure script has proper shebang."""
        if not content.startswith("#!"):
            return "#!/bin/bash\n\n" + content
        return content

    @staticmethod
    def add_slurm_directives(
        content: str,
        job_name: Optional[str] = None,
        cpus: Optional[int] = None,
        mem: Optional[int] = None,
        time: Optional[int] = None,
        partition: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        constraint: Optional[str] = None,
        account: Optional[str] = None,
        ntasks_per_node: Optional[int] = None,
        nodes: Optional[int] = None,
        gpus_per_node: Optional[int] = None,
        gres: Optional[str] = None,
    ) -> str:
        """Add SLURM directives to a shell script using centralized formatter.

        This delegates formatting/normalization to `to_directives` so all
        callers share the same logic for aliases and units.
        """
        params = {
            "job_name": job_name,
            "cpus_per_task": cpus,
            "mem_gb": mem,
            "time": time,
            "partition": partition,
            "output": output,
            "error": error,
            "constraint": constraint,
            "account": account,
            "ntasks_per_node": ntasks_per_node,
            "nodes": nodes,
            "gpus_per_node": gpus_per_node,
            "gres": gres,
        }

        directives = to_directives(params)

        if not directives:
            return content

        # Find insertion point after shebang
        lines = content.split("\n")
        insert_idx = 1 if lines and lines[0].startswith("#!") else 0

        # Insert directives
        for i, directive in enumerate(directives):
            lines.insert(insert_idx + i, directive)

        return "\n".join(lines)

    @classmethod
    def prepare_script(
        cls,
        script_path: Path,
        target_dir: Path,
        params: Optional[Union[SlurmParams, dict]] = None,
    ) -> Path:
        """Prepare script for SLURM submission.

        Returns path to the prepared script in target directory.
        """
        content = script_path.read_text()

        # Ensure proper shebang
        content = cls.ensure_shebang(content)

        # Add SLURM directives if it's a plain shell script
        if not cls.is_slurm_script(script_path):
            if params is None:
                directive_params = {}
            elif isinstance(params, SlurmParams):
                directive_params = params.as_dict()
            else:
                directive_params = params

            # Use the centralized formatter
            directives = to_directives(directive_params)
            if directives:
                # Insert directives after shebang
                lines = content.split("\n")
                insert_idx = 1 if lines and lines[0].startswith("#!") else 0
                for i, directive in enumerate(directives):
                    lines.insert(insert_idx + i, directive)
                content = "\n".join(lines)

        # Create target script path with .slurm extension
        script_name = script_path.stem + ".slurm"
        target_script = target_dir / script_name

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write prepared script
        target_script.write_text(content)
        target_script.chmod(0o755)  # Make executable

        return target_script
