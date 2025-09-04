"""Watcher engine for monitoring job outputs."""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..cache import get_cache
from ..models.job import JobInfo, JobState
from ..models.watcher import (
    WatcherDefinition,
    WatcherInstance,
    WatcherState,
)
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class WatcherEngine:
    """Engine for running and managing watchers."""

    def __init__(self):
        self.cache = get_cache()
        self.active_tasks: Dict[int, asyncio.Task] = {}
        self._shutdown = False

    async def start_watchers_for_job(
        self, job_id: str, hostname: str, watchers: List[WatcherDefinition]
    ) -> List[int]:
        """
        Start watchers for a newly submitted job.

        Returns:
            List of watcher IDs
        """
        watcher_ids = []

        for definition in watchers:
            # Store watcher in database
            watcher_id = self._store_watcher(job_id, hostname, definition)
            if watcher_id:
                watcher_ids.append(watcher_id)

                # Start monitoring task
                task = asyncio.create_task(
                    self._monitor_watcher(watcher_id, job_id, hostname)
                )
                self.active_tasks[watcher_id] = task

                logger.info(
                    f"Started watcher {watcher_id} for job {job_id}: "
                    f"pattern='{definition.pattern}', interval={definition.interval_seconds}s"
                )

        return watcher_ids

    async def stop_watchers_for_job(self, job_id: str, hostname: str):
        """Stop all watchers for a job."""
        # Get watcher IDs from database
        watcher_ids = self._get_watcher_ids_for_job(job_id, hostname)

        for watcher_id in watcher_ids:
            if watcher_id in self.active_tasks:
                self.active_tasks[watcher_id].cancel()
                del self.active_tasks[watcher_id]

            # Update state in database
            self._update_watcher_state(watcher_id, WatcherState.COMPLETED)

        logger.info(f"Stopped {len(watcher_ids)} watchers for job {job_id}")

    async def _monitor_watcher(self, watcher_id: int, job_id: str, hostname: str):
        """Monitor a single watcher."""
        backoff_factor = 1.0
        consecutive_failures = 0

        try:
            while not self._shutdown:
                try:
                    # Get watcher details from database
                    watcher = self._get_watcher(watcher_id)
                    if not watcher or watcher.state != WatcherState.ACTIVE:
                        break

                    # Check if job is still active
                    job_info = await self._get_job_info(job_id, hostname)
                    if not job_info or job_info.state not in [
                        JobState.PENDING,
                        JobState.RUNNING,
                    ]:
                        logger.info(
                            f"Job {job_id} no longer active, stopping watcher {watcher_id}"
                        )
                        break

                    # Get new output content
                    new_content = await self._get_new_output(
                        job_info, watcher.definition.output_type, watcher.last_position
                    )

                    if new_content:
                        # Update last position
                        new_position = watcher.last_position + len(new_content.encode())
                        self._update_watcher_position(watcher_id, new_position)

                        # Check for pattern matches
                        matches_found = self._check_patterns(watcher, new_content)

                        if matches_found:
                            # Reset backoff on successful match
                            backoff_factor = 1.0
                            consecutive_failures = 0
                        else:
                            # No matches, increase backoff slightly
                            backoff_factor = min(backoff_factor * 1.1, 5.0)

                    # Sleep with backoff
                    sleep_time = watcher.definition.interval_seconds * backoff_factor
                    await asyncio.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"Error in watcher {watcher_id} monitor loop: {e}")
                    consecutive_failures += 1

                    if consecutive_failures > 5:
                        logger.error(
                            f"Too many failures for watcher {watcher_id}, disabling"
                        )
                        self._update_watcher_state(watcher_id, WatcherState.DISABLED)
                        break

                    # Exponential backoff on failures
                    await asyncio.sleep(min(60, 2**consecutive_failures))

        except asyncio.CancelledError:
            logger.info(f"Watcher {watcher_id} cancelled")
        finally:
            if watcher_id in self.active_tasks:
                del self.active_tasks[watcher_id]

    def _check_patterns(self, watcher: WatcherInstance, content: str) -> bool:
        """Check content for pattern matches and trigger actions."""
        pattern = watcher.definition.pattern
        matches_found = False

        try:
            # Compile regex pattern
            regex = re.compile(pattern, re.MULTILINE)

            for match in regex.finditer(content):
                matches_found = True
                matched_text = match.group(0)

                # Extract captured groups
                captured_vars = {}
                if watcher.definition.captures:
                    groups = match.groups()
                    for i, capture_name in enumerate(watcher.definition.captures):
                        if i < len(groups):
                            captured_vars[capture_name] = groups[i]

                # Update watcher variables
                watcher.variables.update(captured_vars)
                self._update_watcher_variables(watcher.id, captured_vars)

                # Check condition if specified
                if watcher.definition.condition:
                    if not self._evaluate_condition(
                        watcher.definition.condition, watcher.variables
                    ):
                        continue

                # Trigger actions
                for action in watcher.definition.actions:
                    # Check action-specific condition
                    if action.condition:
                        if not self._evaluate_condition(
                            action.condition, watcher.variables
                        ):
                            continue

                    # Execute action asynchronously
                    asyncio.create_task(
                        self._execute_action(
                            watcher, action, matched_text, captured_vars
                        )
                    )

                # Update trigger count
                watcher.trigger_count += 1
                self._update_watcher_trigger_count(watcher.id, watcher.trigger_count)

                # Check max triggers
                if watcher.definition.max_triggers:
                    if watcher.trigger_count >= watcher.definition.max_triggers:
                        logger.info(
                            f"Watcher {watcher.id} reached max triggers "
                            f"({watcher.definition.max_triggers}), disabling"
                        )
                        self._update_watcher_state(watcher.id, WatcherState.TRIGGERED)
                        break

        except Exception as e:
            logger.error(f"Error checking patterns for watcher {watcher.id}: {e}")

        return matches_found

    def _evaluate_condition(self, condition: str, variables: Dict[str, Any]) -> bool:
        """Safely evaluate a condition with variables."""
        try:
            # Create safe evaluation context
            safe_context = {
                "float": float,
                "int": int,
                "str": str,
                "len": len,
                "abs": abs,
                "min": min,
                "max": max,
            }
            safe_context.update(variables)

            # Evaluate condition
            result = eval(condition, {"__builtins__": {}}, safe_context)
            return bool(result)

        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    async def _execute_action(
        self,
        watcher: WatcherInstance,
        action: Any,
        matched_text: str,
        captured_vars: Dict[str, Any],
    ):
        """Execute a watcher action."""
        from .actions import ActionExecutor

        try:
            executor = ActionExecutor()
            success, result = await executor.execute(
                action_type=action.type,
                params=action.params,
                job_id=watcher.job_id,
                hostname=watcher.hostname,
                variables=captured_vars,
            )

            # Log event
            self._log_watcher_event(
                watcher_id=watcher.id,
                job_id=watcher.job_id,
                hostname=watcher.hostname,
                matched_text=matched_text,
                captured_vars=captured_vars,
                action_type=action.type.value,
                action_result=result,
                success=success,
            )

            logger.info(
                f"Executed action {action.type.value} for watcher {watcher.id}: "
                f"success={success}, result={result}"
            )

        except Exception as e:
            logger.error(f"Failed to execute action for watcher {watcher.id}: {e}")

    async def _get_job_info(self, job_id: str, hostname: str) -> Optional[JobInfo]:
        """Get job information."""
        try:
            from ..job_data_manager import get_job_data_manager

            manager = get_job_data_manager()
            job_data = await manager.get_job_data(job_id, hostname)
            return job_data.job_info if job_data else None

        except Exception as e:
            logger.error(f"Failed to get job info for {job_id}: {e}")
            return None

    async def _get_new_output(
        self, job_info: JobInfo, output_type: str, last_position: int
    ) -> Optional[str]:
        """Get new output content since last position."""
        try:
            from ..web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return None

            slurm_host = manager.get_host_by_name(job_info.hostname)
            conn = manager._get_connection(slurm_host.host)

            # Determine which file to read
            if output_type == "stderr" and job_info.stderr_file:
                file_path = job_info.stderr_file
            elif job_info.stdout_file:
                file_path = job_info.stdout_file
            else:
                return None

            # Read from last position (like tail -f)
            result = conn.run(
                f"tail -c +{last_position + 1} '{file_path}' 2>/dev/null || true",
                hide=True,
                warn=True,
            )

            if result.ok and result.stdout:
                return result.stdout

            return None

        except Exception as e:
            logger.error(f"Failed to get output for job {job_info.job_id}: {e}")
            return None

    # Database helper methods

    def _store_watcher(
        self, job_id: str, hostname: str, definition: WatcherDefinition
    ) -> Optional[int]:
        """Store watcher in database."""
        try:
            with self.cache._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO job_watchers 
                    (job_id, hostname, name, pattern, interval_seconds, 
                     captures_json, condition, actions_json, created_at, state)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        hostname,
                        definition.name,
                        definition.pattern,
                        definition.interval_seconds,
                        json.dumps(definition.captures),
                        definition.condition,
                        json.dumps(
                            [
                                {
                                    "type": action.type.value,
                                    "params": action.params,
                                    "condition": action.condition,
                                }
                                for action in definition.actions
                            ]
                        ),
                        datetime.now().isoformat(),
                        WatcherState.ACTIVE.value,
                    ),
                )
                conn.commit()
                return cursor.lastrowid

        except Exception as e:
            logger.error(f"Failed to store watcher: {e}")
            return None

    def _get_watcher(self, watcher_id: int) -> Optional[WatcherInstance]:
        """Get watcher from database."""
        try:
            with self.cache._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
                )
                row = cursor.fetchone()

                if row:
                    from ..models.watcher import ActionType, WatcherAction

                    definition = WatcherDefinition(
                        name=row["name"],
                        pattern=row["pattern"],
                        interval_seconds=row["interval_seconds"],
                        captures=json.loads(row["captures_json"] or "[]"),
                        condition=row["condition"],
                        actions=[
                            WatcherAction(
                                type=ActionType(action_data["type"]),
                                params=action_data.get("params", {}),
                                condition=action_data.get("condition"),
                            )
                            for action_data in json.loads(row["actions_json"] or "[]")
                        ],
                    )

                    instance = WatcherInstance(
                        id=row["id"],
                        job_id=row["job_id"],
                        hostname=row["hostname"],
                        definition=definition,
                        state=WatcherState(row["state"]),
                        last_position=row["last_position"],
                        trigger_count=row["trigger_count"],
                    )

                    # Load variables
                    cursor = conn.execute(
                        "SELECT * FROM watcher_variables WHERE watcher_id = ?",
                        (watcher_id,),
                    )
                    for var_row in cursor.fetchall():
                        instance.variables[var_row["variable_name"]] = var_row[
                            "variable_value"
                        ]

                    return instance

        except Exception as e:
            logger.error(f"Failed to get watcher {watcher_id}: {e}")

        return None

    def _get_watcher_ids_for_job(self, job_id: str, hostname: str) -> List[int]:
        """Get watcher IDs for a job."""
        try:
            with self.cache._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id FROM job_watchers WHERE job_id = ? AND hostname = ?",
                    (job_id, hostname),
                )
                return [row["id"] for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get watcher IDs for job {job_id}: {e}")
            return []

    def _update_watcher_state(self, watcher_id: int, state: WatcherState):
        """Update watcher state."""
        try:
            with self.cache._get_connection() as conn:
                conn.execute(
                    "UPDATE job_watchers SET state = ? WHERE id = ?",
                    (state.value, watcher_id),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update watcher {watcher_id} state: {e}")

    def _update_watcher_position(self, watcher_id: int, position: int):
        """Update watcher last read position."""
        try:
            with self.cache._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE job_watchers 
                    SET last_position = ?, last_check = ?
                    WHERE id = ?
                    """,
                    (position, datetime.now().isoformat(), watcher_id),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update watcher {watcher_id} position: {e}")

    def _update_watcher_trigger_count(self, watcher_id: int, count: int):
        """Update watcher trigger count."""
        try:
            with self.cache._get_connection() as conn:
                conn.execute(
                    "UPDATE job_watchers SET trigger_count = ? WHERE id = ?",
                    (count, watcher_id),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update watcher {watcher_id} trigger count: {e}")

    def _update_watcher_variables(self, watcher_id: int, variables: Dict[str, Any]):
        """Update watcher variables."""
        try:
            with self.cache._get_connection() as conn:
                for name, value in variables.items():
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO watcher_variables
                        (watcher_id, variable_name, variable_value, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (watcher_id, name, str(value), datetime.now().isoformat()),
                    )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update watcher {watcher_id} variables: {e}")

    def _log_watcher_event(
        self,
        watcher_id: int,
        job_id: str,
        hostname: str,
        matched_text: str,
        captured_vars: Dict[str, Any],
        action_type: str,
        action_result: str,
        success: bool,
    ):
        """Log a watcher event."""
        try:
            with self.cache._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO watcher_events
                    (watcher_id, job_id, hostname, timestamp, matched_text,
                     captured_vars_json, action_type, action_result, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        watcher_id,
                        job_id,
                        hostname,
                        datetime.now().isoformat(),
                        matched_text[:1000],  # Limit size
                        json.dumps(captured_vars),
                        action_type,
                        action_result[:1000],  # Limit size
                        success,
                    ),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to log watcher event: {e}")

    async def shutdown(self):
        """Shutdown the watcher engine."""
        self._shutdown = True

        # Cancel all active tasks
        for task in self.active_tasks.values():
            task.cancel()

        # Wait for tasks to complete
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)

        self.active_tasks.clear()
        logger.info("Watcher engine shut down")


# Global instance
_watcher_engine: Optional[WatcherEngine] = None


def get_watcher_engine() -> WatcherEngine:
    """Get or create the global watcher engine."""
    global _watcher_engine
    if _watcher_engine is None:
        _watcher_engine = WatcherEngine()
    return _watcher_engine
