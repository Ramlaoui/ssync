"""Script preprocessing for Slurm job submission."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..models.watcher import ActionType, WatcherAction, WatcherDefinition
from ..slurm.params import SlurmParams, to_directives


class ScriptProcessor:
    """Processes shell and Slurm scripts for job submission."""

    @staticmethod
    def _contains_slurm_directives(content: str) -> bool:
        """Check whether in-memory script content already has Slurm directives."""
        return bool(re.search(r"#SBATCH\s+", content))

    @staticmethod
    def _apply_watcher_action_defaults(watcher: WatcherDefinition) -> None:
        """Propagate watcher-level settings into action params when needed."""
        if watcher.remaining_resubmits is None:
            return

        for action in watcher.actions:
            if action.type == ActionType.RESUBMIT:
                action.params.setdefault(
                    "remaining_resubmits", watcher.remaining_resubmits
                )

    @staticmethod
    def decrement_watcher_resubmit_counter(
        script_content: str,
        *,
        watcher_name: Optional[str],
        watcher_pattern: str,
        trigger_on_job_end: bool,
        current_remaining: int,
    ) -> str:
        """Decrement the resubmit counter for the matching watcher block."""
        if current_remaining < 0:
            raise ValueError("remaining resubmits cannot be negative")

        lines = script_content.split("\n")
        updated = False
        i = 0

        while i < len(lines):
            if lines[i].strip() != "#WATCHER_BEGIN":
                i += 1
                continue

            block_start = i
            i += 1
            watcher_lines: List[str] = []
            while i < len(lines) and lines[i].strip() != "#WATCHER_END":
                watcher_lines.append(lines[i])
                i += 1

            if i >= len(lines):
                break

            block_end = i
            parsed = ScriptProcessor._parse_watcher_block("\n".join(watcher_lines))
            if not parsed:
                i += 1
                continue

            has_resubmit = any(
                action.type == ActionType.RESUBMIT for action in parsed.actions
            )
            if (
                has_resubmit
                and parsed.name == watcher_name
                and parsed.pattern == watcher_pattern
                and parsed.trigger_on_job_end == trigger_on_job_end
            ):
                action_remaining = next(
                    (
                        action.params.get("remaining_resubmits")
                        for action in parsed.actions
                        if action.type == ActionType.RESUBMIT
                    ),
                    None,
                )
                if action_remaining is not None and int(action_remaining) != int(
                    current_remaining
                ):
                    i += 1
                    continue

                next_remaining = current_remaining - 1
                comment_prefix = "# "
                for raw_line in watcher_lines:
                    match = re.match(r"^(\s*#\s*)", raw_line)
                    if match:
                        comment_prefix = match.group(1)
                        break

                field_replaced = False
                for idx, raw_line in enumerate(watcher_lines):
                    if re.match(
                        r"^\s*#\s*(remaining_resubmits|resubmit_count)\s*:",
                        raw_line,
                    ):
                        key_match = re.match(
                            r"^(\s*#\s*)(remaining_resubmits|resubmit_count)\s*:",
                            raw_line,
                        )
                        key = key_match.group(2) if key_match else "remaining_resubmits"
                        prefix = key_match.group(1) if key_match else comment_prefix
                        watcher_lines[idx] = f"{prefix}{key}: {next_remaining}"
                        field_replaced = True
                        break

                if not field_replaced:
                    insert_at = len(watcher_lines)
                    for idx, raw_line in enumerate(watcher_lines):
                        if re.match(r"^\s*#\s*actions\s*:", raw_line):
                            insert_at = idx
                            break
                    watcher_lines.insert(
                        insert_at,
                        f"{comment_prefix}remaining_resubmits: {next_remaining}",
                    )

                lines[block_start + 1 : block_end] = watcher_lines
                updated = True
                break

            i += 1

        if not updated:
            raise ValueError("Could not locate watcher block to decrement resubmit counter")

        return "\n".join(lines)

    @staticmethod
    def render_script_variables(
        content: str, variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Render supported ${var} shell-style expressions for provided variables.

        Only variables explicitly present in ``variables`` are rendered. Missing
        variables are left untouched so the shell can handle them later.
        """
        if not variables:
            return content

        rendered = content
        render_vars = {
            str(name): str(value)
            for name, value in variables.items()
            if not str(name).startswith("_")
        }

        for var_name, var_value in render_vars.items():
            cond_pattern = re.compile(
                re.escape("${" + var_name + ":+")
                + r"((?:[^{}]|\$\{[^}]*\})*)"
                + re.escape("}")
            )

            def _expand_conditional(match: re.Match) -> str:
                word = match.group(1)
                for nested_name, nested_value in render_vars.items():
                    word = word.replace(f"${{{nested_name}}}", nested_value)
                return word

            rendered = cond_pattern.sub(_expand_conditional, rendered)

            default_pattern = re.compile(
                re.escape("${" + var_name + ":-") + r"[^}]*" + re.escape("}")
            )
            rendered = default_pattern.sub(var_value, rendered)
            rendered = rendered.replace(f"${{{var_name}}}", var_value)

        return rendered

    @staticmethod
    def is_slurm_script(script_path: Path) -> bool:
        """Check if script contains Slurm directives."""
        try:
            content = script_path.read_text()
            return ScriptProcessor._contains_slurm_directives(content)
        except Exception:
            return False

    @staticmethod
    def prepare_script_content(
        content: str, params: Optional[Union[SlurmParams, dict]] = None
    ) -> str:
        """Prepare in-memory script content for submission and future relaunch."""
        prepared = ScriptProcessor.ensure_shebang(content)

        if ScriptProcessor._contains_slurm_directives(prepared):
            return prepared

        if params is None:
            directive_params = {}
        elif isinstance(params, SlurmParams):
            directive_params = params.as_dict()
        else:
            directive_params = params

        directives = to_directives(directive_params)
        if not directives:
            return prepared

        lines = prepared.split("\n")
        insert_idx = 1 if lines and lines[0].startswith("#!") else 0
        for i, directive in enumerate(directives):
            lines.insert(insert_idx + i, directive)

        return "\n".join(lines)

    @staticmethod
    def extract_array_spec(script_content: str) -> Optional[str]:
        """
        Extract array job specification from Slurm script.

        Returns:
            Array spec string (e.g., "0-5", "1,3,5", "0-100%10") or None if not an array job
        """
        # Look for #SBATCH --array=... directive
        match = re.search(r"#SBATCH\s+--array[=\s]+([^\s]+)", script_content)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def parse_array_spec(array_spec: str) -> Optional[int]:
        """
        Parse array spec to determine expected number of tasks.

        Args:
            array_spec: Array specification like "0-5", "1,3,5", "0-100%10"

        Returns:
            Expected number of tasks, or None if cannot determine
        """
        if not array_spec:
            return None

        try:
            # Handle step notation (e.g., "0-100%10" means 11 tasks)
            if "%" in array_spec:
                range_part, step = array_spec.split("%")
                step = int(step)
            else:
                range_part = array_spec
                step = 1

            # Handle comma-separated list (e.g., "1,3,5")
            if "," in range_part:
                return len(range_part.split(","))

            # Handle range notation (e.g., "0-5")
            if "-" in range_part:
                start, end = range_part.split("-")
                start = int(start)
                end = int(end)
                return (end - start) // step + 1

            # Single task
            return 1

        except (ValueError, IndexError):
            return None

    @staticmethod
    def ensure_shebang(content: str) -> str:
        """Ensure script has proper shebang."""
        if not content.startswith("#!"):
            return "#!/bin/bash\n" + content
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
        """Add Slurm directives to a shell script using centralized formatter.

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
        """Prepare script for Slurm submission.

        Returns path to the prepared script in target directory.
        """
        content = cls.prepare_script_content(script_path.read_text(), params=params)

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
        in_actions = False

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Remove leading comment marker if present
            stripped = line.strip()
            if stripped.startswith("# "):
                line = stripped[2:]
            elif stripped.startswith("#"):
                # Try removing just the #
                line = stripped[1:].strip()
                if not line:  # Was just a single #
                    continue

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
                        except json.JSONDecodeError:
                            watcher.captures = [
                                v.strip() for v in value.strip("[]").split(",")
                            ]
                    else:
                        watcher.captures = [v.strip() for v in value.split(",")]
                elif key == "condition":
                    watcher.condition = value.strip("\"'")
                elif key == "timer_mode_enabled" or key == "timer_mode":
                    watcher.timer_mode_enabled = value.lower() in [
                        "true",
                        "yes",
                        "1",
                        "on",
                    ]
                elif key == "timer_interval_seconds" or key == "timer_interval":
                    try:
                        watcher.timer_interval_seconds = int(value)
                    except ValueError:
                        pass
                elif key == "trigger_on_job_end":
                    watcher.trigger_on_job_end = value.lower() in [
                        "true",
                        "yes",
                        "1",
                        "on",
                    ]
                elif key == "trigger_job_states":
                    if value.startswith("["):
                        try:
                            watcher.trigger_job_states = json.loads(value)
                        except json.JSONDecodeError:
                            watcher.trigger_job_states = [
                                v.strip().strip("\"'")
                                for v in value.strip("[]").split(",")
                                if v.strip()
                            ]
                    else:
                        watcher.trigger_job_states = [
                            v.strip().strip("\"'")
                            for v in value.split(",")
                            if v.strip()
                        ]
                elif key == "remaining_resubmits" or key == "resubmit_count":
                    try:
                        watcher.remaining_resubmits = int(value)
                    except ValueError:
                        pass
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
        # Pattern is required, but actions can be empty (will be added later or use defaults)
        if watcher.pattern or watcher.trigger_on_job_end:
            # If no actions specified, add a default log_event action
            if not watcher.actions:
                watcher.actions.append(
                    WatcherAction(type=ActionType.LOG_EVENT, params={})
                )
            ScriptProcessor._apply_watcher_action_defaults(watcher)
            return watcher
        return None

    @staticmethod
    def _parse_inline_watcher(line: str) -> Optional[WatcherDefinition]:
        """Parse an inline watcher directive."""
        watcher = WatcherDefinition()

        # Improved regex to handle quoted strings, function calls, and arrays
        # This regex matches: key="value" or key='value' or key=func(params) or key=[array] or key=value
        parts = re.findall(
            r'(\w+)=("[^"]*"|\'[^\']*\'|\[[^\]]*\]|\w+\([^)]*\)|[^\s]+)', line
        )

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
            elif key == "captures":
                # Parse array syntax [item1, item2]
                if value.startswith("[") and value.endswith("]"):
                    watcher.captures = [
                        v.strip() for v in value[1:-1].split(",") if v.strip()
                    ]
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
            elif key == "trigger_on_job_end":
                watcher.trigger_on_job_end = value.lower() in [
                    "true",
                    "yes",
                    "1",
                    "on",
                ]
            elif key == "trigger_job_states":
                if value.startswith("[") and value.endswith("]"):
                    watcher.trigger_job_states = [
                        v.strip().strip("\"'")
                        for v in value[1:-1].split(",")
                        if v.strip()
                    ]
            elif key == "remaining_resubmits" or key == "resubmit_count":
                try:
                    watcher.remaining_resubmits = int(value)
                except ValueError:
                    pass

        # Validate minimum requirements
        # Pattern is required, but actions can be empty (will be added later or use defaults)
        if watcher.pattern or watcher.trigger_on_job_end:
            # If no actions specified, add a default log_event action
            if not watcher.actions:
                watcher.actions.append(
                    WatcherAction(type=ActionType.LOG_EVENT, params={})
                )
            ScriptProcessor._apply_watcher_action_defaults(watcher)
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
