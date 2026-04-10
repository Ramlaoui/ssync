"""Watcher-related orchestration helpers used by web routes."""

import gzip
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ...models.job import JobState
from ...utils.async_helpers import create_task
from ...utils.logging import setup_logger

logger = setup_logger(__name__)
FINISHED_JOB_STATES = {
    JobState.COMPLETED,
    JobState.FAILED,
    JobState.CANCELLED,
    JobState.TIMEOUT,
    JobState.UNKNOWN,
}


def format_watcher_name(watcher_id: int, name: Optional[str]) -> str:
    return name or f"watcher_{watcher_id}"


def parse_json_field(raw_value: Optional[str], default):
    return json.loads(raw_value) if raw_value else default


def serialize_watcher_actions(actions: List[Dict[str, Any]]) -> str:
    formatted_actions = []
    for action in actions:
        formatted_action = {"type": action["type"]}
        if action.get("condition"):
            formatted_action["condition"] = action["condition"]
        if action.get("params"):
            formatted_action["params"] = action["params"]
        elif action.get("config"):
            formatted_action["params"] = action["config"]
        formatted_actions.append(formatted_action)
    return json.dumps(formatted_actions)


def serialize_watcher_captures(watcher_config: Dict[str, Any]) -> str:
    return json.dumps(
        watcher_config.get("captures", watcher_config.get("capture_groups", []))
    )


def format_api_actions(actions_json: Optional[str]) -> List[Dict[str, Any]]:
    if not actions_json:
        return []

    formatted_actions = []
    for action in json.loads(actions_json):
        formatted_action = {"type": action["type"]}
        if action.get("condition"):
            formatted_action["condition"] = action["condition"]
        if action.get("params"):
            formatted_action["config"] = action["params"]
        formatted_actions.append(formatted_action)
    return formatted_actions


def format_watcher_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    response = {
        "id": row_dict["id"],
        "job_id": row_dict["job_id"],
        "hostname": row_dict["hostname"],
        "name": format_watcher_name(row_dict["id"], row_dict.get("name")),
        "pattern": row_dict["pattern"],
        "interval_seconds": row_dict["interval_seconds"],
        "state": row_dict["state"],
        "trigger_count": row_dict["trigger_count"],
        "last_check": row_dict.get("last_check"),
        "last_position": row_dict.get("last_position"),
        "created_at": row_dict.get("created_at"),
        "timer_mode_enabled": bool(row_dict.get("timer_mode_enabled", 0)),
        "timer_interval_seconds": row_dict.get("timer_interval_seconds", 30),
        "timer_mode_active": bool(row_dict.get("timer_mode_active", 0)),
        "trigger_on_job_end": bool(row_dict.get("trigger_on_job_end", 0)),
        "trigger_job_states": parse_json_field(
            row_dict.get("trigger_job_states_json"), []
        ),
        "is_array_template": bool(row_dict.get("is_array_template", 0)),
        "array_spec": row_dict.get("array_spec"),
        "parent_watcher_id": row_dict.get("parent_watcher_id"),
        "discovered_task_count": row_dict.get("discovered_task_count", 0),
        "expected_task_count": row_dict.get("expected_task_count"),
        "captures": parse_json_field(row_dict.get("captures_json"), []),
        "actions": format_api_actions(row_dict.get("actions_json")),
    }

    if row_dict.get("condition"):
        response["condition"] = row_dict["condition"]

    return response


def cancel_watcher_task(watcher_id: int) -> None:
    try:
        from ...watchers import get_watcher_engine

        engine = get_watcher_engine()
        if hasattr(engine, "active_tasks") and watcher_id in engine.active_tasks:
            engine.active_tasks[watcher_id].cancel()
            del engine.active_tasks[watcher_id]
    except Exception as exc:
        logger.debug(f"Could not cancel watcher task {watcher_id}: {exc}")


