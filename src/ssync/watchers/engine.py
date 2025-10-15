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
        self._pattern_cache: Dict[str, re.Pattern] = {}  # Cache compiled regex patterns

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
                try:
                    await self.active_tasks[watcher_id]
                except asyncio.CancelledError:
                    pass
                del self.active_tasks[watcher_id]

            # Update state in database
            self._update_watcher_state(watcher_id, WatcherState.COMPLETED)

        logger.info(f"Stopped {len(watcher_ids)} watchers for job {job_id}")

    async def cleanup_orphaned_watchers(self):
        """Stop watchers for jobs that no longer exist or have completed."""
        try:
            # Get all active watchers from database
            with self.cache._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, job_id, hostname FROM job_watchers WHERE state = 'active'"
                )
                active_watchers = cursor.fetchall()

            for row in active_watchers:
                watcher_id, job_id, hostname = row

                # Check if job still exists and is active
                job_info = await self._get_job_info(job_id, hostname)

                should_stop = False
                if not job_info:
                    logger.info(
                        f"Job {job_id} not found, stopping orphaned watcher {watcher_id}"
                    )
                    should_stop = True
                elif job_info.state in [
                    JobState.COMPLETED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                    JobState.TIMEOUT,
                    JobState.UNKNOWN,
                ]:
                    logger.info(
                        f"Job {job_id} is {job_info.state}, stopping watcher {watcher_id}"
                    )
                    should_stop = True

                if should_stop:
                    # Cancel task if running
                    if watcher_id in self.active_tasks:
                        self.active_tasks[watcher_id].cancel()
                        try:
                            await self.active_tasks[watcher_id]
                        except asyncio.CancelledError:
                            pass
                        del self.active_tasks[watcher_id]

                    # Update state in database
                    self._update_watcher_state(watcher_id, WatcherState.COMPLETED)

        except Exception as e:
            logger.error(f"Error cleaning up orphaned watchers: {e}")

    async def check_and_restart_watchers(self):
        """Check health of watchers and restart if needed."""
        try:
            # Get all active watchers from database
            with self.cache._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, job_id, hostname, last_check, interval_seconds
                    FROM job_watchers 
                    WHERE state = 'active'
                    """
                )
                watchers = cursor.fetchall()

            for row in watchers:
                watcher_id = row["id"]
                job_id = row["job_id"]
                hostname = row["hostname"]
                last_check = row["last_check"]
                interval = row["interval_seconds"]

                # Check if watcher task is running
                if (
                    watcher_id not in self.active_tasks
                    or self.active_tasks[watcher_id].done()
                ):
                    # Task is not running or has finished

                    # Check if it should still be running
                    job_info = await self._get_job_info(job_id, hostname)
                    if job_info and job_info.state in [
                        JobState.RUNNING,
                        JobState.PENDING,
                    ]:
                        logger.warning(
                            f"Watcher {watcher_id} for job {job_id} is not running, restarting..."
                        )

                        # Restart the watcher
                        task = asyncio.create_task(
                            self._monitor_watcher(watcher_id, job_id, hostname)
                        )
                        self.active_tasks[watcher_id] = task

                # Check if watcher is stale (hasn't checked in too long)
                if last_check:
                    last_check_time = datetime.fromisoformat(last_check)
                    time_since_check = (
                        datetime.now() - last_check_time
                    ).total_seconds()

                    # If hasn't checked in 3x the interval, might be stuck
                    if time_since_check > interval * 3:
                        logger.warning(
                            f"Watcher {watcher_id} hasn't checked in {time_since_check:.0f}s "
                            f"(expected every {interval}s)"
                        )

        except Exception as e:
            logger.error(f"Error checking watcher health: {e}")

    async def _monitor_watcher(self, watcher_id: int, job_id: str, hostname: str):
        """Monitor a single watcher."""
        backoff_factor = 1.0
        consecutive_failures = 0
        last_action_time = datetime.now()
        action_count_in_window = 0
        rate_limit_window = 60  # 1 minute window
        max_actions_per_window = 10  # Max 10 actions per minute

        # Initial delay to let job start and produce some output
        initial_delay = 5  # seconds
        logger.info(f"Watcher {watcher_id} waiting {initial_delay}s before first check")
        await asyncio.sleep(initial_delay)

        try:
            while not self._shutdown:
                try:
                    # Get watcher details from database (fresh state each iteration)
                    watcher = self._get_watcher(watcher_id)
                    if not watcher or watcher.state != WatcherState.ACTIVE:
                        break

                    # Update last check timestamp
                    self._update_watcher_last_check(watcher_id)

                    # Check if job is still active
                    job_info = await self._get_job_info(job_id, hostname)
                    if not job_info:
                        logger.info(
                            f"Job {job_id} not found, stopping watcher {watcher_id}"
                        )
                        self._update_watcher_state(watcher_id, WatcherState.COMPLETED)
                        break

                    # Check if job has finished (any terminal state)
                    if job_info.state in [
                        JobState.COMPLETED,
                        JobState.FAILED,
                        JobState.CANCELLED,
                        JobState.TIMEOUT,
                        JobState.UNKNOWN,
                    ]:
                        logger.info(
                            f"Job {job_id} finished with state {job_info.state}, stopping watcher {watcher_id}"
                        )
                        self._update_watcher_state(watcher_id, WatcherState.COMPLETED)
                        break

                    # Check if watcher is in timer mode
                    if watcher.timer_mode_active:
                        logger.debug(
                            f"Timer mode active for watcher {watcher_id}, executing actions"
                        )

                        # Rate limiting check
                        now = datetime.now()
                        if (now - last_action_time).total_seconds() > rate_limit_window:
                            action_count_in_window = 0
                            last_action_time = now

                        if action_count_in_window >= max_actions_per_window:
                            logger.warning(
                                f"Rate limit reached for watcher {watcher_id}, skipping actions"
                            )
                            await asyncio.sleep(
                                watcher.definition.timer_interval_seconds
                            )
                            continue

                        # Timer mode: execute actions periodically using cached variables
                        # Reload variables from database for consistency
                        fresh_variables = self._get_watcher_variables(watcher_id)

                        actions_executed = 0
                        for action in watcher.definition.actions:
                            # Check action-specific condition
                            if action.condition:
                                if not self._evaluate_condition(
                                    action.condition, fresh_variables
                                ):
                                    continue

                            # Execute action with fresh variables and track result
                            try:
                                success, result = await self._execute_action(
                                    watcher, action, "", fresh_variables
                                )
                                if success:
                                    actions_executed += 1
                                    action_count_in_window += 1
                                logger.debug(f"Timer action result: {result}")
                            except Exception as e:
                                logger.error(f"Failed to execute timer action: {e}")

                        # Update trigger count for timer mode (increment from current database value)
                        new_trigger_count = watcher.trigger_count + 1
                        self._update_watcher_trigger_count(
                            watcher.id, new_trigger_count
                        )

                        # Check max triggers in timer mode
                        if watcher.definition.max_triggers:
                            if new_trigger_count >= watcher.definition.max_triggers:
                                logger.info(
                                    f"Timer mode watcher {watcher_id} reached max triggers "
                                    f"({watcher.definition.max_triggers}), disabling"
                                )
                                self._update_watcher_state(
                                    watcher_id, WatcherState.TRIGGERED
                                )
                                break

                        # Sleep for timer interval
                        logger.debug(
                            f"Timer mode watcher {watcher_id} sleeping for {watcher.definition.timer_interval_seconds}s"
                        )
                        await asyncio.sleep(watcher.definition.timer_interval_seconds)

                    else:
                        # Pattern matching mode
                        # Get new output content
                        new_content = await self._get_new_output(
                            job_info,
                            watcher.definition.output_type,
                            watcher.last_position,
                        )

                        if new_content:
                            # Update last position
                            new_position = watcher.last_position + len(
                                new_content.encode()
                            )
                            self._update_watcher_position(watcher_id, new_position)

                            # Check for pattern matches
                            matches_found = self._check_patterns(watcher, new_content)

                            if matches_found:
                                # Reset backoff on successful match
                                backoff_factor = 1.0
                                consecutive_failures = 0

                                # Switch to timer mode if enabled
                                if watcher.definition.timer_mode_enabled:
                                    watcher.timer_mode_active = True
                                    self._update_watcher_timer_mode(watcher_id, True)
                                    logger.info(
                                        f"Watcher {watcher_id} switched to timer mode after pattern match"
                                    )
                            else:
                                # No matches, increase backoff slightly
                                backoff_factor = min(backoff_factor * 1.1, 5.0)

                        # Sleep with backoff for pattern matching mode
                        sleep_time = (
                            watcher.definition.interval_seconds * backoff_factor
                        )
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
            # Use cached compiled regex if available
            if pattern not in self._pattern_cache:
                try:
                    self._pattern_cache[pattern] = re.compile(pattern, re.MULTILINE)
                except re.error as e:
                    logger.error(f"Invalid regex pattern '{pattern}': {e}")
                    return False

            regex = self._pattern_cache[pattern]

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

                # Trigger actions (with rate limiting)
                for action in watcher.definition.actions:
                    # Check action-specific condition
                    if action.condition:
                        if not self._evaluate_condition(
                            action.condition, watcher.variables
                        ):
                            continue

                    # Execute action and track results properly
                    try:
                        # Create task but also track it for cleanup
                        task = asyncio.create_task(
                            self._execute_action(
                                watcher, action, matched_text, captured_vars
                            )
                        )
                        # Store task reference for potential cleanup
                        if not hasattr(self, "_action_tasks"):
                            self._action_tasks = []
                        self._action_tasks.append(task)
                    except Exception as e:
                        logger.error(f"Failed to create action task: {e}")

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
            # Include matched text in variables for $0 substitution
            variables_with_match = {"_matched_text": matched_text, **captured_vars}
            success, result = await executor.execute(
                action_type=action.type,
                params=action.params,
                job_id=watcher.job_id,
                hostname=watcher.hostname,
                variables=variables_with_match,
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

            return success, result

        except Exception as e:
            logger.error(f"Failed to execute action for watcher {watcher.id}: {e}")
            return False, f"Error: {e}"

    async def execute_timer_actions(self, watcher_id: int) -> tuple[bool, str]:
        """
        Manually execute timer mode actions for a watcher.
        Used for manual triggers from the UI.

        Returns:
            Tuple of (success, message)
        """
        try:
            # Get watcher instance
            watcher = self._get_watcher(watcher_id)
            if not watcher:
                return False, "Watcher not found"

            # Check if watcher is in timer mode
            if not watcher.timer_mode_active:
                return False, "Watcher is not in timer mode"

            # Get fresh variables from database
            fresh_variables = self._get_watcher_variables(watcher_id)

            actions_executed = 0
            action_results = []

            for action in watcher.definition.actions:
                # Check action-specific condition
                if action.condition:
                    if not self._evaluate_condition(action.condition, fresh_variables):
                        continue

                # Execute action with fresh variables
                try:
                    success, result = await self._execute_action(
                        watcher, action, "[Manual Timer Trigger]", fresh_variables
                    )
                    if success:
                        actions_executed += 1
                        action_results.append(f"{action.type.value}: {result}")
                    else:
                        action_results.append(f"{action.type.value}: Failed - {result}")
                except Exception as e:
                    logger.error(f"Failed to execute timer action: {e}")
                    action_results.append(f"{action.type.value}: Error - {str(e)}")

            # Update trigger count
            new_trigger_count = watcher.trigger_count + 1
            self._update_watcher_trigger_count(watcher.id, new_trigger_count)

            # Check max triggers
            if watcher.definition.max_triggers:
                if new_trigger_count >= watcher.definition.max_triggers:
                    self._update_watcher_state(watcher.id, WatcherState.TRIGGERED)
                    action_results.append("Max triggers reached - watcher disabled")

            if actions_executed > 0:
                result_msg = f"Executed {actions_executed} timer action(s): "
                result_msg += "; ".join(action_results)
                return True, result_msg
            else:
                return True, "No timer actions met conditions for execution"

        except Exception as e:
            logger.error(f"Error executing timer actions for watcher {watcher_id}: {e}")
            return False, f"Error: {str(e)}"

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

            # First check if file exists and get its size
            size_result = conn.run(
                f"stat -c %s '{file_path}' 2>/dev/null || echo 0",
                hide=True,
                warn=True,
            )

            if size_result.ok:
                try:
                    file_size = int(size_result.stdout.strip())

                    # Handle file rotation/truncation
                    if file_size < last_position:
                        logger.warning(
                            f"File {file_path} was truncated/rotated "
                            f"(size={file_size} < position={last_position}), resetting position"
                        )
                        last_position = 0
                        # Note: Position will be updated by caller

                    # Don't read if we're at the end
                    if file_size == last_position:
                        return None

                except ValueError:
                    pass

            # Read from last position (like tail -f)
            # Limit read size to prevent memory issues
            max_read_size = 1024 * 1024  # 1MB max per read
            result = conn.run(
                f"tail -c +{last_position + 1} '{file_path}' 2>/dev/null | head -c {max_read_size}",
                hide=True,
                warn=True,
            )

            if result.ok and result.stdout:
                # Filter out binary data
                try:
                    # Try to decode as UTF-8, replace invalid chars
                    clean_output = result.stdout.encode("utf-8", "ignore").decode(
                        "utf-8", "ignore"
                    )
                    return clean_output
                except Exception:
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
                     captures_json, condition, actions_json, created_at, state,
                     timer_mode_enabled, timer_interval_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        1 if definition.timer_mode_enabled else 0,
                        definition.timer_interval_seconds,
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
                        timer_mode_enabled=bool(
                            row["timer_mode_enabled"]
                            if "timer_mode_enabled" in row.keys()
                            else 0
                        ),
                        timer_interval_seconds=row["timer_interval_seconds"]
                        if "timer_interval_seconds" in row.keys()
                        else 30,
                    )

                    instance = WatcherInstance(
                        id=row["id"],
                        job_id=row["job_id"],
                        hostname=row["hostname"],
                        definition=definition,
                        state=WatcherState(row["state"]),
                        last_position=row["last_position"],
                        trigger_count=row["trigger_count"],
                        timer_mode_active=bool(
                            row["timer_mode_active"]
                            if "timer_mode_active" in row.keys()
                            else 0
                        ),
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

    def _update_watcher_timer_mode(self, watcher_id: int, timer_mode_active: bool):
        """Update watcher timer mode state."""
        try:
            with self.cache._get_connection() as conn:
                conn.execute(
                    "UPDATE job_watchers SET timer_mode_active = ? WHERE id = ?",
                    (1 if timer_mode_active else 0, watcher_id),
                )
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update watcher {watcher_id} timer mode: {e}")

    def _update_watcher_last_check(self, watcher_id: int):
        """Update watcher last check timestamp."""
        try:
            with self.cache._get_connection() as conn:
                conn.execute(
                    "UPDATE job_watchers SET last_check = ? WHERE id = ?",
                    (datetime.now().isoformat(), watcher_id),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update watcher {watcher_id} last check: {e}")

    def _get_watcher_variables(self, watcher_id: int) -> Dict[str, Any]:
        """Get watcher variables from database."""
        try:
            with self.cache._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT variable_name, variable_value FROM watcher_variables WHERE watcher_id = ?",
                    (watcher_id,),
                )
                return {
                    row["variable_name"]: row["variable_value"]
                    for row in cursor.fetchall()
                }
        except Exception as e:
            logger.error(f"Failed to get watcher {watcher_id} variables: {e}")
            return {}

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
