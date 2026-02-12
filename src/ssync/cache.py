"""
Simple but powerful caching mechanism for Slurm job data.

This module provides persistent caching for job information, scripts, and outputs
to preserve data even when jobs are no longer queryable from Slurm.
"""

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models.job import JobInfo
from .utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class CachedJobData:
    """Represents cached job information with metadata."""

    job_id: str
    hostname: str
    job_info: JobInfo
    script_content: Optional[str] = None
    # Compressed output storage
    stdout_compressed: Optional[bytes] = None
    stdout_size: int = 0
    stdout_compression: str = "none"  # 'gzip' or 'none'
    stderr_compressed: Optional[bytes] = None
    stderr_size: int = 0
    stderr_compression: str = "none"
    cached_at: datetime = None
    last_updated: datetime = None
    is_active: bool = True  # Whether job is still running/pending
    local_source_dir: Optional[str] = None  # The local directory that was synced

    def __post_init__(self):
        if self.cached_at is None:
            self.cached_at = datetime.now()
        if self.last_updated is None:
            self.last_updated = datetime.now()


@dataclass
class NotificationDevice:
    api_key_hash: str
    device_token: str
    platform: str
    bundle_id: Optional[str] = None
    environment: Optional[str] = None
    device_id: Optional[str] = None
    enabled: bool = True
    created_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_seen is None:
            self.last_seen = datetime.now()