def start_watcher_task(watcher_id: int, job_id: str, hostname: str) -> None:
    try:
        from ...watchers import get_watcher_engine

        engine = get_watcher_engine()
        if hasattr(engine, "active_tasks"):
            task = create_task(engine._monitor_watcher(watcher_id, job_id, hostname))
            engine.active_tasks[watcher_id] = task
    except Exception as exc:
        logger.debug(f"Could not start watcher task {watcher_id}: {exc}")


def decode_cached_output(
    compressed_data: Optional[bytes], compression: str, output_type: str
) -> str:
    if not compressed_data:
        return ""

    try:
        if compression == "gzip":
            return gzip.decompress(compressed_data).decode("utf-8")
        return compressed_data.decode("utf-8")
    except Exception as exc:
        logger.warning(f"Failed to decompress cached {output_type}: {exc}")
        return ""


def decode_cached_job_outputs(cached_job) -> tuple[str, str]:
    return (
        decode_cached_output(
            cached_job.stdout_compressed,
            cached_job.stdout_compression,
            "stdout",
        ),
        decode_cached_output(
            cached_job.stderr_compressed,
            cached_job.stderr_compression,
            "stderr",
        ),
    )


def read_remote_output(conn, file_path: Optional[str], output_type: str) -> str:
    if not conn or not file_path:
        return ""

    try:
        result = conn.run(f"cat '{file_path}'", warn=True, hide=True)
        if result.ok:
            content = result.stdout
            logger.info(f"Fetched {output_type} from Slurm: {len(content)} chars")
            return content
    except Exception as exc:
        logger.warning(f"Failed to fetch {output_type} from Slurm: {exc}")
    return ""


def fetch_job_outputs_from_slurm(
    *, get_slurm_manager, hostname: str, job_id: str
) -> tuple[str, str]:
    try:
        logger.info(f"Cache empty, fetching output from Slurm for job {job_id}")
        manager = get_slurm_manager()
        job_info = manager.get_job_info(hostname, job_id)
        if not job_info:
            return "", ""

        try:
            slurm_host = manager.get_host_by_name(hostname)
            conn = manager._get_connection(slurm_host.host)
        except Exception as exc:
            logger.warning(f"Failed to get connection for {hostname}: {exc}")
            return "", ""

        return (
            read_remote_output(conn, job_info.stdout_file, "stdout"),
            read_remote_output(conn, job_info.stderr_file, "stderr"),
        )
    except Exception as exc:
        logger.warning(f"Failed to fetch output from Slurm: {exc}")
        return "", ""


def load_watcher_output_text(
    *, get_slurm_manager, cache, job_id: str, hostname: str, watcher_id: int
) -> tuple[str, str]:
    cached_job = cache.get_cached_job(job_id, hostname)
    if cached_job and (cached_job.stdout_compressed or cached_job.stderr_compressed):
        stdout_content, stderr_content = decode_cached_job_outputs(cached_job)
        logger.info(
            f"Using cached output for watcher {watcher_id} - "
            f"stdout: {len(stdout_content)} chars, stderr: {len(stderr_content)} chars"
        )
        if stdout_content or stderr_content:
            return stdout_content, stderr_content

    return fetch_job_outputs_from_slurm(
        get_slurm_manager=get_slurm_manager,
        hostname=hostname,
        job_id=job_id,
    )


def select_watcher_content(
    output_type: str, stdout_content: str, stderr_content: str
) -> str:
    if output_type == "stdout":
        return stdout_content
    if output_type == "stderr":
        return stderr_content
    return stdout_content + "\n" + stderr_content


def resolve_initial_watcher_state(
    *,
    get_slurm_manager,
    job_id: str,
    hostname: str,
    requested_state: str,
) -> str:
    try:
        manager = get_slurm_manager()
        job_info = manager.get_job_info(hostname, job_id)
        logger.info(
            f"Checking job {job_id} state for watcher creation - "
            f"job_info: {job_info}, state: {job_info.state if job_info else 'None'}"
        )
        if not job_info:
            logger.info(
                f"Job {job_id} not found in queue - creating STATIC watcher "
                "(job likely completed)"
            )
            return "static"

        if job_info.state in FINISHED_JOB_STATES:
            logger.info(
                f"Creating STATIC watcher for finished job {job_id} "
                f"(state: {job_info.state.value})"
            )
            return "static"

        logger.info(
            f"Creating {requested_state.upper()} watcher for job {job_id} "
            f"(state: {job_info.state.value})"
        )
        return requested_state
    except Exception as exc:
        logger.warning(
            f"Could not determine job state for {job_id}: {exc} - defaulting to STATIC"
        )
        return "static"


