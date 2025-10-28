"""Action executor for watchers."""

import json
import os
import re
import tempfile
from datetime import datetime
from typing import Any, Dict, Tuple

from ..models.watcher import ActionType
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class ActionExecutor:
    """Executes watcher actions."""

    async def execute(
        self,
        action_type: ActionType,
        params: Dict[str, Any],
        job_id: str,
        hostname: str,
        variables: Dict[str, Any],
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
                return await self._resubmit_job(job_id, hostname, params)

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
                                [k for k in variables.keys() if not k.startswith("_") and not k.isdigit()]
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
        """Cancel a SLURM job."""
        try:
            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return False, "No SLURM manager available"

            slurm_host = manager.get_host_by_name(hostname)
            conn = manager._get_connection(slurm_host.host)

            # Cancel the job
            result = conn.run(f"scancel {job_id}", hide=True, warn=True)

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
                    logger.error(f"Failed to stop watchers for cancelled job {job_id}: {e}")

                return True, f"Job {job_id} cancelled: {reason}"
            else:
                return False, f"Failed to cancel job: {result.stderr}"

        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False, str(e)

    async def _resubmit_job(
        self, job_id: str, hostname: str, params: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Resubmit a job with modified parameters."""
        try:
            from ..cache import get_cache
            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return False, "No SLURM manager available"

            # Get original script
            cache = get_cache()
            cached_job = cache.get_cached_job(job_id, hostname)
            if not cached_job or not cached_job.script_content:
                return False, "Original script not found in cache"

            script_content = cached_job.script_content

            # Modify script with new parameters
            modifications = params.get("modifications", {})
            for key, value in modifications.items():
                # Simple replacement of SBATCH directives
                pattern = f"#SBATCH --{key}=.*"
                replacement = f"#SBATCH --{key}={value}"
                script_content = re.sub(pattern, replacement, script_content)

            # Cancel previous job first if requested
            if params.get("cancel_previous", True):
                await self._cancel_job(job_id, hostname, {"reason": "Resubmitting"})

            # Submit new job
            slurm_host = manager.get_host_by_name(hostname)
            conn = manager._get_connection(slurm_host.host)

            # Write script to temp file and submit
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(script_content)
                temp_path = f.name

            try:
                # Transfer script
                conn.put(temp_path, f"/tmp/resubmit_{job_id}.sh")

                # Submit
                result = conn.run(
                    f"sbatch /tmp/resubmit_{job_id}.sh", hide=True, warn=True
                )

                if result.ok:
                    # Extract new job ID
                    match = re.search(r"Submitted batch job (\d+)", result.stdout)
                    new_job_id = match.group(1) if match else "unknown"

                    logger.info(f"Resubmitted job {job_id} as {new_job_id}")
                    return True, f"Resubmitted as job {new_job_id}"
                else:
                    return False, f"Failed to resubmit: {result.stderr}"

            finally:
                # Clean up temp file
                os.unlink(temp_path)
                conn.run(f"rm -f /tmp/resubmit_{job_id}.sh", warn=True)

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
        """Send email notification."""
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
                conn = manager._get_connection(slurm_host.host)

                # Send email via mail command
                result = conn.run(
                    f'echo "{message}" | mail -s "{subject}" {recipient}',
                    hide=True,
                    warn=True,
                )

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
        """Run a custom command."""
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
                return False, "No SLURM manager available"

            slurm_host = manager.get_host_by_name(hostname)
            conn = manager._get_connection(slurm_host.host)

            # Try to get job's working directory for better context
            work_dir = None
            try:
                # Get job info to find working directory
                job_result = conn.run(
                    f"scontrol show job {job_id}", hide=True, warn=True
                )
                if job_result.ok:
                    for line in job_result.stdout.split("\n"):
                        if "WorkDir=" in line:
                            work_dir = line.split("WorkDir=")[1].split()[0]
                            break
            except:
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

            # Run command asynchronously using asyncio.to_thread to avoid blocking
            import asyncio

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

            # Run the SSH command in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_ssh_command)

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