class JobDataCache:
    """
    Simple but powerful job data cache with SQLite persistence.

    Features:
    - Automatic caching of job data, scripts, and outputs
    - Persistent storage with SQLite
    - Thread-safe operations
    - Configurable TTL and cleanup
    - Smart cache validation based on job state
    """

    def __init__(self, cache_dir: Optional[Path] = None, max_age_days: int = 365):
        """
        Initialize the job data cache.

        Args:
            cache_dir: Directory to store cache files. Defaults to ~/.cache/ssync
            max_age_days: Maximum age of cached data in days before cleanup (0 = never expire)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "ssync"

        from .utils.config import config as app_config

        self.cache_settings = app_config.cache_settings
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.cache_dir / "jobs.db"
        self.max_age_days = max_age_days
        self._lock = threading.RLock()
        self._init_database()

        logger.info(f"Initialized job cache at {self.cache_dir}")

    def _prepare_dict_for_json(self, data: Dict) -> Dict:
        """Recursively prepare dictionary for JSON serialization by converting enums."""
        result = {}
        for key, value in data.items():
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, dict):
                result[key] = self._prepare_dict_for_json(value)
            elif isinstance(value, list):
                result[key] = [
                    self._prepare_dict_for_json(item)
                    if isinstance(item, dict)
                    else (item.value if isinstance(item, Enum) else item)
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _init_database(self):
        """Initialize SQLite database with required tables."""
        with self._get_connection() as conn:
            # Enable WAL mode for better concurrency (allows multiple readers + 1 writer)
            conn.execute("PRAGMA journal_mode=WAL")
            # Set busy timeout to 10 seconds
            conn.execute("PRAGMA busy_timeout=10000")
            # Enable synchronous=NORMAL for better performance (still safe with WAL)
            conn.execute("PRAGMA synchronous=NORMAL")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cached_jobs (
                    job_id TEXT,
                    hostname TEXT,
                    job_info_json TEXT NOT NULL,
                    script_content TEXT,
                    -- Compressed output storage
                    stdout_compressed BLOB,
                    stdout_size INTEGER DEFAULT 0,
                    stdout_compression TEXT DEFAULT 'none',
                    stderr_compressed BLOB,
                    stderr_size INTEGER DEFAULT 0,
                    stderr_compression TEXT DEFAULT 'none',
                    cached_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    stdout_fetched_after_completion BOOLEAN DEFAULT 0,
                    stderr_fetched_after_completion BOOLEAN DEFAULT 0,
                    PRIMARY KEY (job_id, hostname)
                )
            """)

            # Add columns if they don't exist (for migration)
            try:
                conn.execute(
                    "ALTER TABLE cached_jobs ADD COLUMN stdout_fetched_after_completion BOOLEAN DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute(
                    "ALTER TABLE cached_jobs ADD COLUMN stderr_fetched_after_completion BOOLEAN DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE cached_jobs ADD COLUMN local_source_dir TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cached_job_ranges (
                    cache_key TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    filters_json TEXT NOT NULL,
                    job_ids_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS host_fetch_state (
                    hostname TEXT PRIMARY KEY,
                    last_fetch_time TEXT NOT NULL,
                    last_fetch_time_utc TEXT NOT NULL,
                    cluster_timezone TEXT,
                    fetch_count INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hostname ON cached_jobs(hostname)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cached_at ON cached_jobs(cached_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_is_active ON cached_jobs(is_active)"
            )
            # Add composite index for faster completed job lookups
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_completed_jobs ON cached_jobs(hostname, is_active)"
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_range_hostname ON cached_job_ranges(hostname)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_range_expires ON cached_job_ranges(expires_at)"
            )

            # Watcher tables for job monitoring
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_watchers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    name TEXT,
                    pattern TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL DEFAULT 60,
                    captures_json TEXT,
                    condition TEXT,
                    actions_json TEXT NOT NULL,
                    last_check TEXT,
                    last_position INTEGER DEFAULT 0,
                    trigger_count INTEGER DEFAULT 0,
                    state TEXT DEFAULT 'active',
                    timer_mode_enabled INTEGER DEFAULT 0,
                    timer_interval_seconds INTEGER DEFAULT 30,
                    timer_mode_active INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id, hostname) REFERENCES cached_jobs(job_id, hostname)
                )
            """)

            # Add timer mode columns if they don't exist (for migration)
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN timer_mode_enabled INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN timer_interval_seconds INTEGER DEFAULT 30"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN timer_mode_active INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Add array template columns if they don't exist (for migration)
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN is_array_template INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE job_watchers ADD COLUMN array_spec TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN parent_watcher_id INTEGER"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN discovered_task_count INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute(
                    "ALTER TABLE job_watchers ADD COLUMN expected_task_count INTEGER"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

            conn.execute("""
                CREATE TABLE IF NOT EXISTS watcher_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    watcher_id INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    matched_text TEXT,
                    captured_vars_json TEXT,
                    action_type TEXT NOT NULL,
                    action_result TEXT,
                    success BOOLEAN NOT NULL,
                    FOREIGN KEY (watcher_id) REFERENCES job_watchers(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS watcher_variables (
                    watcher_id INTEGER NOT NULL,
                    variable_name TEXT NOT NULL,
                    variable_value TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (watcher_id, variable_name),
                    FOREIGN KEY (watcher_id) REFERENCES job_watchers(id)
                )
            """)

            # Create indices for watchers
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watchers_job ON job_watchers(job_id, hostname)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watchers_state ON job_watchers(state)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_watcher ON watcher_events(watcher_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON watcher_events(timestamp)"
            )

            # Notification device registrations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key_hash TEXT NOT NULL,
                    device_token TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    bundle_id TEXT,
                    environment TEXT,
                    device_id TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    UNIQUE(api_key_hash, device_token)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notification_devices_key ON notification_devices(api_key_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notification_devices_platform ON notification_devices(platform)"
            )

            # Notification preferences (per API key)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    api_key_hash TEXT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    allowed_states_json TEXT,
                    muted_job_ids_json TEXT,
                    muted_hosts_json TEXT,
                    muted_job_name_patterns_json TEXT,
                    allowed_users_json TEXT,
                    updated_at TEXT NOT NULL
                )
            """)

            # Web Push subscriptions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS webpush_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key_hash TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    user_agent TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    UNIQUE(api_key_hash, endpoint)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_webpush_subscriptions_key ON webpush_subscriptions(api_key_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_webpush_subscriptions_enabled ON webpush_subscriptions(enabled)"
            )

            # Array job metadata tables for efficient grouping and querying
            conn.execute("""
                CREATE TABLE IF NOT EXISTS array_jobs (
                    array_job_id TEXT,
                    hostname TEXT,
                    job_name TEXT,
                    user TEXT,
                    script_content TEXT,
                    total_tasks INTEGER DEFAULT 0,
                    submit_time TEXT,
                    partition TEXT,
                    account TEXT,
                    work_dir TEXT,
                    created_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY (array_job_id, hostname)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS array_task_stats (
                    array_job_id TEXT,
                    hostname TEXT,
                    state TEXT,
                    count INTEGER DEFAULT 0,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY (array_job_id, hostname, state),
                    FOREIGN KEY (array_job_id, hostname)
                        REFERENCES array_jobs(array_job_id, hostname)
                )
            """)

            # Indices for array job queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_array_jobs_hostname ON array_jobs(hostname)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_array_jobs_user ON array_jobs(hostname, user)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_array_task_stats_array ON array_task_stats(array_job_id, hostname)"
            )

            # Add array_job_id column to cached_jobs for easier filtering (migration safe)
            try:
                conn.execute("ALTER TABLE cached_jobs ADD COLUMN array_job_id TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Add index on array_job_id for fast task lookups
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cached_jobs_array_id ON cached_jobs(array_job_id, hostname)"
            )

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get thread-safe database connection."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            # Set WAL mode for this connection (idempotent, safe to call multiple times)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            try:
                yield conn
            finally:
                conn.close()

    def _merge_job_info(self, new_job: JobInfo, existing_job: JobInfo) -> JobInfo:
        """
        Intelligently merge job info, preserving non-None values from existing job.

        Priority order:
        1. New non-None/non-empty values (updates)
        2. Existing non-None/non-empty values (preservation)
        3. New None/empty values (fallback)
        """
        from dataclasses import fields

        merged_data = {}
        for field in fields(JobInfo):
            new_val = getattr(new_job, field.name)
            existing_val = getattr(existing_job, field.name)

            critical_fields = [
                "stdout_file",
                "stderr_file",
                "work_dir",
                "submit_line",
                "req_tres",
                "alloc_tres",
                "node_list",
            ]

            if field.name in critical_fields:
                if existing_val and not new_val:
                    merged_data[field.name] = existing_val
                    logger.debug(
                        f"Preserving critical field {field.name} for job {new_job.job_id}"
                    )
                else:
                    merged_data[field.name] = new_val if new_val else existing_val
            else:
                merged_data[field.name] = (
                    new_val if new_val is not None else existing_val
                )

        return JobInfo(**merged_data)

    def cache_job(
        self,
        job_info: JobInfo,
        script_content: Optional[str] = None,
        local_source_dir: Optional[str] = None,
    ):
        """
        Cache job information and associated data.

        IMPORTANT: This method preserves existing script content if not provided.
        This ensures scripts cached at job launch time are not lost when job status is updated.

        Args:
            job_info: JobInfo object to cache
            script_content: Optional script content (if None, preserves existing)
            local_source_dir: Optional local source directory that was synced
        """
        now = datetime.now()
        # Check if job is in active state (Pending or Running)
        from .models.job import JobState as JS

        is_active = job_info.state in [JS.PENDING, JS.RUNNING]

        existing_cached = self.get_cached_job(job_info.job_id, job_info.hostname)

        if existing_cached:
            if script_content is None and existing_cached.script_content:
                script_content = existing_cached.script_content
                logger.debug(
                    f"Preserving existing script content for job {job_info.job_id}"
                )
            if local_source_dir is None and existing_cached.local_source_dir:
                local_source_dir = existing_cached.local_source_dir
                logger.debug(
                    f"Preserving existing local source dir for job {job_info.job_id}"
                )
            # Output preservation is now handled via update_job_outputs_compressed

            if existing_cached.job_info:
                job_info = self._merge_job_info(job_info, existing_cached.job_info)

            cached_at = existing_cached.cached_at
        else:
            cached_at = now

        # Preserve existing compressed outputs if available
        stdout_compressed = (
            existing_cached.stdout_compressed if existing_cached else None
        )
        stdout_size = existing_cached.stdout_size if existing_cached else 0
        stdout_compression = (
            existing_cached.stdout_compression if existing_cached else "none"
        )
        stderr_compressed = (
            existing_cached.stderr_compressed if existing_cached else None
        )
        stderr_size = existing_cached.stderr_size if existing_cached else 0
        stderr_compression = (
            existing_cached.stderr_compression if existing_cached else "none"
        )

        cached_data = CachedJobData(
            job_id=job_info.job_id,
            hostname=job_info.hostname,
            job_info=job_info,
            script_content=script_content,
            local_source_dir=local_source_dir,
            # Preserve existing outputs or initialize empty
            stdout_compressed=stdout_compressed,
            stdout_size=stdout_size,
            stdout_compression=stdout_compression,
            stderr_compressed=stderr_compressed,
            stderr_size=stderr_size,
            stderr_compression=stderr_compression,
            cached_at=cached_at,
            last_updated=now,
            is_active=is_active,
        )

        self._store_cached_data(cached_data)

    def _store_cached_data(self, cached_data: CachedJobData):
        """Store cached data in database and maintain array metadata."""
        with self._get_connection() as conn:
            job_info_dict = asdict(cached_data.job_info)

            # Convert enums to strings for JSON serialization
            job_info_dict = self._prepare_dict_for_json(job_info_dict)

            # Extract array_job_id from job_info
            array_job_id = cached_data.job_info.array_job_id

            conn.execute(
                """
                INSERT OR REPLACE INTO cached_jobs
                (job_id, hostname, job_info_json, script_content, local_source_dir,
                 stdout_compressed, stdout_size, stdout_compression,
                 stderr_compressed, stderr_size, stderr_compression,
                 cached_at, last_updated, is_active, array_job_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    cached_data.job_id,
                    cached_data.hostname,
                    json.dumps(job_info_dict),
                    cached_data.script_content,
                    cached_data.local_source_dir,
                    cached_data.stdout_compressed,
                    cached_data.stdout_size,
                    cached_data.stdout_compression,
                    cached_data.stderr_compressed,
                    cached_data.stderr_size,
                    cached_data.stderr_compression,
                    cached_data.cached_at.isoformat(),
                    cached_data.last_updated.isoformat(),
                    cached_data.is_active,
                    array_job_id,
                ),
            )

            # Maintain array metadata if this is an array job
            if array_job_id:
                self._update_array_metadata(
                    conn, cached_data.job_info, cached_data.script_content
                )

            conn.commit()

    def _update_array_metadata(
        self, conn, job_info: JobInfo, script_content: Optional[str] = None
    ):
        """Update array job metadata and task statistics.

        This method maintains the array_jobs and array_task_stats tables.
        Should be called whenever an array job task is cached.
        """
        array_job_id = job_info.array_job_id
        hostname = job_info.hostname
        array_task_id = job_info.array_task_id
        now = datetime.now()

        # Skip parent entries (with brackets) - we only track actual tasks
        if array_task_id and "[" in array_task_id:
            return

        # Ensure array_jobs record exists
        cursor = conn.execute(
            "SELECT 1 FROM array_jobs WHERE array_job_id = ? AND hostname = ?",
            (array_job_id, hostname),
        )
        array_exists = cursor.fetchone() is not None

        if not array_exists:
            # Create new array job record
            conn.execute(
                """
                INSERT INTO array_jobs
                (array_job_id, hostname, job_name, user, script_content,
                 total_tasks, submit_time, partition, account, work_dir,
                 created_at, last_updated)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    array_job_id,
                    hostname,
                    job_info.name,
                    job_info.user,
                    script_content,
                    job_info.submit_time,
                    job_info.partition,
                    job_info.account,
                    job_info.work_dir,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            logger.debug(f"Created array job metadata for {array_job_id} on {hostname}")
        else:
            # Update existing array job record (preserve script if not provided)
            if script_content:
                conn.execute(
                    """
                    UPDATE array_jobs
                    SET job_name = ?, user = ?, script_content = ?,
                        submit_time = ?, partition = ?, account = ?, work_dir = ?,
                        last_updated = ?
                    WHERE array_job_id = ? AND hostname = ?
                    """,
                    (
                        job_info.name,
                        job_info.user,
                        script_content,
                        job_info.submit_time,
                        job_info.partition,
                        job_info.account,
                        job_info.work_dir,
                        now.isoformat(),
                        array_job_id,
                        hostname,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE array_jobs
                    SET job_name = ?, user = ?,
                        submit_time = ?, partition = ?, account = ?, work_dir = ?,
                        last_updated = ?
                    WHERE array_job_id = ? AND hostname = ?
                    """,
                    (
                        job_info.name,
                        job_info.user,
                        job_info.submit_time,
                        job_info.partition,
                        job_info.account,
                        job_info.work_dir,
                        now.isoformat(),
                        array_job_id,
                        hostname,
                    ),
                )

        # Update task count
        cursor = conn.execute(
            """
            SELECT COUNT(*) as task_count FROM cached_jobs
            WHERE array_job_id = ? AND hostname = ?
              AND job_id NOT LIKE '%[%'
            """,
            (array_job_id, hostname),
        )
        task_count = cursor.fetchone()[0]

        conn.execute(
            """
            UPDATE array_jobs
            SET total_tasks = ?, last_updated = ?
            WHERE array_job_id = ? AND hostname = ?
            """,
            (task_count, now.isoformat(), array_job_id, hostname),
        )

        # Recalculate state statistics
        self._recalculate_array_stats(conn, array_job_id, hostname)

        logger.debug(
            f"Updated array metadata for {array_job_id} on {hostname}: {task_count} tasks"
        )

    def _recalculate_array_stats(self, conn, array_job_id: str, hostname: str):
        """Recalculate and update state statistics for an array job."""
        now = datetime.now()

        # Get state counts from actual tasks
        cursor = conn.execute(
            """
            SELECT
                json_extract(job_info_json, '$.state') as state,
                COUNT(*) as count
            FROM cached_jobs
            WHERE array_job_id = ? AND hostname = ?
              AND job_id NOT LIKE '%[%'
            GROUP BY state
            """,
            (array_job_id, hostname),
        )

        state_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Clear existing stats
        conn.execute(
            """
            DELETE FROM array_task_stats
            WHERE array_job_id = ? AND hostname = ?
            """,
            (array_job_id, hostname),
        )

        # Insert updated stats
        for state, count in state_counts.items():
            conn.execute(
                """
                INSERT INTO array_task_stats
                (array_job_id, hostname, state, count, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (array_job_id, hostname, state, count, now.isoformat()),
            )

    def get_array_job_metadata(
        self, array_job_id: str, hostname: str
    ) -> Optional[Dict[str, Any]]:
        """Get metadata for an array job including statistics.

        Returns:
            Dictionary with array job metadata and task statistics, or None if not found
        """
        with self._get_connection() as conn:
            # Get array job metadata
            cursor = conn.execute(
                """
                SELECT * FROM array_jobs
                WHERE array_job_id = ? AND hostname = ?
                """,
                (array_job_id, hostname),
            )
            row = cursor.fetchone()

            if not row:
                return None

            metadata = dict(row)

            # Get task statistics
            cursor = conn.execute(
                """
                SELECT state, count FROM array_task_stats
                WHERE array_job_id = ? AND hostname = ?
                """,
                (array_job_id, hostname),
            )

            stats = {row["state"]: row["count"] for row in cursor.fetchall()}
            metadata["state_counts"] = stats

            return metadata

    def get_array_tasks(
        self, array_job_id: str, hostname: str, limit: Optional[int] = None
    ) -> List[JobInfo]:
        """Get all tasks for an array job efficiently.

        Args:
            array_job_id: The array job ID
            hostname: Hostname
            limit: Optional limit on number of tasks to return

        Returns:
            List of JobInfo objects for array tasks
        """
        with self._get_connection() as conn:
            query = """
                SELECT job_info_json FROM cached_jobs
                WHERE array_job_id = ? AND hostname = ?
                  AND job_id NOT LIKE '%[%'
                ORDER BY job_id
            """
            params = [array_job_id, hostname]

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor = conn.execute(query, params)

            jobs = []
            for row in cursor.fetchall():
                try:
                    job_dict = json.loads(row["job_info_json"])
                    # Convert state string back to JobState enum
                    if "state" in job_dict and isinstance(job_dict["state"], str):
                        from .models.job import JobState

                        try:
                            job_dict["state"] = JobState(job_dict["state"])
                        except ValueError:
                            job_dict["state"] = JobState.UNKNOWN
                    jobs.append(JobInfo(**job_dict))
                except Exception as e:
                    logger.warning(f"Failed to parse array task: {e}")

            return jobs

    def get_cached_job(
        self,
        job_id: str,
        hostname: Optional[str] = None,
        max_age_days: Optional[int] = None,
    ) -> Optional[CachedJobData]:
        """
        Retrieve cached job data.

        Args:
            job_id: Job ID to look up
            hostname: Optional hostname filter
            max_age_days: Maximum age in days for cached job to be considered valid.
                         Jobs older than this are likely recycled IDs. Default 30 days.

        Returns:
            CachedJobData if found and not too old, None otherwise
        """
        if max_age_days is None:
            max_age_days = self.cache_settings.recycled_id_max_age_days

        cache_cutoff = self._get_cache_cutoff_iso(max_age_days)
        submit_time_cutoff = self._get_submit_time_cutoff(max_age_days)

        with self._get_connection() as conn:
            query = "SELECT * FROM cached_jobs WHERE job_id = ?"
            params: List[Any] = [job_id]
            if hostname:
                query += " AND hostname = ?"
                params.append(hostname)
            if cache_cutoff:
                query += " AND cached_at >= ?"
                params.append(cache_cutoff)
            cursor = conn.execute(query, params)

            row = cursor.fetchone()
            if row:
                cached_data = self._row_to_cached_data(row)

                # Validate that the cached job isn't too old (likely a recycled ID)
                if cached_data.job_info and cached_data.job_info.submit_time:
                    if self._is_submit_time_older_than_cutoff(
                        cached_data.job_info.submit_time, submit_time_cutoff
                    ):
                        logger.debug(
                            f"Ignoring stale cached job {job_id} on {hostname} "
                            f"(>{max_age_days} days old)"
                        )
                        return None

                return cached_data

            return None

    def get_cached_jobs_by_ids(
        self,
        job_ids: List[str],
        hostname: Optional[str] = None,
        max_age_days: Optional[int] = None,
    ) -> Dict[str, CachedJobData]:
        """Batch lookup cached jobs by ID.

        Returns a dict of job_id -> CachedJobData for jobs that exist and pass age checks.
        """
        if not job_ids:
            return {}

        results: Dict[str, CachedJobData] = {}
        if max_age_days is None:
            max_age_days = self.cache_settings.recycled_id_max_age_days
        cache_cutoff = self._get_cache_cutoff_iso(max_age_days)
        submit_time_cutoff = self._get_submit_time_cutoff(max_age_days)

        # SQLite has a limit on variables; chunk to stay under it.
        chunk_size = 500
        skipped_stale: List[str] = []
        with self._get_connection() as conn:
            for i in range(0, len(job_ids), chunk_size):
                chunk = job_ids[i : i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                if hostname:
                    query = (
                        f"SELECT * FROM cached_jobs WHERE job_id IN ({placeholders}) "
                        "AND hostname = ?"
                    )
                    params = [*chunk, hostname]
                else:
                    query = (
                        f"SELECT * FROM cached_jobs WHERE job_id IN ({placeholders})"
                    )
                    params = [*chunk]
                if cache_cutoff:
                    query += " AND cached_at >= ?"
                    params.append(cache_cutoff)

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                for row in rows:
                    cached_data = self._row_to_cached_data(row)
                    job_id = cached_data.job_id

                    # Validate age to avoid recycled IDs
                    if cached_data.job_info and cached_data.job_info.submit_time:
                        if self._is_submit_time_older_than_cutoff(
                            cached_data.job_info.submit_time, submit_time_cutoff
                        ):
                            skipped_stale.append(job_id)
                            continue

                    results[job_id] = cached_data

        if skipped_stale:
            logger.debug(
                f"Skipped {len(skipped_stale)} stale cached jobs (>{max_age_days} days old)"
            )

        return results

    def _get_cache_cutoff_iso(self, max_age_days: Optional[int]) -> Optional[str]:
        """Return cached_at cutoff (local time) for quick stale row filtering."""
        if max_age_days is None or max_age_days <= 0:
            return None
        return (datetime.now() - timedelta(days=max_age_days)).isoformat()

    def _get_submit_time_cutoff(self, max_age_days: Optional[int]) -> Optional[datetime]:
        """Return submit_time cutoff (UTC) for recycled-ID validation."""
        if max_age_days is None or max_age_days <= 0:
            return None
        from datetime import timezone

        return datetime.now(timezone.utc) - timedelta(days=max_age_days)

    def _is_submit_time_older_than_cutoff(
        self, submit_time: Any, cutoff: Optional[datetime]
    ) -> bool:
        """Check whether submit_time is older than the provided UTC cutoff."""
        if not submit_time or cutoff is None:
            return False

        from datetime import timezone

        parsed_submit_time: Optional[datetime]
        if isinstance(submit_time, str):
            try:
                parsed_submit_time = datetime.fromisoformat(
                    submit_time.replace("Z", "+00:00")
                )
            except ValueError:
                logger.debug(f"Failed to parse cached submit_time: {submit_time}")
                return False
        elif isinstance(submit_time, datetime):
            parsed_submit_time = submit_time
        else:
            return False

        if parsed_submit_time.tzinfo is None:
            parsed_submit_time = parsed_submit_time.replace(tzinfo=timezone.utc)
        else:
            parsed_submit_time = parsed_submit_time.astimezone(timezone.utc)

        return parsed_submit_time < cutoff

    def get_cached_jobs(
        self,
        hostname: Optional[str] = None,
        active_only: bool = False,
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> List[CachedJobData]:
        """
        Get list of cached jobs with optional filtering.

        Args:
            hostname: Optional hostname filter
            active_only: If True, only return active jobs
            limit: Optional limit on number of results
            since: Optional datetime to filter jobs submitted after this time (assumed UTC)

        Returns:
            List of CachedJobData objects
        """
        with self._get_connection() as conn:
            query = "SELECT * FROM cached_jobs WHERE 1=1"
            params = []

            if hostname:
                query += " AND hostname = ?"
                params.append(hostname)

            if active_only:
                query += " AND is_active = 1"

            if since:
                # Filter by submit time if available in the JSON
                # Strip timezone for comparison with stored times (which have no timezone)
                since_for_comparison = (
                    since.replace(tzinfo=None) if since.tzinfo else since
                )
                query += " AND datetime(json_extract(job_info_json, '$.submit_time')) > datetime(?)"
                params.append(since_for_comparison.isoformat())

            query += " ORDER BY last_updated DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor = conn.execute(query, params)
            return [self._row_to_cached_data(row) for row in cursor.fetchall()]

    def _row_to_cached_data(self, row: sqlite3.Row) -> CachedJobData:
        """Convert database row to CachedJobData."""
        from .models.job import JobState

        job_info_dict = json.loads(row["job_info_json"])

        # Convert string back to enum for JobState
        if "state" in job_info_dict and isinstance(job_info_dict["state"], str):
            try:
                job_info_dict["state"] = JobState(job_info_dict["state"])
            except ValueError:
                # Fallback for unknown states
                job_info_dict["state"] = JobState.UNKNOWN

        job_info = JobInfo(**job_info_dict)

        # Handle optional local_source_dir column for existing DBs
        local_source_dir = None
        try:
            local_source_dir = row["local_source_dir"]
        except (KeyError, IndexError):
            # Column doesn't exist in older databases
            pass

        return CachedJobData(
            job_id=row["job_id"],
            hostname=row["hostname"],
            job_info=job_info,
            script_content=row["script_content"],
            local_source_dir=local_source_dir,
            stdout_compressed=row["stdout_compressed"],
            stdout_size=row["stdout_size"],
            stdout_compression=row["stdout_compression"],
            stderr_compressed=row["stderr_compressed"],
            stderr_size=row["stderr_size"],
            stderr_compression=row["stderr_compression"],
            cached_at=datetime.fromisoformat(row["cached_at"]),
            last_updated=datetime.fromisoformat(row["last_updated"]),
            is_active=bool(row["is_active"]),
        )

    def update_job_outputs_compressed(
        self,
        job_id: str,
        hostname: str,
        stdout_data: Optional[dict] = None,
        stderr_data: Optional[dict] = None,
        mark_fetched_after_completion: bool = False,
    ):
        """
        Update cached job outputs with compressed data.

        Args:
            job_id: Job ID
            hostname: Hostname
            stdout_data: Dict with compressed stdout data and metadata
            stderr_data: Dict with compressed stderr data and metadata
            mark_fetched_after_completion: If True, mark outputs as fetched after job completion
        """
        import base64
        import gzip

        with self._get_connection() as conn:
            updates = []
            params = []

            if stdout_data is not None:
                # Decode base64 and store as BLOB
                compressed_data = base64.b64decode(stdout_data["data"])

                # Further compress if not already compressed and large enough
                if not stdout_data.get("compressed") and len(compressed_data) > 1024:
                    compressed_data = gzip.compress(compressed_data)
                    compression = "gzip"
                else:
                    compression = stdout_data.get("compression", "none")

                updates.extend(
                    [
                        "stdout_compressed = ?",
                        "stdout_size = ?",
                        "stdout_compression = ?",
                    ]
                )
                params.extend(
                    [compressed_data, stdout_data.get("original_size", 0), compression]
                )

                if mark_fetched_after_completion:
                    updates.append("stdout_fetched_after_completion = 1")

            if stderr_data is not None:
                # Decode base64 and store as BLOB
                compressed_data = base64.b64decode(stderr_data["data"])

                # Further compress if not already compressed and large enough
                if not stderr_data.get("compressed") and len(compressed_data) > 1024:
                    compressed_data = gzip.compress(compressed_data)
                    compression = "gzip"
                else:
                    compression = stderr_data.get("compression", "none")

                updates.extend(
                    [
                        "stderr_compressed = ?",
                        "stderr_size = ?",
                        "stderr_compression = ?",
                    ]
                )
                params.extend(
                    [compressed_data, stderr_data.get("original_size", 0), compression]
                )

                if mark_fetched_after_completion:
                    updates.append("stderr_fetched_after_completion = 1")

            if updates:
                updates.append("last_updated = ?")
                params.append(datetime.now().isoformat())
                params.extend([job_id, hostname])

                query = f"""
                    UPDATE cached_jobs 
                    SET {", ".join(updates)}
                    WHERE job_id = ? AND hostname = ?
                """
                conn.execute(query, params)
                conn.commit()

                logger.debug(
                    f"Updated compressed outputs for job {job_id} on {hostname}"
                )

    def update_job_outputs(
        self,
        job_id: str,
        hostname: str,
        stdout_content: Optional[str] = None,
        stderr_content: Optional[str] = None,
        mark_fetched_after_completion: bool = False,
    ):
        """
        Update cached job outputs without replacing the entire entry.
        This is a compatibility wrapper that converts text content to compressed format.

        Args:
            job_id: Job ID
            hostname: Hostname
            stdout_content: Updated stdout content (plain text)
            stderr_content: Updated stderr content (plain text)
            mark_fetched_after_completion: If True, mark outputs as fetched after job completion
        """
        import base64
        import gzip

        # Convert text content to compressed format
        stdout_data = None
        stderr_data = None

        if stdout_content is not None:
            # Compress if large enough
            if len(stdout_content) > 1024:
                compressed = gzip.compress(stdout_content.encode("utf-8"))
                stdout_data = {
                    "compressed": True,
                    "data": base64.b64encode(compressed).decode("ascii"),
                    "original_size": len(stdout_content),
                    "compression": "gzip",
                }
            else:
                # Store uncompressed for small content
                stdout_data = {
                    "compressed": False,
                    "data": base64.b64encode(stdout_content.encode("utf-8")).decode(
                        "ascii"
                    ),
                    "original_size": len(stdout_content),
                    "compression": "none",
                }

        if stderr_content is not None:
            # Compress if large enough
            if len(stderr_content) > 1024:
                compressed = gzip.compress(stderr_content.encode("utf-8"))
                stderr_data = {
                    "compressed": True,
                    "data": base64.b64encode(compressed).decode("ascii"),
                    "original_size": len(stderr_content),
                    "compression": "gzip",
                }
            else:
                # Store uncompressed for small content
                stderr_data = {
                    "compressed": False,
                    "data": base64.b64encode(stderr_content.encode("utf-8")).decode(
                        "ascii"
                    ),
                    "original_size": len(stderr_content),
                    "compression": "none",
                }

        # Call the compressed version
        self.update_job_outputs_compressed(
            job_id=job_id,
            hostname=hostname,
            stdout_data=stdout_data,
            stderr_data=stderr_data,
            mark_fetched_after_completion=mark_fetched_after_completion,
        )

    def update_job_script(
        self,
        job_id: str,
        hostname: str,
        script_content: str,
    ):
        """
        Update or set cached job script without replacing the entire entry.
        Creates a minimal entry if the job doesn't exist in cache yet.

        Args:
            job_id: Job ID
            hostname: Hostname
            script_content: Script content to cache
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM cached_jobs WHERE job_id = ? AND hostname = ?",
                (job_id, hostname),
            )
            exists = cursor.fetchone()["count"] > 0

            if exists:
                conn.execute(
                    """
                    UPDATE cached_jobs 
                    SET script_content = ?, last_updated = ?
                    WHERE job_id = ? AND hostname = ?
                    """,
                    (script_content, datetime.now().isoformat(), job_id, hostname),
                )
            else:
                from .models.job import JobInfo, JobState

                minimal_job_info = JobInfo(
                    job_id=job_id,
                    name=f"job_{job_id}",
                    state=JobState.PENDING,
                    hostname=hostname,
                )

                cached_data = CachedJobData(
                    job_id=job_id,
                    hostname=hostname,
                    job_info=minimal_job_info,
                    script_content=script_content,
                    is_active=True,
                )

                self._store_cached_data(cached_data)

            conn.commit()

    def mark_job_completed(self, job_id: str, hostname: str):
        """Mark a job as no longer active (completed/failed/cancelled)."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE cached_jobs 
                SET is_active = 0, last_updated = ?
                WHERE job_id = ? AND hostname = ?
            """,
                (datetime.now().isoformat(), job_id, hostname),
            )
            conn.commit()

    def check_outputs_fetched_after_completion(
        self, job_id: str, hostname: str
    ) -> tuple[bool, bool]:
        """
        Check if outputs were already fetched after job completion.

        Returns:
            Tuple of (stdout_fetched_after_completion, stderr_fetched_after_completion)
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT stdout_fetched_after_completion, stderr_fetched_after_completion
                FROM cached_jobs
                WHERE job_id = ? AND hostname = ?
            """,
                (job_id, hostname),
            )
            row = cursor.fetchone()
            if row:
                try:
                    stdout_fetched = bool(row["stdout_fetched_after_completion"])
                except (KeyError, TypeError):
                    stdout_fetched = False
                try:
                    stderr_fetched = bool(row["stderr_fetched_after_completion"])
                except (KeyError, TypeError):
                    stderr_fetched = False
                return stdout_fetched, stderr_fetched
            return False, False

    def mark_outputs_fetched_after_completion(
        self, job_id: str, hostname: str, stdout: bool = True, stderr: bool = True
    ):
        """Mark that outputs were fetched after job completion.

        This prevents re-fetching outputs for completed jobs since they won't change.

        Args:
            job_id: Job ID
            hostname: Hostname where the job ran
            stdout: Mark stdout as fetched
            stderr: Mark stderr as fetched
        """
        with self._get_connection() as conn:
            updates = []
            if stdout:
                updates.append("stdout_fetched_after_completion = 1")
            if stderr:
                updates.append("stderr_fetched_after_completion = 1")

            if updates:
                query = f"""
                    UPDATE cached_jobs 
                    SET {", ".join(updates)}, last_updated = ?
                    WHERE job_id = ? AND hostname = ? AND is_active = 0
                """
                conn.execute(query, (datetime.now().isoformat(), job_id, hostname))
                conn.commit()
                logger.debug(
                    f"Marked outputs as fetched after completion for job {job_id} on {hostname}"
                )

    def cleanup_old_entries(
        self,
        max_age_days: Optional[int] = None,
        preserve_scripts: bool = True,
        force_cleanup: bool = False,
    ) -> int:
        """
        Clean up old cache entries. By default, preserves scripts permanently.

        Args:
            max_age_days: Override default max age (0 = never expire)
            preserve_scripts: If True, never delete entries with scripts
            force_cleanup: If True, ignore preservation settings

        Returns:
            Number of entries cleaned up
        """
        from .utils.config import config as app_config

        cache_settings = app_config.cache_settings

        if max_age_days is None:
            max_age_days = self.max_age_days

        if max_age_days == 0 and not force_cleanup:
            logger.info("Cache cleanup skipped (max_age_days=0, preservation mode)")
            return 0

        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        with self._get_connection() as conn:
            query = "DELETE FROM cached_jobs WHERE cached_at < ?"
            params = [cutoff_date.isoformat()]

            script_preservation = (
                cache_settings.script_max_age_days == 0 or preserve_scripts
            ) and not force_cleanup

            if script_preservation:
                query += ' AND (script_content IS NULL OR script_content = "")'
                logger.info(
                    "Cleaning up old cache entries (preserving all scripts indefinitely)"
                )
            else:
                logger.warning("Cleaning up old cache entries (including scripts!)")

            cursor = conn.execute(query, params)
            deleted_count = cursor.rowcount
            conn.commit()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old cache entries")

            return deleted_count

    def _generate_cache_key(self, hostname: str, filters: Dict[str, Any]) -> str:
        """Generate a unique cache key for a query."""
        filter_str = json.dumps(filters, sort_keys=True)
        key_source = f"{hostname}:{filter_str}"
        return hashlib.sha256(key_source.encode()).hexdigest()[:16]

    def _parse_since_to_dates(self, since: str) -> Tuple[datetime, datetime]:
        """Parse 'since' parameter to date range."""
        end_date = datetime.now()
        import re

        match = re.match(r"^(\d+)([hdwm])$", since)
        if not match:
            start_date = end_date - timedelta(days=1)
        else:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == "h":
                start_date = end_date - timedelta(hours=value)
            elif unit == "d":
                start_date = end_date - timedelta(days=value)
            elif unit == "w":
                start_date = end_date - timedelta(weeks=value)
            elif unit == "m":
                start_date = end_date - timedelta(days=value * 30)
            else:
                start_date = end_date - timedelta(days=1)

        return start_date, end_date

    def check_date_range_cache(
        self, hostname: str, filters: Dict[str, Any], since: Optional[str] = None
    ) -> Optional[List[str]]:
        """Check if we have cached job IDs for this date range query.

        Returns:
            List of job IDs if cache hit, None if cache miss
        """
        if not since:
            return None

        cache_key = self._generate_cache_key(hostname, filters)
        requested_start, requested_end = self._parse_since_to_dates(since)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT job_ids_json, cached_at, hit_count
                FROM cached_job_ranges
                WHERE hostname = ?
                  AND cache_key = ?
                  AND start_date <= ?
                  AND end_date >= ?
                  AND expires_at > ?
                ORDER BY cached_at DESC
                LIMIT 1
            """,
                (
                    hostname,
                    cache_key,
                    requested_start.isoformat(),
                    requested_end.isoformat(),
                    datetime.now().isoformat(),
                ),
            )

            row = cursor.fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE cached_job_ranges
                    SET hit_count = hit_count + 1
                    WHERE cache_key = ?
                """,
                    (cache_key,),
                )
                conn.commit()

                job_ids = json.loads(row["job_ids_json"])
                logger.debug(
                    f"Date range cache HIT for {hostname}: {len(job_ids)} jobs "
                    f"(hit #{row['hit_count'] + 1})"
                )
                return job_ids

        return None

    def cache_date_range_query(
        self,
        hostname: str,
        filters: Dict[str, Any],
        since: str,
        job_ids: List[str],
        ttl_seconds: int = 60,
    ):
        """Cache the job IDs from a date range query."""
        cache_key = self._generate_cache_key(hostname, filters)
        start_date, end_date = self._parse_since_to_dates(since)

        with self._get_connection() as conn:
            now = datetime.now()
            expires_at = now + timedelta(seconds=ttl_seconds)

            conn.execute(
                """
                INSERT OR REPLACE INTO cached_job_ranges
                (cache_key, hostname, start_date, end_date, filters_json,
                 job_ids_json, cached_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
                (
                    cache_key,
                    hostname,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    json.dumps(filters),
                    json.dumps(job_ids),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()

            logger.info(
                f"Cached date range query for {hostname}: {len(job_ids)} jobs, "
                f"TTL={ttl_seconds}s"
            )

    def cleanup_expired_ranges(self) -> int:
        """Clean up expired date range cache entries.

        Returns:
            Number of entries cleaned up
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM cached_job_ranges
                WHERE expires_at < ?
            """,
                (datetime.now().isoformat(),),
            )

            deleted = cursor.rowcount
            if deleted > 0:
                conn.commit()
                logger.info(f"Cleaned up {deleted} expired date range cache entries")

            return deleted

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as total FROM cached_jobs")
            total = cursor.fetchone()["total"]
            cursor = conn.execute(
                "SELECT COUNT(*) as active FROM cached_jobs WHERE is_active = 1"
            )
            active = cursor.fetchone()["active"]
            cursor = conn.execute("""
                SELECT hostname, COUNT(*) as count 
                FROM cached_jobs 
                GROUP BY hostname 
                ORDER BY count DESC
            """)
            by_hostname = {row["hostname"]: row["count"] for row in cursor.fetchall()}
            cursor = conn.execute(
                "SELECT COUNT(*) as with_scripts FROM cached_jobs WHERE script_content IS NOT NULL"
            )
            with_scripts = cursor.fetchone()["with_scripts"]

            cursor = conn.execute(
                "SELECT COUNT(*) as with_stdout FROM cached_jobs WHERE stdout_compressed IS NOT NULL"
            )
            with_stdout = cursor.fetchone()["with_stdout"]
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_ranges,
                    SUM(hit_count) as total_hits,
                    AVG(hit_count) as avg_hits_per_range
                FROM cached_job_ranges
                WHERE expires_at > ?
            """,
                (datetime.now().isoformat(),),
            )
            range_stats = cursor.fetchone()
            cursor = conn.execute(
                """
                SELECT hostname, filters_json, hit_count, cached_at
                FROM cached_job_ranges
                WHERE expires_at > ?
                ORDER BY hit_count DESC
                LIMIT 5
            """,
                (datetime.now().isoformat(),),
            )
            top_ranges = [
                {
                    "hostname": row["hostname"],
                    "filters": json.loads(row["filters_json"]),
                    "hits": row["hit_count"],
                    "cached_at": row["cached_at"],
                }
                for row in cursor.fetchall()
            ]

            return {
                "total_jobs": total,
                "active_jobs": active,
                "completed_jobs": total - active,
                "jobs_by_hostname": by_hostname,
                "jobs_with_scripts": with_scripts,
                "jobs_with_stdout": with_stdout,
                "cache_dir": str(self.cache_dir),
                "db_size_mb": self.db_path.stat().st_size / (1024 * 1024)
                if self.db_path.exists()
                else 0,
                "date_range_cache": {
                    "active_ranges": range_stats["total_ranges"] or 0,
                    "total_hits": range_stats["total_hits"] or 0,
                    "avg_hits_per_range": float(range_stats["avg_hits_per_range"] or 0),
                    "top_ranges": top_ranges,
                },
            }

    def upsert_notification_device(
        self,
        *,
        api_key_hash: str,
        device_token: str,
        platform: str,
        bundle_id: Optional[str] = None,
        environment: Optional[str] = None,
        device_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        """Insert or update a notification device registration."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO notification_devices
                (api_key_hash, device_token, platform, bundle_id, environment, device_id,
                 enabled, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(api_key_hash, device_token) DO UPDATE SET
                    platform=excluded.platform,
                    bundle_id=excluded.bundle_id,
                    environment=excluded.environment,
                    device_id=excluded.device_id,
                    enabled=excluded.enabled,
                    last_seen=excluded.last_seen
            """,
                (
                    api_key_hash,
                    device_token,
                    platform,
                    bundle_id,
                    environment,
                    device_id,
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
            conn.commit()

    def remove_notification_device(
        self, *, api_key_hash: str, device_token: str
    ) -> int:
        """Remove a notification device registration."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM notification_devices
                WHERE api_key_hash = ? AND device_token = ?
            """,
                (api_key_hash, device_token),
            )
            deleted = cursor.rowcount
            if deleted:
                conn.commit()
            return deleted

    def list_notification_devices(
        self,
        *,
        platform: Optional[str] = None,
        environment: Optional[str] = None,
        bundle_id: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List notification devices for dispatch."""
        query = "SELECT * FROM notification_devices WHERE 1=1"
        params: List[Any] = []

        if platform:
            query += " AND platform = ?"
            params.append(platform)
        if environment:
            query += " AND (environment = ? OR environment IS NULL)"
            params.append(environment)
        if bundle_id:
            query += " AND (bundle_id = ? OR bundle_id IS NULL)"
            params.append(bundle_id)
        if enabled_only:
            query += " AND enabled = 1"

        devices: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                devices.append(
                    {
                        "api_key_hash": row["api_key_hash"],
                        "device_token": row["device_token"],
                        "platform": row["platform"],
                        "bundle_id": row["bundle_id"],
                        "environment": row["environment"],
                        "device_id": row["device_id"],
                        "enabled": bool(row["enabled"]),
                        "created_at": row["created_at"],
                        "last_seen": row["last_seen"],
                    }
                )

        return devices

    def get_notification_preferences(self, *, api_key_hash: str) -> Dict[str, Any]:
        """Return notification preferences for a user (API key)."""
        defaults = {
            "enabled": True,
            "allowed_states": None,
            "muted_job_ids": [],
            "muted_hosts": [],
            "muted_job_name_patterns": [],
            "allowed_users": [],
        }

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT enabled, allowed_states_json, muted_job_ids_json, muted_hosts_json,
                       muted_job_name_patterns_json, allowed_users_json
                FROM notification_preferences
                WHERE api_key_hash = ?
            """,
                (api_key_hash,),
            )
            row = cursor.fetchone()

        if not row:
            return defaults

        try:
            return {
                "enabled": bool(row["enabled"]),
                "allowed_states": json.loads(row["allowed_states_json"])
                if row["allowed_states_json"]
                else None,
                "muted_job_ids": json.loads(row["muted_job_ids_json"] or "[]"),
                "muted_hosts": json.loads(row["muted_hosts_json"] or "[]"),
                "muted_job_name_patterns": json.loads(
                    row["muted_job_name_patterns_json"] or "[]"
                ),
                "allowed_users": json.loads(row["allowed_users_json"] or "[]"),
            }
        except Exception:
            return defaults

    def upsert_notification_preferences(
        self, *, api_key_hash: str, preferences: Dict[str, Any]
    ) -> None:
        """Insert or update notification preferences for a user."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO notification_preferences
                (api_key_hash, enabled, allowed_states_json, muted_job_ids_json, muted_hosts_json,
                 muted_job_name_patterns_json, allowed_users_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(api_key_hash) DO UPDATE SET
                    enabled=excluded.enabled,
                    allowed_states_json=excluded.allowed_states_json,
                    muted_job_ids_json=excluded.muted_job_ids_json,
                    muted_hosts_json=excluded.muted_hosts_json,
                    muted_job_name_patterns_json=excluded.muted_job_name_patterns_json,
                    allowed_users_json=excluded.allowed_users_json,
                    updated_at=excluded.updated_at
            """,
                (
                    api_key_hash,
                    1 if preferences.get("enabled", True) else 0,
                    json.dumps(preferences.get("allowed_states")),
                    json.dumps(preferences.get("muted_job_ids", [])),
                    json.dumps(preferences.get("muted_hosts", [])),
                    json.dumps(preferences.get("muted_job_name_patterns", [])),
                    json.dumps(preferences.get("allowed_users", [])),
                    now,
                ),
            )
            conn.commit()

    def upsert_webpush_subscription(
        self,
        *,
        api_key_hash: str,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        """Insert or update a Web Push subscription."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO webpush_subscriptions
                (api_key_hash, endpoint, p256dh, auth, user_agent, enabled, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(api_key_hash, endpoint) DO UPDATE SET
                    p256dh=excluded.p256dh,
                    auth=excluded.auth,
                    user_agent=excluded.user_agent,
                    enabled=excluded.enabled,
                    last_seen=excluded.last_seen
            """,
                (
                    api_key_hash,
                    endpoint,
                    p256dh,
                    auth,
                    user_agent,
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
            conn.commit()

    def remove_webpush_subscription(self, *, api_key_hash: str, endpoint: str) -> int:
        """Remove a Web Push subscription."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM webpush_subscriptions
                WHERE api_key_hash = ? AND endpoint = ?
            """,
                (api_key_hash, endpoint),
            )
            deleted = cursor.rowcount
            if deleted:
                conn.commit()
            return deleted

    def list_webpush_subscriptions(
        self,
        *,
        api_key_hash: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List Web Push subscriptions."""
        query = "SELECT * FROM webpush_subscriptions WHERE 1=1"
        params: List[Any] = []

        if api_key_hash:
            query += " AND api_key_hash = ?"
            params.append(api_key_hash)
        if enabled_only:
            query += " AND enabled = 1"

        subscriptions: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                subscriptions.append(
                    {
                        "api_key_hash": row["api_key_hash"],
                        "endpoint": row["endpoint"],
                        "p256dh": row["p256dh"],
                        "auth": row["auth"],
                        "user_agent": row["user_agent"],
                        "enabled": bool(row["enabled"]),
                        "created_at": row["created_at"],
                        "last_seen": row["last_seen"],
                    }
                )

        return subscriptions

    def verify_cached_jobs(
        self, current_job_ids: Dict[str, List[str]]
    ) -> List[Tuple[str, str]]:
        """
        Verify cached jobs against current Slurm state and return jobs to mark as completed.

        Args:
            current_job_ids: Dict mapping hostname to list of current job IDs

        Returns:
            List of (job_id, hostname) tuples for jobs that should be marked completed
        """
        to_mark_completed = []

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT job_id, hostname FROM cached_jobs WHERE is_active = 1"
            )
            active_cached_jobs = [
                (row["job_id"], row["hostname"]) for row in cursor.fetchall()
            ]

        for job_id, hostname in active_cached_jobs:
            current_ids_for_host = current_job_ids.get(hostname, [])
            if job_id not in current_ids_for_host:
                to_mark_completed.append((job_id, hostname))

        return to_mark_completed

    def find_zombie_jobs(self, max_age_days: int = 7) -> list[tuple[str, str, str]]:
        """Find zombie jobs: stale PD/UNKNOWN entries that are likely abandoned.

        Returns list of (job_id, hostname, current_state) tuples.
        """
        from datetime import timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        zombies = []

        with self._get_connection() as conn:
            # Find active jobs that have been stuck in PD/UNKNOWN for too long
            cursor = conn.execute(
                """
                SELECT job_id, hostname, 
                       json_extract(job_info_json, '$.state') as state,
                       json_extract(job_info_json, '$.submit_time') as submit_time,
                       json_extract(job_info_json, '$.runtime') as runtime
                FROM cached_jobs 
                WHERE is_active = 1
                  AND (state = 'PD' OR state = 'UNKNOWN')
                  AND cached_at < ?
                """,
                (cutoff.isoformat(),),
            )

            for row in cursor.fetchall():
                # Zombie indicators: no runtime (never started) and old submit time
                runtime = row["runtime"]

                if not runtime or runtime in ("N/A", "", "0:00"):
                    zombies.append((row["job_id"], row["hostname"], row["state"]))

        return zombies

    def clear_all(self) -> int:
        """
        Clear all cache entries from all tables.

        Returns:
            Total number of entries deleted
        """
        deleted_count = 0
        with self._get_connection() as conn:
            # Clear cached jobs
            cursor = conn.execute("DELETE FROM cached_jobs")
            deleted_count += cursor.rowcount

            # Clear date range cache (correct table name)
            cursor = conn.execute("DELETE FROM cached_job_ranges")
            deleted_count += cursor.rowcount

            # Clear host fetch state
            cursor = conn.execute("DELETE FROM host_fetch_state")
            deleted_count += cursor.rowcount

            conn.commit()
            logger.info(
                f"Cleared all cache entries: {deleted_count} total entries deleted"
            )

        return deleted_count

    def cleanup_other_users_jobs(
        self, hostname: Optional[str] = None, keep_user: Optional[str] = None
    ) -> int:
        """
        Remove jobs from other users to clean up cache pollution.

        This is useful when the cache accidentally gets filled with other users' jobs
        due to skip_user_detection=True being used incorrectly.

        Args:
            hostname: Optional hostname filter (if None, cleans all hosts)
            keep_user: Optional user to keep (if None, auto-detects current user per host)

        Returns:
            Number of jobs deleted
        """
        deleted_count = 0

        with self._get_connection() as conn:
            if hostname:
                hostnames = [hostname]
            else:
                # Get all unique hostnames
                cursor = conn.execute("SELECT DISTINCT hostname FROM cached_jobs")
                hostnames = [row["hostname"] for row in cursor.fetchall()]

            for host in hostnames:
                user_to_keep = keep_user

                # If no user specified, try to detect the current user for this host
                if not user_to_keep:
                    try:
                        from .web.app import get_slurm_manager

                        manager = get_slurm_manager()
                        if manager:
                            slurm_host = manager.get_host_by_name(host)
                            conn_ssh = manager._get_connection(slurm_host.host)
                            user_to_keep = manager.slurm_client.get_username(conn_ssh)
                            logger.info(
                                f"Auto-detected current user for {host}: {user_to_keep}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Could not auto-detect user for {host}: {e}. "
                            f"Skipping cleanup for this host."
                        )
                        continue

                if user_to_keep:
                    # Delete all jobs on this host that don't belong to the user
                    cursor = conn.execute(
                        """
                        DELETE FROM cached_jobs
                        WHERE hostname = ?
                          AND (json_extract(job_info_json, '$.user') != ?
                               OR json_extract(job_info_json, '$.user') IS NULL)
                    """,
                        (host, user_to_keep),
                    )

                    host_deleted = cursor.rowcount
                    deleted_count += host_deleted

                    if host_deleted > 0:
                        logger.info(
                            f"Deleted {host_deleted} jobs from other users on {host} "
                            f"(keeping only user: {user_to_keep})"
                        )

            conn.commit()

        if deleted_count > 0:
            logger.info(
                f"Cache cleanup complete: removed {deleted_count} jobs from other users"
            )
        else:
            logger.info("No jobs from other users found in cache")

        return deleted_count

    def cleanup_by_size(self, max_size_mb: int) -> int:
        """
        Clean up cache entries to stay under size limit.
        Removes oldest entries first, but preserves scripts.

        Args:
            max_size_mb: Maximum cache size in MB

        Returns:
            Number of entries cleaned up
        """
        current_size_mb = (
            self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
        )

        if current_size_mb <= max_size_mb:
            return 0

        logger.info(
            f"Cache size ({current_size_mb:.1f}MB) exceeds limit ({max_size_mb}MB), cleaning up"
        )

        deleted_count = 0
        with self._get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM cached_jobs 
                WHERE (script_content IS NULL OR script_content = "")
                  AND job_id IN (
                    SELECT job_id FROM cached_jobs 
                    WHERE (script_content IS NULL OR script_content = "")
                    ORDER BY cached_at ASC 
                    LIMIT 100
                  )
            """)
            deleted_count = cursor.rowcount
            conn.commit()
        current_size_mb = self.db_path.stat().st_size / (1024 * 1024)
        if current_size_mb > max_size_mb:
            logger.warning(
                "Still over size limit after cleanup, consider increasing limit or manual cleanup"
            )

        return deleted_count

    def export_cache_data(
        self, output_file: Path, job_ids: Optional[List[str]] = None
    ) -> int:
        """
        Export cache data to JSON for backup/archival.

        Args:
            output_file: Path to output JSON file
            job_ids: Optional list of specific job IDs to export

        Returns:
            Number of jobs exported
        """
        import json

        with self._get_connection() as conn:
            if job_ids:
                placeholders = ",".join("?" * len(job_ids))
                query = f"SELECT * FROM cached_jobs WHERE job_id IN ({placeholders})"
                cursor = conn.execute(query, job_ids)
            else:
                cursor = conn.execute(
                    "SELECT * FROM cached_jobs ORDER BY cached_at DESC"
                )

            export_data = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                export_data.append(row_dict)

            with open(output_file, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

            logger.info(f"Exported {len(export_data)} jobs to {output_file}")
            return len(export_data)

    def get_host_fetch_state(self, hostname: str) -> Optional[Dict[str, Any]]:
        """Get the last fetch state for a host.

        Args:
            hostname: The hostname to get fetch state for

        Returns:
            Dictionary with fetch state or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT last_fetch_time, last_fetch_time_utc, 
                       cluster_timezone, fetch_count, updated_at
                FROM host_fetch_state
                WHERE hostname = ?
                """,
                (hostname,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "last_fetch_time": row["last_fetch_time"],
                    "last_fetch_time_utc": row["last_fetch_time_utc"],
                    "cluster_timezone": row["cluster_timezone"],
                    "fetch_count": row["fetch_count"],
                    "updated_at": row["updated_at"],
                }
            return None

    def update_host_fetch_state(
        self,
        hostname: str,
        fetch_time: datetime,
        fetch_time_utc: datetime,
        cluster_timezone: Optional[str] = None,
    ):
        """Update the last fetch state for a host.

        Args:
            hostname: The hostname to update
            fetch_time: The fetch time in cluster's local timezone
            fetch_time_utc: The fetch time in UTC for consistency
            cluster_timezone: The cluster's timezone (e.g., 'America/New_York')
        """
        with self._get_connection() as conn:
            # Get existing fetch count
            cursor = conn.execute(
                "SELECT fetch_count FROM host_fetch_state WHERE hostname = ?",
                (hostname,),
            )
            row = cursor.fetchone()
            fetch_count = (row["fetch_count"] + 1) if row else 1

            conn.execute(
                """
                INSERT OR REPLACE INTO host_fetch_state
                (hostname, last_fetch_time, last_fetch_time_utc, 
                 cluster_timezone, fetch_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hostname,
                    fetch_time.isoformat(),
                    fetch_time_utc.isoformat(),
                    cluster_timezone,
                    fetch_count,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            logger.debug(
                f"Updated fetch state for {hostname}: "
                f"last_fetch={fetch_time_utc.isoformat()} (UTC), count={fetch_count}"
            )

    def get_cached_completed_job_ids(
        self, hostname: str, since: Optional[datetime] = None, max_age_days: int = 90
    ) -> Set[str]:
        """Get IDs of all cached completed jobs for a host - FAST lookup.

        This is used to avoid re-querying Slurm for jobs we already have cached.
        Much faster than fetching full job data.

        Args:
            hostname: The hostname to get job IDs for
            since: Optional datetime to filter jobs submitted after this time
            max_age_days: Maximum age in days for cached jobs to be considered valid.
                         Jobs older than this are likely recycled IDs. Default 90 days.

        Returns:
            Set of job IDs that are completed (is_active = 0) in cache and not too old
        """
        with self._get_connection() as conn:
            from datetime import timezone

            # Calculate cutoff date for old jobs
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

            query = """
                SELECT job_id 
                FROM cached_jobs 
                WHERE hostname = ? AND is_active = 0
                  AND json_extract(job_info_json, '$.submit_time') >= ?
            """
            params = [hostname, cutoff_date.isoformat()]

            if since:
                # Also filter by the provided since date (use the more recent of the two)
                effective_since = (
                    max(since, cutoff_date)
                    if since.tzinfo
                    else max(since.replace(tzinfo=timezone.utc), cutoff_date)
                )
                params[1] = effective_since.isoformat()

            cursor = conn.execute(query, params)
            job_ids = {row["job_id"] for row in cursor.fetchall()}

            if job_ids:
                logger.debug(
                    f"Found {len(job_ids)} completed jobs in cache for {hostname} "
                    f"(excluding jobs older than {max_age_days} days)"
                )

            return job_ids

    def get_cached_completed_jobs(
        self, hostname: str, since: Optional[datetime] = None
    ) -> List[JobInfo]:
        """Get cached completed jobs for a host.

        Args:
            hostname: The hostname to get jobs for
            since: Optional datetime to filter jobs submitted after this time (assumed UTC)

        Returns:
            List of cached completed jobs
        """
        jobs = []
        with self._get_connection() as conn:
            query = """
                SELECT job_info_json 
                FROM cached_jobs 
                WHERE hostname = ? AND is_active = 0
            """
            params = [hostname]

            if since:
                # Get cluster timezone info for this host
                host_fetch_state = self.get_host_fetch_state(hostname)
                cluster_timezone = (
                    host_fetch_state.get("cluster_timezone")
                    if host_fetch_state
                    else None
                )

                # Convert UTC 'since' time to cluster's local timezone
                if cluster_timezone and since.tzinfo:
                    try:
                        import zoneinfo

                        cluster_tz = zoneinfo.ZoneInfo(cluster_timezone)
                        since_local = since.astimezone(cluster_tz)
                        # Strip timezone info for comparison with stored times (which have no timezone)
                        since_for_comparison = since_local.replace(tzinfo=None)
                    except (ImportError, Exception) as e:
                        logger.warning(
                            f"Failed to convert timezone for {hostname}: {e}, using UTC time"
                        )
                        since_for_comparison = since.replace(tzinfo=None)
                else:
                    # No timezone info available, strip timezone from since parameter
                    since_for_comparison = (
                        since.replace(tzinfo=None) if since.tzinfo else since
                    )

                # Filter by submit time if available in the JSON
                query += " AND datetime(json_extract(job_info_json, '$.submit_time')) > datetime(?)"
                params.append(since_for_comparison.isoformat())

            query += " ORDER BY json_extract(job_info_json, '$.submit_time') DESC"

            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                try:
                    job_dict = json.loads(row["job_info_json"])
                    # Convert state string back to JobState enum if needed
                    if "state" in job_dict and isinstance(job_dict["state"], str):
                        from .models.job import JobState

                        try:
                            job_dict["state"] = JobState(job_dict["state"])
                        except ValueError:
                            # Fallback for unknown states
                            job_dict["state"] = JobState.UNKNOWN
                    job_info = JobInfo(**job_dict)
                    jobs.append(job_info)
                except Exception as e:
                    logger.warning(f"Failed to parse cached job: {e}")

        return jobs

    def close(self):
        """Clean up resources. Does NOT perform cleanup to preserve data."""
        logger.info("Job cache closed (data preserved)")


_cache_instance: Optional[JobDataCache] = None
_cache_lock = threading.Lock()


def get_cache() -> JobDataCache:
    """Get or create global cache instance."""
    global _cache_instance

    with _cache_lock:
        if _cache_instance is None:
            from .utils.config import config as app_config

            cache_settings = app_config.cache_settings

            cache_dir = (
                Path(cache_settings.cache_dir).expanduser()
                if cache_settings.cache_dir
                else None
            )

            _cache_instance = JobDataCache(
                cache_dir=cache_dir, max_age_days=cache_settings.max_age_days
            )

            # Log cache strategy
            if cache_settings.max_age_days == 0:
                logger.info("Cache initialized in PRESERVATION mode (never expires)")
            else:
                logger.info(
                    f"Cache initialized with {cache_settings.max_age_days} day retention policy"
                )

            if cache_settings.script_max_age_days == 0:
                logger.info("Scripts will be preserved indefinitely")

        return _cache_instance