def build_watcher_update_fields(
    watcher_update: Dict[str, Any],
) -> tuple[List[str], List[Any]]:
    update_fields: List[str] = []
    update_values: List[Any] = []

    direct_fields = (
        "name",
        "pattern",
        "interval_seconds",
        "condition",
        "timer_interval_seconds",
    )
    for field in direct_fields:
        if field in watcher_update:
            update_fields.append(f"{field} = ?")
            update_values.append(watcher_update[field])

    if "captures" in watcher_update or "capture_groups" in watcher_update:
        update_fields.append("captures_json = ?")
        update_values.append(serialize_watcher_captures(watcher_update))
    if "actions" in watcher_update:
        update_fields.append("actions_json = ?")
        update_values.append(serialize_watcher_actions(watcher_update["actions"]))
    if "timer_mode_enabled" in watcher_update:
        update_fields.append("timer_mode_enabled = ?")
        update_values.append(1 if watcher_update["timer_mode_enabled"] else 0)

    return update_fields, update_values


def get_job_watchers_payload(
    *, cache, job_id: str, host: Optional[str]
) -> Dict[str, Any]:
    watchers = []
    watcher_ids = []

    with cache._get_connection() as conn:
        query = """
            SELECT id, job_id, hostname, name, pattern, interval_seconds,
                   captures_json, condition, actions_json, state,
                   trigger_count, last_check, last_position, created_at,
                   timer_mode_enabled, timer_interval_seconds, timer_mode_active,
                   trigger_on_job_end, trigger_job_states_json,
                   is_array_template, array_spec, parent_watcher_id,
                   discovered_task_count, expected_task_count
            FROM job_watchers
            WHERE job_id = ?
        """
        params = [job_id]
        if host:
            query += " AND hostname = ?"
            params.append(host)

        for row in conn.execute(query, params).fetchall():
            row_dict = dict(row)
            watchers.append(format_watcher_row(row_dict))
            watcher_ids.append(row["id"])

        if watcher_ids:
            placeholders = ",".join("?" * len(watcher_ids))
            var_cursor = conn.execute(
                f"""
                SELECT watcher_id, variable_name, variable_value
                FROM watcher_variables
                WHERE watcher_id IN ({placeholders})
                """,
                watcher_ids,
            )

            variables_by_watcher: Dict[int, Dict[str, str]] = {}
            for var_row in var_cursor.fetchall():
                variables_by_watcher.setdefault(var_row["watcher_id"], {})[
                    var_row["variable_name"]
                ] = var_row["variable_value"]

            for watcher in watchers:
                watcher["variables"] = variables_by_watcher.get(watcher["id"], {})

    return {"job_id": job_id, "watchers": watchers, "count": len(watchers)}


def get_all_watchers_payload(
    *, cache, state: Optional[str], limit: int
) -> Dict[str, Any]:
    with cache._get_connection() as conn:
        query = """
            SELECT w.*, j.hostname
            FROM job_watchers w
            LEFT JOIN cached_jobs j ON w.job_id = j.job_id
            WHERE 1=1
        """
        params = []
        if state:
            query += " AND w.state = ?"
            params.append(state)
        query += " ORDER BY w.created_at DESC LIMIT ?"
        params.append(limit)

        watchers = [
            format_watcher_row(dict(row))
            for row in conn.execute(query, params).fetchall()
        ]
    return {"watchers": watchers}


