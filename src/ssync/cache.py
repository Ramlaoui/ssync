"""
Simple but powerful caching mechanism for SLURM job data.

This module provides persistent caching for job information, scripts, and outputs
to preserve data even when jobs are no longer queryable from SLURM.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    stdout_content: Optional[str] = None
    stderr_content: Optional[str] = None
    cached_at: datetime = None
    last_updated: datetime = None
    is_active: bool = True  # Whether job is still running/pending

    def __post_init__(self):
        if self.cached_at is None:
            self.cached_at = datetime.now()
        if self.last_updated is None:
            self.last_updated = datetime.now()


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
            cache_dir: Directory to store cache files. Defaults to ~/.ssync/cache
            max_age_days: Maximum age of cached data in days before cleanup (0 = never expire)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".ssync" / "cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.cache_dir / "jobs.db"
        self.max_age_days = max_age_days

        # Thread safety
        self._lock = threading.RLock()

        # Initialize database
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cached_jobs (
                    job_id TEXT,
                    hostname TEXT,
                    job_info_json TEXT NOT NULL,
                    script_content TEXT,
                    stdout_content TEXT,
                    stderr_content TEXT,
                    cached_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    PRIMARY KEY (job_id, hostname)
                )
            """)

            # Create indexes for common queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hostname ON cached_jobs(hostname)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cached_at ON cached_jobs(cached_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_is_active ON cached_jobs(is_active)"
            )

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get thread-safe database connection."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def cache_job(
        self,
        job_info: JobInfo,
        script_content: Optional[str] = None,
        stdout_content: Optional[str] = None,
        stderr_content: Optional[str] = None,
    ):
        """
        Cache job information and associated data.

        Args:
            job_info: JobInfo object to cache
            script_content: Optional script content
            stdout_content: Optional stdout content
            stderr_content: Optional stderr content
        """
        now = datetime.now()
        is_active = job_info.state in ["PD", "R"]  # Pending or Running

        cached_data = CachedJobData(
            job_id=job_info.job_id,
            hostname=job_info.hostname,
            job_info=job_info,
            script_content=script_content,
            stdout_content=stdout_content,
            stderr_content=stderr_content,
            cached_at=now,
            last_updated=now,
            is_active=is_active,
        )

        self._store_cached_data(cached_data)
        logger.debug(f"Cached job {job_info.job_id} on {job_info.hostname}")

    def _store_cached_data(self, cached_data: CachedJobData):
        """Store cached data in database."""
        with self._get_connection() as conn:
            job_info_dict = asdict(cached_data.job_info)

            # Convert enums to strings for JSON serialization
            job_info_dict = self._prepare_dict_for_json(job_info_dict)

            conn.execute(
                """
                INSERT OR REPLACE INTO cached_jobs 
                (job_id, hostname, job_info_json, script_content, stdout_content, 
                 stderr_content, cached_at, last_updated, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    cached_data.job_id,
                    cached_data.hostname,
                    json.dumps(job_info_dict),
                    cached_data.script_content,
                    cached_data.stdout_content,
                    cached_data.stderr_content,
                    cached_data.cached_at.isoformat(),
                    cached_data.last_updated.isoformat(),
                    cached_data.is_active,
                ),
            )
            conn.commit()

    def get_cached_job(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[CachedJobData]:
        """
        Retrieve cached job data.

        Args:
            job_id: Job ID to look up
            hostname: Optional hostname filter

        Returns:
            CachedJobData if found, None otherwise
        """
        with self._get_connection() as conn:
            if hostname:
                cursor = conn.execute(
                    "SELECT * FROM cached_jobs WHERE job_id = ? AND hostname = ?",
                    (job_id, hostname),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM cached_jobs WHERE job_id = ?", (job_id,)
                )

            row = cursor.fetchone()
            if row:
                return self._row_to_cached_data(row)

            return None

    def get_cached_jobs(
        self,
        hostname: Optional[str] = None,
        active_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[CachedJobData]:
        """
        Get list of cached jobs with optional filtering.

        Args:
            hostname: Optional hostname filter
            active_only: If True, only return active jobs
            limit: Optional limit on number of results

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

        return CachedJobData(
            job_id=row["job_id"],
            hostname=row["hostname"],
            job_info=job_info,
            script_content=row["script_content"],
            stdout_content=row["stdout_content"],
            stderr_content=row["stderr_content"],
            cached_at=datetime.fromisoformat(row["cached_at"]),
            last_updated=datetime.fromisoformat(row["last_updated"]),
            is_active=bool(row["is_active"]),
        )

    def update_job_outputs(
        self,
        job_id: str,
        hostname: str,
        stdout_content: Optional[str] = None,
        stderr_content: Optional[str] = None,
    ):
        """
        Update cached job outputs without replacing the entire entry.

        Args:
            job_id: Job ID
            hostname: Hostname
            stdout_content: Updated stdout content
            stderr_content: Updated stderr content
        """
        with self._get_connection() as conn:
            updates = []
            params = []

            if stdout_content is not None:
                updates.append("stdout_content = ?")
                params.append(stdout_content)

            if stderr_content is not None:
                updates.append("stderr_content = ?")
                params.append(stderr_content)

            if updates:
                updates.append("last_updated = ?")
                params.append(datetime.now().isoformat())

                query = f"""
                    UPDATE cached_jobs 
                    SET {", ".join(updates)}
                    WHERE job_id = ? AND hostname = ?
                """
                params.extend([job_id, hostname])

                conn.execute(query, params)
                conn.commit()

                logger.debug(f"Updated outputs for job {job_id} on {hostname}")

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

            logger.debug(f"Marked job {job_id} on {hostname} as completed")

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
        if max_age_days is None:
            max_age_days = self.max_age_days

        # If max_age_days is 0, never expire unless forced
        if max_age_days == 0 and not force_cleanup:
            logger.info("Cache cleanup skipped (max_age_days=0, preservation mode)")
            return 0

        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        with self._get_connection() as conn:
            # Build cleanup query with preservation logic
            query = "DELETE FROM cached_jobs WHERE cached_at < ?"
            params = [cutoff_date.isoformat()]

            # Preserve entries with scripts unless forced
            if preserve_scripts and not force_cleanup:
                query += ' AND (script_content IS NULL OR script_content = "")'
                logger.info("Cleaning up old cache entries (preserving scripts)")
            else:
                logger.warning("Cleaning up old cache entries (including scripts!)")

            cursor = conn.execute(query, params)
            deleted_count = cursor.rowcount
            conn.commit()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old cache entries")

            return deleted_count

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._get_connection() as conn:
            # Total jobs
            cursor = conn.execute("SELECT COUNT(*) as total FROM cached_jobs")
            total = cursor.fetchone()["total"]

            # Active jobs
            cursor = conn.execute(
                "SELECT COUNT(*) as active FROM cached_jobs WHERE is_active = 1"
            )
            active = cursor.fetchone()["active"]

            # Jobs by hostname
            cursor = conn.execute("""
                SELECT hostname, COUNT(*) as count 
                FROM cached_jobs 
                GROUP BY hostname 
                ORDER BY count DESC
            """)
            by_hostname = {row["hostname"]: row["count"] for row in cursor.fetchall()}

            # Jobs with scripts/outputs
            cursor = conn.execute(
                "SELECT COUNT(*) as with_scripts FROM cached_jobs WHERE script_content IS NOT NULL"
            )
            with_scripts = cursor.fetchone()["with_scripts"]

            cursor = conn.execute(
                "SELECT COUNT(*) as with_stdout FROM cached_jobs WHERE stdout_content IS NOT NULL"
            )
            with_stdout = cursor.fetchone()["with_stdout"]

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
            }

    def verify_cached_jobs(
        self, current_job_ids: Dict[str, List[str]]
    ) -> List[Tuple[str, str]]:
        """
        Verify cached jobs against current SLURM state and return jobs to mark as completed.

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
            # Remove oldest entries without scripts first
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

        # Check if we need more aggressive cleanup
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

    def close(self):
        """Clean up resources. Does NOT perform cleanup to preserve data."""
        logger.info("Job cache closed (data preserved)")


# Global cache instance
_cache_instance: Optional[JobDataCache] = None
_cache_lock = threading.Lock()


def get_cache() -> JobDataCache:
    """Get or create global cache instance."""
    global _cache_instance

    with _cache_lock:
        if _cache_instance is None:
            cache_dir = os.getenv("SSYNC_CACHE_DIR")
            max_age = int(
                os.getenv("SSYNC_CACHE_MAX_AGE_DAYS", "365")
            )  # Conservative default

            _cache_instance = JobDataCache(
                cache_dir=Path(cache_dir) if cache_dir else None, max_age_days=max_age
            )

            # Log cache strategy
            if max_age == 0:
                logger.info("Cache initialized in PRESERVATION mode (never expires)")
            else:
                logger.info(f"Cache initialized with {max_age} day retention policy")

        return _cache_instance
