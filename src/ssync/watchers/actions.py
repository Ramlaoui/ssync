"""Action executor for watchers."""

import asyncio
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Tuple

from ..launch import LaunchManager
from ..models.watcher import ActionType
from ..parsers.script_processor import ScriptProcessor
from ..slurm.params import SlurmParams
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class ActionExecutor:
    """Executes watcher actions."""

    @staticmethod
    def _referenced_script_variables(script_content: str) -> set[str]:
        """Extract named shell-style variables referenced in a script body."""
        referenced: set[str] = set()
        for match in re.finditer(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-+][^}]*)?\}", script_content
        ):
            referenced.add(match.group(1))
        for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", script_content):
            referenced.add(match.group(1))
        return referenced

    def _validate_required_resubmit_captures(
        self,
        script_content: str,
        variables: Dict[str, Any] | None,
        watcher: Any | None,
    ) -> str | None:
        """Fail closed when a job-end resubmit is missing named captures it uses."""
        if watcher is None or not watcher.definition.trigger_on_job_end:
            return None

        named_captures = {
            str(capture_name)
            for capture_name in watcher.definition.captures
            if str(capture_name) and not str(capture_name).isdigit()
        }
        if not named_captures:
            return None

        referenced_captures = (
            self._referenced_script_variables(script_content) & named_captures
        )
        if not referenced_captures:
            return None

        missing = sorted(
            name
            for name in referenced_captures
            if variables is None or variables.get(name) in (None, "")
        )
        if not missing:
            return None

        return (
            "Missing required watcher capture(s) for resubmit: "
            + ", ".join(missing)
        )

    async def execute(
        self,
        action_type: ActionType,
        params: Dict[str, Any],
        job_id: str,
        hostname: str,
        variables: Dict[str, Any],
        watcher: Any | None = None,
    ) -> Tuple[bool, str]:
        """
        Execute an action.

        Returns:
            Tuple of (success, result_message)
        """
        try:
            # Substitute variables in parameters
            params = self._substitute_variables(params, variables, job_id, hostname)

            # Route to appropriate handler
            if action_type == ActionType.CANCEL_JOB:
                return await self._cancel_job(job_id, hostname, params)

            elif action_type == ActionType.RESUBMIT:
                return await self._resubmit_job(
                    job_id, hostname, params, variables, watcher
                )

            elif action_type == ActionType.NOTIFY_EMAIL:
                return await self._notify_email(job_id, hostname, params, variables)

            elif action_type == ActionType.NOTIFY_SLACK:
                return await self._notify_slack(job_id, hostname, params, variables)

            elif action_type == ActionType.RUN_COMMAND:
                return await self._run_command(job_id, hostname, params, variables)

            elif action_type == ActionType.STORE_METRIC:
                return await self._store_metric(job_id, hostname, params, variables)

            elif action_type == ActionType.LOG_EVENT:
                return await self._log_event(job_id, hostname, params, variables)

            else:
                return False, f"Unknown action type: {action_type}"

        except Exception as e:
            logger.error(f"Failed to execute action {action_type}: {e}")
            return False, str(e)

    def _substitute_variables(
        self,
        params: Dict[str, Any],
        variables: Dict[str, Any],
        job_id: str,
        hostname: str,
    ) -> Dict[str, Any]:
        """Substitute ${var} placeholders in parameters."""
        # Add built-in variables
        all_vars = {
            "JOB_ID": job_id,
            "HOSTNAME": hostname,
            **variables,
        }

        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                original_value = value
                # First, handle numbered capture groups ($0, $1, $2, etc.)
                # These come from the regex match groups
                import re

                # Handle $0 - the full matched text (if available)
                if "$0" in value and "_matched_text" in variables:
                    value = value.replace("$0", str(variables.get("_matched_text", "")))

                # Look for $1, $2, etc. patterns
                for match in re.finditer(r"\$(\d+)", value):
                    group_num = int(match.group(1))
                    if group_num > 0:
                        # First, try to get the value using the numeric key directly
                        # (New behavior: captures stored as "1", "2", etc.)
                        replacement = variables.get(str(group_num))

                        if replacement is None:
                            # Fallback: old behavior using sorted capture names
                            # (For backward compatibility with named-only captures)
                            capture_names = sorted(
                                [
                                    k
                                    for k in variables.keys()
                                    if not k.startswith("_") and not k.isdigit()
                                ]
                            )
                            if group_num <= len(capture_names):
                                capture_name = capture_names[group_num - 1]
                                replacement = variables.get(capture_name, "")

                        if replacement is not None:
                            logger.debug(
                                f"Replacing ${group_num} with value={replacement}"
                            )
                            value = value.replace(f"${group_num}", str(replacement))

                # Also handle named variables directly - $output_dir, $error_rate, etc.
                for var_name, var_value in variables.items():
                    if not var_name.startswith("_"):  # Skip internal variables
                        value = value.replace(f"${var_name}", str(var_value))

                # Then replace ${var} patterns for named variables
                for var_name, var_value in all_vars.items():
                    value = value.replace(f"${{{var_name}}}", str(var_value))
                    value = value.replace(
                        f"${var_name}", str(var_value)
                    )  # Also support $var without braces

                if original_value != value:
                    logger.debug(f"Substituted '{original_value}' -> '{value}'")
            result[key] = value

        return result

    async def _cancel_job(
        self, job_id: str, hostname: str, params: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Cancel a Slurm job with per-host throttling."""
        try:
            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return False, "No Slurm manager available"

            slurm_host = manager.get_host_by_name(hostname)
            conn = await asyncio.to_thread(manager._get_connection, slurm_host.host)

            # Import throttler for rate limiting SSH commands per host
            from .engine import get_host_throttler

            throttler = get_host_throttler()

            # Cancel the job with throttling
            def do_cancel():
                return conn.run(f"scancel {job_id}", hide=True, warn=True)

            async with throttler.throttle(hostname):
                result = await asyncio.to_thread(do_cancel)

            if result.ok:
                reason = params.get("reason", "Triggered by watcher")
                logger.info(f"Cancelled job {job_id}: {reason}")

                # Stop all watchers for this job to prevent orphaned watchers
                try:
                    from . import get_watcher_engine

                    engine = get_watcher_engine()
                    await engine.stop_watchers_for_job(job_id, hostname)
                    logger.info(f"Stopped all watchers for cancelled job {job_id}")
                except Exception as e:
                    logger.error(
                        f"Failed to stop watchers for cancelled job {job_id}: {e}"
                    )

                return True, f"Job {job_id} cancelled: {reason}"
            else:
                return False, f"Failed to cancel job: {result.stderr}"

        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False, str(e)

    async def _resubmit_job(
        self,
        job_id: str,
        hostname: str,
        params: Dict[str, Any],
        variables: Dict[str, Any] | None = None,
        watcher: Any | None = None,
    ) -> Tuple[bool, str]:
        """Resubmit a job with modified parameters and per-host throttling."""
        try:
            from ..cache import get_cache
            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return False, "No Slurm manager available"

            # Get original script
            cache = get_cache()
            cached_job = cache.get_cached_job(job_id, hostname)
            if not cached_job or not cached_job.script_content:
                return False, "Original script not found in cache"

            script_content = cached_job.script_content
            remaining_resubmits = params.get("remaining_resubmits")
            if remaining_resubmits is not None:
                try:
                    remaining_resubmits = int(remaining_resubmits)
                except (TypeError, ValueError):
                    return (
                        False,
                        f"Invalid remaining_resubmits value: {remaining_resubmits}",
                    )

                if remaining_resubmits <= 0:
                    return False, "No resubmits remaining for this watcher"

                if watcher is None:
                    return False, "Cannot decrement resubmit counter without watcher context"

                script_content = ScriptProcessor.decrement_watcher_resubmit_counter(
                    script_content,
                    watcher_name=watcher.definition.name,
                    watcher_pattern=watcher.definition.pattern,
                    trigger_on_job_end=watcher.definition.trigger_on_job_end,
                    current_remaining=remaining_resubmits,
                )

            missing_capture_error = self._validate_required_resubmit_captures(
                script_content=script_content,
                variables=variables,
                watcher=watcher,
            )
            if missing_capture_error:
                return False, missing_capture_error

            # Modify script with new parameters
            modifications = params.get("modifications", {})
            for key, value in modifications.items():
                # Simple replacement of SBATCH directives
                pattern = f"#SBATCH --{key}=.*"
                replacement = f"#SBATCH --{key}={value}"
                script_content = re.sub(pattern, replacement, script_content)

            all_vars = {"JOB_ID": job_id, "HOSTNAME": hostname, **(variables or {})}
            logger.info(f"Rendering resubmitted script with variables: {all_vars}")

            # Cancel previous job first if requested (already throttled).
            # Skip cancel when triggered by job-end (job is already terminal) —
            # avoids a wasted scancel SSH call and, critically, prevents
            # stop_watchers_for_job from killing sibling watchers.
            job_already_ended = bool(variables and variables.get("job_end_state"))
            if params.get("cancel_previous", True) and not job_already_ended:
                await self._cancel_job(job_id, hostname, {"reason": "Resubmitting"})

            slurm_host = manager.get_host_by_name(hostname)
            source_dir = (
                Path(cached_job.local_source_dir)
                if cached_job.local_source_dir
                else None
            )
            work_dir = cached_job.job_info.work_dir
            if not work_dir and source_dir is not None:
                work_dir = str(Path(slurm_host.work_dir) / source_dir.name)

            launch_manager = LaunchManager(manager)
            new_job = await launch_manager.launch_job(
                script_path=None,
                script_content=script_content,
                script_variables=all_vars,
                source_dir=source_dir,
                host=hostname,
                slurm_params=SlurmParams(),
                sync_enabled=False,
                work_dir_override=work_dir,
            )
            if not new_job:
                return False, "Launch manager did not return a resubmitted job"

            logger.info(f"Resubmitted job {job_id} as {new_job.job_id}")
            return True, f"Resubmitted as job {new_job.job_id}"

        except Exception as e:
            logger.error(f"Failed to resubmit job {job_id}: {e}")
            return False, str(e)

    async def _notify_email(
        self,
        job_id: str,
        hostname: str,
        params: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Send email notification with per-host throttling."""
        try:
            recipient = params.get("to", os.environ.get("SSYNC_EMAIL"))
            if not recipient:
                return False, "No email recipient configured"

            subject = params.get("subject", f"Watcher alert for job {job_id}")
            message = params.get("message", f"Watcher triggered for job {job_id}")

            # Add variables to message
            if variables:
                message += "\n\nCaptured variables:\n"
                for key, value in variables.items():
                    message += f"  {key}: {value}\n"

            # Use mail command if available
            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if manager:
                slurm_host = manager.get_host_by_name(hostname)
                conn = await asyncio.to_thread(manager._get_connection, slurm_host.host)

                # Import throttler for rate limiting SSH commands per host
                from .engine import get_host_throttler

                throttler = get_host_throttler()

                # Send email via mail command with throttling
                def do_send_email():
                    return conn.run(
                        f'echo "{message}" | mail -s "{subject}" {recipient}',
                        hide=True,
                        warn=True,
                    )

                async with throttler.throttle(hostname):
                    result = await asyncio.to_thread(do_send_email)

                if result.ok:
                    logger.info(
                        f"Sent email notification for job {job_id} to {recipient}"
                    )
                    return True, f"Email sent to {recipient}"

            # Log as fallback
            logger.warning(f"Email notification (no mail command): {subject}")
            return True, "Email logged (mail command not available)"

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False, str(e)

    async def _notify_slack(
        self,
        job_id: str,
        hostname: str,
        params: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Send Slack notification."""
        try:
            webhook_url = params.get("webhook", os.environ.get("SSYNC_SLACK_WEBHOOK"))
            if not webhook_url:
                return False, "No Slack webhook configured"

            channel = params.get("channel", "#alerts")
            message = params.get("message", f"Watcher triggered for job {job_id}")

            # Build Slack payload
            payload = {
                "channel": channel,
                "text": message,
                "attachments": [
                    {
                        "color": params.get("color", "warning"),
                        "fields": [
                            {"title": "Job ID", "value": job_id, "short": True},
                            {"title": "Host", "value": hostname, "short": True},
                        ],
                    }
                ],
            }

            # Add captured variables as fields
            if variables:
                for key, value in variables.items():
                    payload["attachments"][0]["fields"].append(
                        {
                            "title": key,
                            "value": str(value),
                            "short": True,
                        }
                    )

            # Send to Slack (would need actual implementation with requests/aiohttp)
            logger.info(f"Slack notification for job {job_id}: {message}")

            # For now, just log it
            return True, "Slack notification logged (implementation pending)"

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False, str(e)

    async def _run_command(
        self,
        job_id: str,
        hostname: str,
        params: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Run a custom command with per-host throttling."""
        try:
            command = params.get("command")
            if not command:
                return False, "No command specified"

            logger.debug(f"Original command: {command}")
            logger.debug(f"Available variables: {variables}")

            # Security check - only allow certain commands
            allowed_prefixes = [
                "echo",
                "logger",
                "date",
                "ls",
                "cat",
                "cd",  # Change directory (often used with && to run commands in specific dirs)
                "pwd",  # Print working directory (useful for debugging)
                "mkdir",  # Create directories (useful for organizing outputs)
                "cp",  # Copy files/directories
                "mv",  # Move/rename files
                "touch",  # Create empty files or update timestamps
                "grep",  # Search text patterns
                "find",  # Find files/directories
                "tail",  # View end of files
                "head",  # View beginning of files
                "wc",  # Count lines/words/chars
                "uv run",  # Run Python with uv-managed dependencies
                "uvx",  # Run Python tools/packages directly
                "python -m uv",  # Alternative uv invocation
                "python",  # Direct Python execution
                "pip",  # Python package management
                "wandb",  # Weights & Biases CLI tool
            ]
            # Also allow compound commands with && or ;
            # Check each part of compound commands

            # Split by && and ; to check each command part
            parts = []
            for part in command.replace("&&", ";").split(";"):
                parts.append(part.strip())

            # Check if all parts are allowed
            all_allowed = True
            for part in parts:
                if part:  # Skip empty parts
                    part_allowed = any(
                        part.startswith(prefix) for prefix in allowed_prefixes
                    )
                    if not part_allowed:
                        all_allowed = False
                        break

            if not all_allowed:
                return False, f"Command not allowed: {command}"

            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return False, "No Slurm manager available"

            slurm_host = manager.get_host_by_name(hostname)
            conn = await asyncio.to_thread(manager._get_connection, slurm_host.host)

            # Import throttler for rate limiting SSH commands per host
            from .engine import get_host_throttler

            throttler = get_host_throttler()

            # Try to get job's working directory for better context
            # This is also throttled to prevent resource exhaustion
            work_dir = None
            try:
                async with throttler.throttle(hostname):
                    # Get job info to find working directory
                    def get_work_dir():
                        job_result = conn.run(
                            f"scontrol show job {job_id}", hide=True, warn=True
                        )
                        if job_result.ok:
                            for line in job_result.stdout.split("\n"):
                                if "WorkDir=" in line:
                                    return line.split("WorkDir=")[1].split()[0]
                        return None

                    work_dir = await asyncio.to_thread(get_work_dir)
            except Exception:
                pass  # Continue without work dir

            # Run command (in job's working directory if available)
            if work_dir and not command.startswith("cd "):
                # For uv commands, run in the job's working directory
                if any(
                    command.startswith(prefix)
                    for prefix in ["uv ", "uvx ", "python -m uv"]
                ):
                    command = f"cd {work_dir} && {command}"
                    logger.info(f"Running command in job directory: {work_dir}")

            # Run command asynchronously with throttling to prevent resource exhaustion
            def run_ssh_command():
                """Run SSH command in a thread to avoid blocking."""
                try:
                    result = conn.run(
                        command, hide=True, warn=True, timeout=120
                    )  # 2 minutes
                    return result
                except Exception as e:
                    logger.error(f"SSH command execution failed: {e}")
                    return None

            # Throttle the main command execution
            async with throttler.throttle(hostname):
                # Run the SSH command in a thread pool to avoid blocking the event loop
                result = await asyncio.to_thread(run_ssh_command)

            if result is None:
                return False, "Failed to execute SSH command"

            if result.ok:
                output = result.stdout.strip()[:500]  # Limit output size
                logger.info(f"Ran command for job {job_id}: {command}")
                return True, f"Command output: {output}"
            else:
                error = result.stderr.strip()[:500]
                return False, f"Command failed: {error}"

        except Exception as e:
            logger.error(f"Failed to run command: {e}")
            return False, str(e)

    async def _store_metric(
        self,
        job_id: str,
        hostname: str,
        params: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Store a metric value."""
        try:
            metric_name = params.get("name", "metric")
            metric_value = params.get("value")

            if metric_value is None:
                # Try to get from variables
                metric_value = variables.get(params.get("variable"))

            if metric_value is None:
                return False, "No metric value specified"

            # Store in cache/database
            from ..cache import get_cache

            cache = get_cache()

            # Store as watcher variable for now
            def store_metric():
                with cache._get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO watcher_variables
                        (watcher_id, variable_name, variable_value, updated_at)
                        VALUES (0, ?, ?, ?)
                        """,
                        (
                            f"{job_id}_{metric_name}",
                            str(metric_value),
                            datetime.now().isoformat(),
                        ),
                    )
                    conn.commit()

            await asyncio.to_thread(store_metric)

            logger.info(f"Stored metric {metric_name}={metric_value} for job {job_id}")
            return True, f"Stored {metric_name}={metric_value}"

        except Exception as e:
            logger.error(f"Failed to store metric: {e}")
            return False, str(e)

    async def _log_event(
        self,
        job_id: str,
        hostname: str,
        params: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Log an event."""
        try:
            message = params.get("message", "Watcher event")
            level = params.get("level", "INFO")

            # Add variables to message
            if variables:
                message += f" | vars: {json.dumps(variables)}"

            # Log at appropriate level
            log_func = getattr(logger, level.lower(), logger.info)
            log_func(f"Job {job_id}: {message}")

            return True, f"Logged: {message}"

        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            return False, str(e)