def get_watcher_events_payload(
    *, cache, job_id: Optional[str], watcher_id: Optional[int], limit: int
) -> Dict[str, Any]:
    events = []
    with cache._get_connection() as conn:
        query = """
            SELECT e.*, w.name as watcher_name, w.pattern
            FROM watcher_events e
            LEFT JOIN job_watchers w ON e.watcher_id = w.id
            WHERE 1=1
        """
        params = []
        if job_id:
            query += " AND e.job_id = ?"
            params.append(job_id)
        if watcher_id:
            query += " AND e.watcher_id = ?"
            params.append(watcher_id)
        query += f" ORDER BY e.timestamp DESC LIMIT {min(limit, 500)}"

        for row in conn.execute(query, params).fetchall():
            events.append(
                {
                    "id": row["id"],
                    "watcher_id": row["watcher_id"],
                    "watcher_name": format_watcher_name(
                        row["watcher_id"], row["watcher_name"]
                    ),
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "timestamp": row["timestamp"],
                    "matched_text": row["matched_text"],
                    "captured_vars": parse_json_field(
                        row["captured_vars_json"], {}
                    ),
                    "action_type": row["action_type"],
                    "action_result": row["action_result"],
                    "success": bool(row["success"]),
                }
            )
    return {"events": events, "count": len(events)}


