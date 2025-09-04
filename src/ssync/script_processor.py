"""Script preprocessing for SLURM job submission."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .models.watcher import ActionType, WatcherAction, WatcherDefinition
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

    @staticmethod
    def extract_watchers(script_content: str) -> Tuple[List[WatcherDefinition], str]:
        """
        Extract watcher definitions from script and return clean script.

        Returns:
            Tuple of (list of watcher definitions, script with watchers removed)
        """
        watchers = []
        clean_lines = []
        lines = script_content.split("\n")

        in_watcher_block = False
        watcher_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check for watcher block start
            if stripped == "#WATCHER_BEGIN":
                in_watcher_block = True
                watcher_lines = []
                i += 1
                continue

            # Check for watcher block end
            elif stripped == "#WATCHER_END":
                if in_watcher_block and watcher_lines:
                    # Parse the watcher block
                    watcher_def = ScriptProcessor._parse_watcher_block(
                        "\n".join(watcher_lines)
                    )
                    if watcher_def:
                        watchers.append(watcher_def)
                in_watcher_block = False
                watcher_lines = []
                i += 1
                continue

            # Check for inline watcher
            elif stripped.startswith("#WATCHER "):
                # Parse inline watcher
                watcher_def = ScriptProcessor._parse_inline_watcher(stripped[9:])
                if watcher_def:
                    watchers.append(watcher_def)
                i += 1
                continue

            # Accumulate watcher block content
            elif in_watcher_block:
                watcher_lines.append(line)
                i += 1
                continue

            # Regular script line
            else:
                clean_lines.append(line)
                i += 1

        return watchers, "\n".join(clean_lines)

    @staticmethod
    def _parse_watcher_block(block_content: str) -> Optional[WatcherDefinition]:
        """Parse a watcher block in YAML-like format."""
        watcher = WatcherDefinition()

        lines = block_content.strip().split("\n")
        current_action = None
        in_actions = False

        for line in lines:
            # Skip comments and empty lines
            if line.strip().startswith("#") or not line.strip():
                continue

            # Remove leading comment marker if present
            if line.lstrip().startswith("# "):
                line = line.lstrip()[2:]

            # Parse key-value pairs
            if ":" in line and not in_actions:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()

                if key == "name":
                    watcher.name = value
                elif key == "pattern":
                    watcher.pattern = value.strip("\"'")
                elif key == "interval":
                    try:
                        watcher.interval_seconds = int(value)
                    except ValueError:
                        pass
                elif key == "captures":
                    # Parse as JSON array or comma-separated
                    if value.startswith("["):
                        try:
                            watcher.captures = json.loads(value)
                        except:
                            watcher.captures = [
                                v.strip() for v in value.strip("[]").split(",")
                            ]
                    else:
                        watcher.captures = [v.strip() for v in value.split(",")]
                elif key == "condition":
                    watcher.condition = value.strip("\"'")
                elif key == "action":
                    # Simple single action
                    action_type, params = ScriptProcessor._parse_action_string(value)
                    if action_type:
                        watcher.actions.append(
                            WatcherAction(type=action_type, params=params)
                        )
                elif key == "actions":
                    in_actions = True

            # Parse actions list
            elif in_actions and line.strip().startswith("- "):
                action_str = line.strip()[2:]
                action_type, params = ScriptProcessor._parse_action_string(action_str)
                if action_type:
                    watcher.actions.append(
                        WatcherAction(type=action_type, params=params)
                    )

        # Validate minimum requirements
        if watcher.pattern and watcher.actions:
            return watcher
        return None

    @staticmethod
    def _parse_inline_watcher(line: str) -> Optional[WatcherDefinition]:
        """Parse an inline watcher directive."""
        watcher = WatcherDefinition()

        # Parse key=value pairs
        parts = re.findall(r'(\w+)=("[^"]*"|\'[^\']*\'|[^\s]+)', line)

        for key, value in parts:
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            key = key.lower()

            if key == "pattern":
                watcher.pattern = value
            elif key == "interval":
                try:
                    watcher.interval_seconds = int(value)
                except ValueError:
                    pass
            elif key == "action":
                action_type, params = ScriptProcessor._parse_action_string(value)
                if action_type:
                    watcher.actions.append(
                        WatcherAction(type=action_type, params=params)
                    )
            elif key == "condition":
                watcher.condition = value
            elif key == "name":
                watcher.name = value

        # Validate minimum requirements
        if watcher.pattern and watcher.actions:
            return watcher
        return None

    @staticmethod
    def _parse_action_string(
        action_str: str,
    ) -> Tuple[Optional[ActionType], Dict[str, Any]]:
        """Parse an action string into type and parameters."""
        params = {}

        # Extract action type (first word or until parentheses)
        match = re.match(r"^(\w+)(?:\((.*)\))?$", action_str.strip())
        if not match:
            # Try space-separated format
            parts = action_str.strip().split(None, 1)
            if not parts:
                return None, {}

            action_name = parts[0]
            if len(parts) > 1:
                params["message"] = parts[1]
        else:
            action_name = match.group(1)
            if match.group(2):
                # Parse parameters in parentheses
                param_str = match.group(2)
                for param in param_str.split(","):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        params[key.strip()] = value.strip().strip("\"'")

        # Map action name to ActionType
        action_map = {
            "cancel": ActionType.CANCEL_JOB,
            "cancel_job": ActionType.CANCEL_JOB,
            "resubmit": ActionType.RESUBMIT,
            "notify": ActionType.NOTIFY_EMAIL,
            "notify_email": ActionType.NOTIFY_EMAIL,
            "notify_slack": ActionType.NOTIFY_SLACK,
            "email": ActionType.NOTIFY_EMAIL,
            "slack": ActionType.NOTIFY_SLACK,
            "run": ActionType.RUN_COMMAND,
            "run_command": ActionType.RUN_COMMAND,
            "command": ActionType.RUN_COMMAND,
            "store": ActionType.STORE_METRIC,
            "store_metric": ActionType.STORE_METRIC,
            "metric": ActionType.STORE_METRIC,
            "log": ActionType.LOG_EVENT,
            "log_event": ActionType.LOG_EVENT,
        }

        action_type = action_map.get(action_name.lower())
        if action_type:
            return action_type, params

        return None, {}