def get_watcher_stats_payload(*, cache) -> Dict[str, Any]:
    with cache._get_connection() as conn:
        total_watchers = conn.execute(
            "SELECT COUNT(*) as count FROM job_watchers"
        ).fetchone()["count"]

        watchers_by_state = {
            row["state"]: row["count"]
            for row in conn.execute(
                """
                SELECT state, COUNT(*) as count
                FROM job_watchers
                GROUP BY state
                """
            ).fetchall()
        }

        total_events = conn.execute(
            "SELECT COUNT(*) as count FROM watcher_events"
        ).fetchone()["count"]

        events_by_action = {}
        for row in conn.execute(
            """
            SELECT action_type, COUNT(*) as count,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count
            FROM watcher_events
            GROUP BY action_type
            """
        ).fetchall():
            events_by_action[row["action_type"]] = {
                "total": row["count"],
                "success": row["success_count"],
                "failed": row["count"] - row["success_count"],
            }

        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        events_last_hour = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM watcher_events
            WHERE timestamp > ?
            """,
            (one_hour_ago,),
        ).fetchone()["count"]

        top_watchers = [
            {
                "watcher_id": row["id"],
                "job_id": row["job_id"],
                "name": format_watcher_name(row["id"], row["name"]),
                "event_count": row["event_count"],
            }
            for row in conn.execute(
                """
                SELECT w.id, w.job_id, w.name, COUNT(e.id) as event_count
                FROM job_watchers w
                LEFT JOIN watcher_events e ON w.id = e.watcher_id
                GROUP BY w.id
                HAVING event_count > 0
                ORDER BY event_count DESC
                LIMIT 10
                """
            ).fetchall()
        ]

    return {
        "total_watchers": total_watchers,
        "watchers_by_state": watchers_by_state,
        "total_events": total_events,
        "events_by_action": events_by_action,
        "events_last_hour": events_last_hour,
        "top_watchers": top_watchers,
    }


async def cleanup_orphaned_watchers_payload(
    *, cache, dry_run: bool
) -> Dict[str, Any]:
    from ...watchers import get_watcher_engine

    engine = get_watcher_engine()
    if dry_run:
        with cache._get_connection() as conn:
            active_watchers = [
                {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "state": row["state"],
                    "name": row["name"],
                }
                for row in conn.execute(
                    """
                    SELECT w.id, w.job_id, w.hostname, w.state, w.name
                    FROM job_watchers w
                    WHERE w.state = 'active'
                    """
                ).fetchall()
            ]
        return {
            "dry_run": True,
            "active_watchers": active_watchers,
            "count": len(active_watchers),
        }

    await engine.cleanup_orphaned_watchers()
    return {"message": "Cleanup completed", "dry_run": False}


def pause_watcher(*, cache, watcher_id: int) -> Dict[str, Any]:
    with cache._get_connection() as conn:
        row = conn.execute(
            "SELECT state FROM job_watchers WHERE id = ?", (watcher_id,)
        ).fetchone()
        if not row:
            raise ValueError("Watcher not found")
        if row["state"] != "active":
            return {
                "message": f"Watcher {watcher_id} is not active (current state: {row['state']})"
            }

        conn.execute(
            "UPDATE job_watchers SET state = 'paused' WHERE id = ?",
            (watcher_id,),
        )
        conn.commit()

    cancel_watcher_task(watcher_id)
    return {"message": f"Watcher {watcher_id} paused successfully"}


async def trigger_watcher_manually_payload(
    *,
    cache,
    get_slurm_manager,
    watcher_id: int,
    test_text: Optional[str],
) -> Dict[str, Any]:
    from ...models.watcher import WatcherState
    from ...watchers.engine import get_watcher_engine

    engine = get_watcher_engine()
    with cache._get_connection() as conn:
        watcher_row = conn.execute(
            """
            SELECT w.*
            FROM job_watchers w
            WHERE w.id = ?
            """,
            (watcher_id,),
        ).fetchone()
        if not watcher_row:
            raise ValueError("Watcher not found")

    watcher = engine._get_watcher(watcher_id)
    if not watcher:
        raise ValueError("Watcher not found in database")
    if watcher.state not in [WatcherState.ACTIVE, WatcherState.STATIC]:
        raise RuntimeError(
            f"Watcher is in {watcher.state.value} state. "
            "It must be ACTIVE or STATIC to trigger manually."
        )

    if watcher.timer_mode_active:
        logger.info(f"Watcher {watcher_id} is in timer mode, executing timer actions")
        success, message = await engine.execute_timer_actions(watcher_id)
        return {
            "success": success,
            "message": message,
            "matches": success,
            "timer_mode": True,
        }

    if test_text:
        content = test_text
        logger.info(f"Manually triggering watcher {watcher_id} with test text")
    else:
        stdout_content, stderr_content = load_watcher_output_text(
            get_slurm_manager=get_slurm_manager,
            cache=cache,
            job_id=watcher_row["job_id"],
            hostname=watcher_row["hostname"],
            watcher_id=watcher_id,
        )
        output_type = (
            watcher.definition.output_type
            if hasattr(watcher.definition, "output_type")
            else "stdout"
        )
        content = select_watcher_content(output_type, stdout_content, stderr_content)

        if content:
            lines = content.split("\n")
            logger.info(
                f"Triggering watcher {watcher_id} with job output "
                f"({len(lines)} lines, {len(content)} chars)"
            )
        else:
            content = ""
            logger.warning(
                f"No output found for job {watcher_row['job_id']} "
                f"on {watcher_row['hostname']} (cache and Slurm both empty)"
            )

    if not content:
        return {
            "success": False,
            "message": (
                f"No output available for job {watcher_row['job_id']}. "
                "The job output may not be cached yet or the output files may not be accessible."
            ),
            "matches": False,
            "timer_mode": False,
        }

    matches_found = engine._check_patterns(watcher, content)
    if matches_found:
        if watcher.definition.timer_mode_enabled and not watcher.timer_mode_active:
            engine._update_watcher_timer_mode(watcher_id, True)
            logger.info(
                f"Watcher {watcher_id} switched to timer mode after manual pattern match"
            )

        pattern = watcher.definition.pattern
        if pattern in engine._pattern_cache:
            regex = engine._pattern_cache[pattern]
            match_count = len(list(regex.finditer(content)))
        else:
            match_count = 1

        return {
            "success": True,
            "message": f"Found {match_count} match(es) and executed actions",
            "matches": True,
            "match_count": match_count,
            "timer_mode": False,
        }

    lines = content.split("\n")
    return {
        "success": True,
        "message": (
            f"No matches found (searched {len(lines)} lines, {len(content)} chars)"
        ),
        "matches": False,
        "timer_mode": False,
    }


def resume_watcher(*, cache, watcher_id: int) -> Dict[str, Any]:
    with cache._get_connection() as conn:
        row = conn.execute(
            "SELECT job_id, hostname, state FROM job_watchers WHERE id = ?",
            (watcher_id,),
        ).fetchone()
        if not row:
            raise ValueError("Watcher not found")
        if row["state"] != "paused":
            return {
                "message": f"Watcher {watcher_id} is not paused (current state: {row['state']})"
            }

        conn.execute(
            "UPDATE job_watchers SET state = 'active' WHERE id = ?",
            (watcher_id,),
        )
        conn.commit()

    start_watcher_task(watcher_id, row["job_id"], row["hostname"])
    return {"message": f"Watcher {watcher_id} resumed successfully"}


async def discover_array_tasks_payload(*, watcher_id: int) -> Dict[str, Any]:
    from ...watchers import get_watcher_engine

    engine = get_watcher_engine()
    watcher = engine._get_watcher(watcher_id)
    if not watcher:
        raise ValueError("Watcher not found")
    if not watcher.definition.is_array_template:
        return {
            "success": False,
            "message": "This watcher is not an array template watcher",
            "is_array_template": False,
        }

    new_tasks_count = await engine.discover_and_spawn_array_tasks(watcher_id)
    updated_watcher = engine._get_watcher(watcher_id)
    return {
        "success": True,
        "message": f"Discovered {new_tasks_count} new array task(s)",
        "new_tasks_discovered": new_tasks_count,
        "total_discovered": updated_watcher.discovered_task_count
        if updated_watcher
        else 0,
        "expected_tasks": updated_watcher.expected_task_count
        if updated_watcher
        else None,
        "is_array_template": True,
    }


def create_watcher(*, cache, watcher_config: Dict[str, Any], get_slurm_manager):
    required_fields = ["job_id", "hostname", "name", "pattern"]
    for field in required_fields:
        if field not in watcher_config:
            raise ValueError(f"Missing required field: {field}")

    with cache._get_connection() as conn:
        name = watcher_config["name"]
        pattern = watcher_config["pattern"]
        job_id = watcher_config["job_id"]
        hostname = watcher_config["hostname"]
        interval_seconds = watcher_config.get("interval_seconds", 30)
        captures_json = serialize_watcher_captures(watcher_config)
        condition = watcher_config.get("condition")
        timer_mode_enabled = watcher_config.get("timer_mode_enabled", False)
        state = resolve_initial_watcher_state(
            get_slurm_manager=get_slurm_manager,
            job_id=job_id,
            hostname=hostname,
            requested_state=watcher_config.get("state", "active"),
        )
        timer_interval_seconds = watcher_config.get(
            "timer_interval_seconds", interval_seconds
        )

        cursor = conn.execute(
            """
            INSERT INTO job_watchers (
                job_id, hostname, name, pattern, interval_seconds,
                captures_json, condition, actions_json, state,
                last_check, last_position, trigger_count, created_at,
                timer_mode_enabled, timer_interval_seconds, timer_mode_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                hostname,
                name,
                pattern,
                interval_seconds,
                captures_json,
                condition,
                serialize_watcher_actions(watcher_config.get("actions", [])),
                state,
                None,
                0,
                0,
                datetime.now().isoformat(),
                1 if timer_mode_enabled else 0,
                timer_interval_seconds,
                0,
            ),
        )
        watcher_id = cursor.lastrowid
        conn.commit()

        if state == "active":
            start_watcher_task(watcher_id, job_id, hostname)
        else:
            logger.info(
                f"Created static watcher {watcher_id} - will only run on manual trigger"
            )

        created_row = conn.execute(
            "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
        ).fetchone()
        return format_watcher_row(dict(created_row))


def build_watcher_definitions(
    *, watchers: List[Dict[str, Any]], job_id: str
):
    from ...models.watcher import ActionType, WatcherAction, WatcherDefinition

    watcher_defs = []
    for watcher_definition in watchers:
        actions = []
        for action in watcher_definition.get("actions", []):
            action_type_str = (
                action["type"].upper()
                if isinstance(action["type"], str)
                else action["type"]
            )
            try:
                action_type = ActionType[action_type_str]
            except KeyError:
                action_type = ActionType(action_type_str.lower())

            actions.append(
                WatcherAction(
                    type=action_type,
                    params=action.get("params", {}),
                )
            )

        watcher_defs.append(
            WatcherDefinition(
                name=watcher_definition.get("name", f"watcher_{job_id}"),
                pattern=watcher_definition.get("pattern", ""),
                interval_seconds=watcher_definition.get("interval_seconds", 60),
                captures=watcher_definition.get(
                    "captures",
                    watcher_definition.get("capture_groups", []),
                ),
                condition=watcher_definition.get("condition"),
                actions=actions,
                max_triggers=watcher_definition.get("max_triggers", 10),
                output_type=watcher_definition.get("output_type", "stdout"),
                timer_mode_enabled=watcher_definition.get(
                    "timer_mode_enabled", False
                ),
                timer_interval_seconds=watcher_definition.get(
                    "timer_interval_seconds", 60
                ),
            )
        )
    return watcher_defs


async def attach_watchers_to_job_payload(
    *,
    get_slurm_manager,
    job_id: str,
    host: str,
    watchers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    from ...watchers import get_watcher_engine

    manager = get_slurm_manager()
    try:
        slurm_host = manager.get_host_by_name(host)
    except Exception as exc:
        logger.error(f"Error getting host {host}: {exc}")
        raise ValueError(f"Unknown host: {host}") from exc

    try:
        job_info = manager.get_job_info(slurm_host, job_id)
        if not job_info:
            raise LookupError(f"Job {job_id} not found on {host}")
    except LookupError:
        raise
    except Exception as exc:
        logger.error(f"Error getting job info for {job_id}: {exc}")
        raise RuntimeError(f"Error checking job status: {str(exc)}") from exc

    if job_info.state not in [JobState.RUNNING, JobState.PENDING]:
        raise RuntimeError(
            "Can only attach watchers to running or pending jobs. "
            f"Job {job_id} is in state: {job_info.state}"
        )

    watcher_defs = build_watcher_definitions(watchers=watchers, job_id=job_id)
    engine = get_watcher_engine()
    watcher_ids = await engine.start_watchers_for_job(job_id, host, watcher_defs)
    logger.info(f"Attached {len(watcher_ids)} watchers to job {job_id} on {host}")

    return {
        "message": f"Successfully attached {len(watcher_ids)} watchers to job {job_id}",
        "watcher_ids": watcher_ids,
        "job_id": job_id,
        "hostname": host,
    }


def update_watcher(*, cache, watcher_id: int, watcher_update: Dict[str, Any]):
    with cache._get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
        ).fetchone()
        if not row:
            raise ValueError("Watcher not found")

        previous_row = dict(row)
        update_fields, update_values = build_watcher_update_fields(watcher_update)

        if update_fields:
            update_values.append(watcher_id)
            conn.execute(
                f"UPDATE job_watchers SET {', '.join(update_fields)} WHERE id = ?",
                update_values,
            )
            conn.commit()

        updated_row = dict(
            conn.execute(
                "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
            ).fetchone()
        )

    if previous_row["state"] != updated_row["state"]:
        if updated_row["state"] == "active" and previous_row["state"] == "paused":
            start_watcher_task(
                watcher_id,
                updated_row["job_id"],
                updated_row["hostname"],
            )
        elif updated_row["state"] == "paused" and previous_row["state"] == "active":
            cancel_watcher_task(watcher_id)

    return format_watcher_row(updated_row)


def delete_watcher(*, cache, watcher_id: int) -> Dict[str, Any]:
    with cache._get_connection() as conn:
        row = conn.execute(
            "SELECT state FROM job_watchers WHERE id = ?", (watcher_id,)
        ).fetchone()
        if not row:
            raise ValueError("Watcher not found")
        if row["state"] == "active":
            cancel_watcher_task(watcher_id)

        conn.execute("DELETE FROM watcher_events WHERE watcher_id = ?", (watcher_id,))
        conn.execute("DELETE FROM job_watchers WHERE id = ?", (watcher_id,))
        conn.commit()

    return {"message": f"Watcher {watcher_id} deleted successfully"}
