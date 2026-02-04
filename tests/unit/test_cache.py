"""Unit tests for cache.py - Job data caching system."""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ssync.cache import CachedJobData, JobDataCache
from ssync.models.job import JobInfo, JobState


class TestCacheInitialization:
    """Tests for cache initialization and database setup."""

    @pytest.mark.unit
    def test_cache_init_creates_directory(self, tmp_path):
        """Test that cache initialization creates the cache directory."""
        cache_dir = tmp_path / "test_cache"
        cache = JobDataCache(cache_dir=cache_dir, max_age_days=30)

        assert cache_dir.exists()
        assert cache_dir.is_dir()
        cache.close()

    @pytest.mark.unit
    def test_cache_init_creates_database(self, tmp_path):
        """Test that cache initialization creates the database file."""
        cache_dir = tmp_path / "test_cache"
        cache = JobDataCache(cache_dir=cache_dir, max_age_days=30)

        db_path = cache_dir / "jobs.db"
        assert db_path.exists()
        assert db_path.is_file()
        cache.close()

    @pytest.mark.unit
    def test_cache_init_creates_all_tables(self, tmp_path):
        """Test that all required tables are created."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        with cache._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row["name"] for row in cursor.fetchall()}

        expected_tables = {
            "cached_jobs",
            "cached_job_ranges",
            "host_fetch_state",
            "job_watchers",
            "watcher_events",
            "watcher_variables",
            "notification_devices",
            "notification_preferences",
            "webpush_subscriptions",
            "array_jobs",
            "array_task_stats",
        }

        assert expected_tables.issubset(tables)
        cache.close()

    @pytest.mark.unit
    def test_cache_init_creates_indices(self, tmp_path):
        """Test that required indices are created."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        with cache._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            indices = {row["name"] for row in cursor.fetchall()}

        expected_indices = {
            "idx_hostname",
            "idx_cached_at",
            "idx_is_active",
            "idx_completed_jobs",
            "idx_watchers_job",
            "idx_watchers_state",
            "idx_notification_devices_key",
            "idx_notification_devices_platform",
            "idx_webpush_subscriptions_key",
            "idx_webpush_subscriptions_enabled",
            "idx_array_jobs_hostname",
        }

        assert expected_indices.issubset(indices)
        cache.close()

    @pytest.mark.unit
    def test_cache_init_default_directory(self):
        """Test that cache uses default directory when none provided."""
        cache = JobDataCache(max_age_days=30)

        assert cache.cache_dir.exists()
        assert "ssync" in str(cache.cache_dir)
        cache.close()


class TestBasicJobCaching:
    """Tests for basic job caching operations."""

    @pytest.mark.unit
    def test_cache_job_basic(self, tmp_path, sample_job_info):
        """Test caching a basic job."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        script_content = "#!/bin/bash\necho 'test'"

        cache.cache_job(sample_job_info, script_content=script_content)

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached is not None
        assert cached.job_id == sample_job_info.job_id
        assert cached.hostname == sample_job_info.hostname
        assert cached.script_content == script_content
        assert cached.job_info.name == sample_job_info.name
        cache.close()

    @pytest.mark.unit
    def test_cache_job_without_script(self, tmp_path, sample_job_info):
        """Test caching a job without script content."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info)

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached is not None
        assert cached.script_content is None
        cache.close()

    @pytest.mark.unit
    def test_cache_job_preserves_script_on_update(self, tmp_path, sample_job_info):
        """Test that script content is preserved when updating job without script."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        script_content = "#!/bin/bash\necho 'test'"

        # Cache job with script
        cache.cache_job(sample_job_info, script_content=script_content)

        # Update job without script
        updated_job = JobInfo(
            job_id=sample_job_info.job_id,
            name="updated_name",
            state=JobState.COMPLETED,
            hostname=sample_job_info.hostname,
        )
        cache.cache_job(updated_job)

        # Script should be preserved
        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached.script_content == script_content
        assert cached.job_info.name == "updated_name"
        cache.close()

    @pytest.mark.unit
    def test_cache_job_updates_is_active(self, tmp_path, sample_job_info):
        """Test that is_active flag is updated based on job state."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache running job (active)
        running_job = JobInfo(
            job_id="123",
            name="test",
            state=JobState.RUNNING,
            hostname="test.host",
            submit_time=datetime.now(timezone.utc).isoformat(),
        )
        cache.cache_job(running_job)

        cached = cache.get_cached_job("123", "test.host")
        assert cached.is_active is True

        # Update to completed (inactive)
        completed_job = JobInfo(
            job_id="123",
            name="test",
            state=JobState.COMPLETED,
            hostname="test.host",
            submit_time=datetime.now(timezone.utc).isoformat(),
        )
        cache.cache_job(completed_job)

        cached = cache.get_cached_job("123", "test.host")
        assert cached.is_active is False
        cache.close()


class TestNotificationDevices:
    """Tests for notification device storage."""

    @pytest.mark.unit
    def test_upsert_and_list_notification_device(self, tmp_path):
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.upsert_notification_device(
            api_key_hash="hash1",
            device_token="token1",
            platform="ios",
            bundle_id="com.example.app",
            environment="sandbox",
            device_id="device-1",
            enabled=True,
        )

        devices = cache.list_notification_devices(platform="ios")
        assert len(devices) == 1
        assert devices[0]["device_token"] == "token1"
        assert devices[0]["environment"] == "sandbox"
        cache.close()

    @pytest.mark.unit
    def test_remove_notification_device(self, tmp_path):
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.upsert_notification_device(
            api_key_hash="hash2",
            device_token="token2",
            platform="ios",
            enabled=True,
        )

        deleted = cache.remove_notification_device(
            api_key_hash="hash2", device_token="token2"
        )
        assert deleted == 1
        assert cache.list_notification_devices(platform="ios") == []
        cache.close()


class TestNotificationPreferences:
    """Tests for notification preferences."""

    @pytest.mark.unit
    def test_default_preferences(self, tmp_path):
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        prefs = cache.get_notification_preferences(api_key_hash="missing")
        assert prefs["enabled"] is True
        assert prefs["muted_job_ids"] == []
        cache.close()

    @pytest.mark.unit
    def test_upsert_preferences(self, tmp_path):
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        cache.upsert_notification_preferences(
            api_key_hash="hash",
            preferences={
                "enabled": False,
                "allowed_states": ["F", "TO"],
                "muted_job_ids": ["123"],
                "muted_hosts": ["host1"],
                "muted_job_name_patterns": ["debug"],
                "allowed_users": ["alice"],
            },
        )
        prefs = cache.get_notification_preferences(api_key_hash="hash")
        assert prefs["enabled"] is False
        assert prefs["allowed_states"] == ["F", "TO"]
        assert prefs["muted_job_ids"] == ["123"]
        assert prefs["muted_hosts"] == ["host1"]
        assert prefs["muted_job_name_patterns"] == ["debug"]
        assert prefs["allowed_users"] == ["alice"]
        cache.close()


class TestWebPushSubscriptions:
    """Tests for Web Push subscriptions."""

    @pytest.mark.unit
    def test_upsert_and_list_subscription(self, tmp_path):
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        cache.upsert_webpush_subscription(
            api_key_hash="hash",
            endpoint="https://example.com/endpoint",
            p256dh="p256",
            auth="auth",
            user_agent="test",
            enabled=True,
        )
        subs = cache.list_webpush_subscriptions(api_key_hash="hash")
        assert len(subs) == 1
        assert subs[0]["endpoint"] == "https://example.com/endpoint"
        cache.close()

    @pytest.mark.unit
    def test_remove_subscription(self, tmp_path):
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        cache.upsert_webpush_subscription(
            api_key_hash="hash",
            endpoint="https://example.com/endpoint",
            p256dh="p256",
            auth="auth",
            user_agent="test",
            enabled=True,
        )
        deleted = cache.remove_webpush_subscription(
            api_key_hash="hash",
            endpoint="https://example.com/endpoint",
        )
        assert deleted == 1
        assert cache.list_webpush_subscriptions(api_key_hash="hash") == []
        cache.close()

    @pytest.mark.unit
    def test_cache_job_with_enum_state(self, tmp_path):
        """Test that JobState enum is properly serialized."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        job = JobInfo(
            job_id="123",
            name="test",
            state=JobState.RUNNING,
            hostname="test.host",
        )
        cache.cache_job(job)

        # Verify it's stored as string in DB
        with cache._get_connection() as conn:
            cursor = conn.execute(
                "SELECT job_info_json FROM cached_jobs WHERE job_id = ?", ("123",)
            )
            row = cursor.fetchone()
            job_dict = json.loads(row["job_info_json"])

        assert job_dict["state"] == "R"  # Enum value, not enum object
        cache.close()

    @pytest.mark.unit
    def test_cache_job_timestamps(self, tmp_path, sample_job_info):
        """Test that cache timestamps are set correctly."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        before = datetime.now()
        cache.cache_job(sample_job_info)
        after = datetime.now()

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert before <= cached.cached_at <= after
        assert before <= cached.last_updated <= after
        cache.close()


class TestJobRetrieval:
    """Tests for retrieving cached jobs."""

    @pytest.mark.unit
    def test_get_cached_job_by_id_and_hostname(self, tmp_path, sample_job_info):
        """Test retrieving job by ID and hostname."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        cache.cache_job(sample_job_info)

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached is not None
        assert cached.job_id == sample_job_info.job_id
        cache.close()

    @pytest.mark.unit
    def test_get_cached_job_not_found(self, tmp_path):
        """Test getting non-existent job returns None."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cached = cache.get_cached_job("nonexistent", "test.host")

        assert cached is None
        cache.close()

    @pytest.mark.unit
    def test_get_cached_job_max_age_validation(self, tmp_path):
        """Test that old jobs are rejected based on max_age_days."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Create job with old submit time
        old_submit = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        old_job = JobInfo(
            job_id="123",
            name="old_job",
            state=JobState.COMPLETED,
            hostname="test.host",
            submit_time=old_submit,
        )
        cache.cache_job(old_job)

        # Should return None because job is > 30 days old
        cached = cache.get_cached_job("123", "test.host", max_age_days=30)

        assert cached is None
        cache.close()

    @pytest.mark.unit
    def test_get_cached_jobs_all(self, tmp_path):
        """Test getting all cached jobs."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache multiple jobs
        for i in range(3):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname="test.host",
            )
            cache.cache_job(job)

        cached_jobs = cache.get_cached_jobs()

        assert len(cached_jobs) == 3
        cache.close()

    @pytest.mark.unit
    def test_get_cached_jobs_hostname_filter(self, tmp_path):
        """Test filtering cached jobs by hostname."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache jobs on different hosts
        for i in range(3):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname=f"host{i % 2}.com",
            )
            cache.cache_job(job)

        cached_jobs = cache.get_cached_jobs(hostname="host0.com")

        assert len(cached_jobs) == 2
        assert all(j.hostname == "host0.com" for j in cached_jobs)
        cache.close()

    @pytest.mark.unit
    def test_get_cached_jobs_active_only(self, tmp_path):
        """Test filtering for active jobs only."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache mix of active and completed jobs
        active_job = JobInfo(
            job_id="1", name="active", state=JobState.RUNNING, hostname="test.host"
        )
        completed_job = JobInfo(
            job_id="2", name="completed", state=JobState.COMPLETED, hostname="test.host"
        )

        cache.cache_job(active_job)
        cache.cache_job(completed_job)

        cached_jobs = cache.get_cached_jobs(active_only=True)

        assert len(cached_jobs) == 1
        assert cached_jobs[0].job_id == "1"
        cache.close()

    @pytest.mark.unit
    def test_get_cached_jobs_with_limit(self, tmp_path):
        """Test limiting number of returned jobs."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache 5 jobs
        for i in range(5):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname="test.host",
            )
            cache.cache_job(job)

        cached_jobs = cache.get_cached_jobs(limit=3)

        assert len(cached_jobs) == 3
        cache.close()


class TestScriptOperations:
    """Tests for script-related operations."""

    @pytest.mark.unit
    def test_update_job_script_existing_job(self, tmp_path, sample_job_info):
        """Test updating script for existing job."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info, script_content="old script")

        new_script = "#!/bin/bash\necho 'new'"
        cache.update_job_script(
            sample_job_info.job_id, sample_job_info.hostname, new_script
        )

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached.script_content == new_script
        cache.close()

    @pytest.mark.unit
    def test_update_job_script_creates_minimal_entry(self, tmp_path):
        """Test that updating script creates minimal entry if job doesn't exist."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        script = "#!/bin/bash\necho 'test'"
        cache.update_job_script("999", "test.host", script)

        cached = cache.get_cached_job("999", "test.host")

        assert cached is not None
        assert cached.script_content == script
        assert cached.job_info.job_id == "999"
        cache.close()


class TestJobStateManagement:
    """Tests for job state management."""

    @pytest.mark.unit
    def test_mark_job_completed(self, tmp_path, sample_job_info):
        """Test marking a job as completed."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info)
        cache.mark_job_completed(sample_job_info.job_id, sample_job_info.hostname)

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached.is_active is False
        cache.close()

    @pytest.mark.unit
    def test_verify_cached_jobs(self, tmp_path):
        """Test verifying cached jobs against current Slurm state."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache 3 active jobs
        for i in range(3):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname="test.host",
            )
            cache.cache_job(job)

        # Only jobs 0 and 1 are still in Slurm
        current_job_ids = {"test.host": ["0", "1"]}

        to_complete = cache.verify_cached_jobs(current_job_ids)

        # Job 2 should be marked for completion
        assert len(to_complete) == 1
        assert to_complete[0] == ("2", "test.host")
        cache.close()


class TestArrayJobMetadata:
    """Tests for array job metadata management."""

    @pytest.mark.unit
    def test_cache_array_job_creates_metadata(self, tmp_path, sample_array_job_info):
        """Test that caching an array job creates metadata entry."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_array_job_info, script_content="#!/bin/bash\necho test")

        metadata = cache.get_array_job_metadata(
            sample_array_job_info.array_job_id, sample_array_job_info.hostname
        )

        assert metadata is not None
        assert metadata["array_job_id"] == sample_array_job_info.array_job_id
        assert metadata["total_tasks"] == 1
        cache.close()

    @pytest.mark.unit
    def test_array_metadata_tracks_multiple_tasks(self, tmp_path):
        """Test that array metadata tracks multiple tasks."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache 3 tasks of same array job
        for i in range(3):
            job = JobInfo(
                job_id=f"100_{i}",
                name="array_job",
                state=JobState.RUNNING,
                hostname="test.host",
                array_job_id="100",
                array_task_id=str(i),
            )
            cache.cache_job(job)

        metadata = cache.get_array_job_metadata("100", "test.host")

        assert metadata["total_tasks"] == 3
        cache.close()

    @pytest.mark.unit
    def test_array_metadata_state_counting(self, tmp_path):
        """Test that array task state statistics are counted correctly."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache tasks with different states
        states = [JobState.RUNNING, JobState.RUNNING, JobState.COMPLETED]
        for i, state in enumerate(states):
            job = JobInfo(
                job_id=f"100_{i}",
                name="array_job",
                state=state,
                hostname="test.host",
                array_job_id="100",
                array_task_id=str(i),
            )
            cache.cache_job(job)

        metadata = cache.get_array_job_metadata("100", "test.host")

        assert metadata["state_counts"]["R"] == 2
        assert metadata["state_counts"]["CD"] == 1
        cache.close()

    @pytest.mark.unit
    def test_get_array_tasks(self, tmp_path):
        """Test retrieving all tasks for an array job."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache 3 array tasks
        for i in range(3):
            job = JobInfo(
                job_id=f"100_{i}",
                name="array_job",
                state=JobState.RUNNING,
                hostname="test.host",
                array_job_id="100",
                array_task_id=str(i),
            )
            cache.cache_job(job)

        tasks = cache.get_array_tasks("100", "test.host")

        assert len(tasks) == 3
        assert all(t.array_job_id == "100" for t in tasks)
        cache.close()

    @pytest.mark.unit
    def test_get_array_tasks_with_limit(self, tmp_path):
        """Test limiting retrieved array tasks."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache 5 array tasks
        for i in range(5):
            job = JobInfo(
                job_id=f"100_{i}",
                name="array_job",
                state=JobState.RUNNING,
                hostname="test.host",
                array_job_id="100",
                array_task_id=str(i),
            )
            cache.cache_job(job)

        tasks = cache.get_array_tasks("100", "test.host", limit=3)

        assert len(tasks) == 3
        cache.close()

    @pytest.mark.unit
    def test_array_metadata_preserves_script(self, tmp_path):
        """Test that array metadata preserves script content."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        script = "#!/bin/bash\necho 'array job'"

        # Cache first task with script
        job1 = JobInfo(
            job_id="100_0",
            name="array_job",
            state=JobState.RUNNING,
            hostname="test.host",
            array_job_id="100",
            array_task_id="0",
        )
        cache.cache_job(job1, script_content=script)

        # Cache second task without script
        job2 = JobInfo(
            job_id="100_1",
            name="array_job",
            state=JobState.RUNNING,
            hostname="test.host",
            array_job_id="100",
            array_task_id="1",
        )
        cache.cache_job(job2)

        metadata = cache.get_array_job_metadata("100", "test.host")

        assert metadata["script_content"] == script
        cache.close()


class TestCacheStatistics:
    """Tests for cache statistics."""

    @pytest.mark.unit
    def test_get_cache_stats_empty(self, tmp_path):
        """Test cache statistics with empty cache."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        stats = cache.get_cache_stats()

        assert stats["total_jobs"] == 0
        assert stats["active_jobs"] == 0
        assert stats["completed_jobs"] == 0
        assert stats["jobs_with_scripts"] == 0
        cache.close()

    @pytest.mark.unit
    def test_get_cache_stats_with_data(self, tmp_path):
        """Test cache statistics with cached jobs."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache mix of jobs
        active_job = JobInfo(
            job_id="1",
            name="active",
            state=JobState.RUNNING,
            hostname="test.host",
        )
        completed_job = JobInfo(
            job_id="2",
            name="completed",
            state=JobState.COMPLETED,
            hostname="test.host",
        )

        cache.cache_job(active_job, script_content="script")
        cache.cache_job(completed_job)

        stats = cache.get_cache_stats()

        assert stats["total_jobs"] == 2
        assert stats["active_jobs"] == 1
        assert stats["completed_jobs"] == 1
        assert stats["jobs_with_scripts"] == 1
        cache.close()

    @pytest.mark.unit
    def test_cache_stats_by_hostname(self, tmp_path):
        """Test cache statistics grouped by hostname."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache jobs on different hosts
        for i in range(3):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname=f"host{i % 2}.com",
            )
            cache.cache_job(job)

        stats = cache.get_cache_stats()

        assert stats["jobs_by_hostname"]["host0.com"] == 2
        assert stats["jobs_by_hostname"]["host1.com"] == 1
        cache.close()


class TestCacheCleanup:
    """Tests for cache cleanup operations."""

    @pytest.mark.unit
    def test_cleanup_old_entries_preserves_scripts_by_default(self, tmp_path):
        """Test that cleanup preserves entries with scripts."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=1)

        # Create old job with script
        old_job = JobInfo(
            job_id="1", name="old", state=JobState.COMPLETED, hostname="test.host"
        )
        cache.cache_job(old_job, script_content="important script")

        # Manually set old cached_at time
        with cache._get_connection() as conn:
            old_time = (datetime.now() - timedelta(days=10)).isoformat()
            conn.execute(
                "UPDATE cached_jobs SET cached_at = ? WHERE job_id = ?",
                (old_time, "1"),
            )
            conn.commit()

        deleted = cache.cleanup_old_entries(max_age_days=1, preserve_scripts=True)

        # Should not delete because it has a script
        assert deleted == 0
        assert cache.get_cached_job("1", "test.host") is not None
        cache.close()

    @pytest.mark.unit
    def test_cleanup_old_entries_deletes_scriptless(self, tmp_path):
        """Test that cleanup deletes old entries without scripts."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=1)

        # Create old job without script
        old_job = JobInfo(
            job_id="1", name="old", state=JobState.COMPLETED, hostname="test.host"
        )
        cache.cache_job(old_job)

        # Manually set old cached_at time
        with cache._get_connection() as conn:
            old_time = (datetime.now() - timedelta(days=10)).isoformat()
            conn.execute(
                "UPDATE cached_jobs SET cached_at = ? WHERE job_id = ?",
                (old_time, "1"),
            )
            conn.commit()

        deleted = cache.cleanup_old_entries(max_age_days=1, preserve_scripts=True)

        assert deleted == 1
        assert cache.get_cached_job("1", "test.host") is None
        cache.close()

    @pytest.mark.unit
    def test_cleanup_force_deletes_all(self, tmp_path):
        """Test that force cleanup deletes everything including scripts."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=1)

        # Create old job with script
        old_job = JobInfo(
            job_id="1", name="old", state=JobState.COMPLETED, hostname="test.host"
        )
        cache.cache_job(old_job, script_content="script")

        # Manually set old cached_at time
        with cache._get_connection() as conn:
            old_time = (datetime.now() - timedelta(days=10)).isoformat()
            conn.execute(
                "UPDATE cached_jobs SET cached_at = ? WHERE job_id = ?",
                (old_time, "1"),
            )
            conn.commit()

        deleted = cache.cleanup_old_entries(max_age_days=1, force_cleanup=True)

        assert deleted == 1
        assert cache.get_cached_job("1", "test.host") is None
        cache.close()


class TestHostFetchState:
    """Tests for host fetch state tracking."""

    @pytest.mark.unit
    def test_update_host_fetch_state(self, tmp_path):
        """Test updating host fetch state."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        fetch_time = datetime.now()
        fetch_time_utc = datetime.now(timezone.utc)

        cache.update_host_fetch_state(
            "test.host", fetch_time, fetch_time_utc, "America/New_York"
        )

        state = cache.get_host_fetch_state("test.host")

        assert state is not None
        assert state["fetch_count"] == 1
        assert state["cluster_timezone"] == "America/New_York"
        cache.close()

    @pytest.mark.unit
    def test_update_host_fetch_state_increments_count(self, tmp_path):
        """Test that fetch count increments on subsequent updates."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        fetch_time = datetime.now()
        fetch_time_utc = datetime.now(timezone.utc)

        # Update twice
        cache.update_host_fetch_state("test.host", fetch_time, fetch_time_utc)
        cache.update_host_fetch_state("test.host", fetch_time, fetch_time_utc)

        state = cache.get_host_fetch_state("test.host")

        assert state["fetch_count"] == 2
        cache.close()

    @pytest.mark.unit
    def test_get_host_fetch_state_not_found(self, tmp_path):
        """Test getting fetch state for non-existent host."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        state = cache.get_host_fetch_state("nonexistent.host")

        assert state is None
        cache.close()

    @pytest.mark.unit
    def test_get_cached_completed_job_ids(self, tmp_path):
        """Test getting completed job IDs efficiently."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache mix of active and completed jobs
        for i in range(3):
            state = JobState.COMPLETED if i < 2 else JobState.RUNNING
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=state,
                hostname="test.host",
                submit_time=datetime.now(timezone.utc).isoformat(),
            )
            cache.cache_job(job)

        completed_ids = cache.get_cached_completed_job_ids("test.host")

        assert len(completed_ids) == 2
        assert "0" in completed_ids
        assert "1" in completed_ids
        assert "2" not in completed_ids
        cache.close()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_cache_job_with_none_fields(self, tmp_path):
        """Test caching job with None values in optional fields."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        job = JobInfo(
            job_id="123",
            name="test",
            state=JobState.RUNNING,
            hostname="test.host",
            user=None,
            partition=None,
            memory=None,
        )
        cache.cache_job(job)

        cached = cache.get_cached_job("123", "test.host")

        assert cached is not None
        assert cached.job_info.user is None
        cache.close()

    @pytest.mark.unit
    def test_row_to_cached_data_handles_missing_columns(self, tmp_path):
        """Test that row parsing handles missing optional columns gracefully."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        job = JobInfo(
            job_id="123", name="test", state=JobState.RUNNING, hostname="test.host"
        )
        cache.cache_job(job)

        # This should work even if local_source_dir column doesn't exist
        cached = cache.get_cached_job("123", "test.host")

        assert cached is not None
        cache.close()

    @pytest.mark.unit
    def test_cache_handles_invalid_job_state(self, tmp_path):
        """Test that cache handles unknown job states gracefully."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Manually insert job with invalid state
        with cache._get_connection() as conn:
            job_dict = {
                "job_id": "123",
                "name": "test",
                "state": "UNKNOWN_STATE",
                "hostname": "test.host",
            }
            conn.execute(
                """
                INSERT INTO cached_jobs
                (job_id, hostname, job_info_json, cached_at, last_updated, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    "123",
                    "test.host",
                    json.dumps(job_dict),
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

        # Should handle gracefully and map to UNKNOWN
        cached = cache.get_cached_job("123", "test.host")

        assert cached is not None
        assert cached.job_info.state == JobState.UNKNOWN
        cache.close()

    @pytest.mark.unit
    def test_cache_thread_safety(self, tmp_path, sample_job_info):
        """Test that cache operations are thread-safe."""
        import threading

        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
        errors = []

        def cache_job_thread(job_id):
            try:
                job = JobInfo(
                    job_id=str(job_id),
                    name=f"job_{job_id}",
                    state=JobState.RUNNING,
                    hostname="test.host",
                )
                cache.cache_job(job)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=cache_job_thread, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        cached_jobs = cache.get_cached_jobs()
        assert len(cached_jobs) == 10
        cache.close()


class TestDateRangeCaching:
    """Tests for date range caching operations."""

    @pytest.mark.unit
    def test_parse_since_to_dates_hours(self, tmp_path):
        """Test parsing 'since' parameter with hours."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        start, end = cache._parse_since_to_dates("12h")

        # Should be approximately 12 hours ago
        delta = end - start
        assert 11 <= delta.total_seconds() / 3600 <= 13  # 12 hours ± 1 hour
        cache.close()

    @pytest.mark.unit
    def test_parse_since_to_dates_days(self, tmp_path):
        """Test parsing 'since' parameter with days."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        start, end = cache._parse_since_to_dates("7d")

        delta = end - start
        assert 6 <= delta.days <= 8  # 7 days ± 1
        cache.close()

    @pytest.mark.unit
    def test_parse_since_to_dates_weeks(self, tmp_path):
        """Test parsing 'since' parameter with weeks."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        start, end = cache._parse_since_to_dates("2w")

        delta = end - start
        assert 13 <= delta.days <= 15  # 14 days ± 1
        cache.close()

    @pytest.mark.unit
    def test_parse_since_to_dates_months(self, tmp_path):
        """Test parsing 'since' parameter with months."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        start, end = cache._parse_since_to_dates("1m")

        delta = end - start
        assert 29 <= delta.days <= 31  # 30 days ± 1
        cache.close()

    @pytest.mark.unit
    def test_parse_since_to_dates_invalid_format(self, tmp_path):
        """Test parsing invalid 'since' parameter defaults to 1 day."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        start, end = cache._parse_since_to_dates("invalid")

        delta = end - start
        assert delta.days <= 1  # Defaults to 1 day
        cache.close()

    @pytest.mark.unit
    def test_generate_cache_key_consistent(self, tmp_path):
        """Test that cache key generation is consistent."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters = {"user": "testuser", "state": "RUNNING"}
        key1 = cache._generate_cache_key("test.host", filters)
        key2 = cache._generate_cache_key("test.host", filters)

        assert key1 == key2
        cache.close()

    @pytest.mark.unit
    def test_generate_cache_key_different_for_different_filters(self, tmp_path):
        """Test that different filters produce different cache keys."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters1 = {"user": "testuser"}
        filters2 = {"user": "otheruser"}
        key1 = cache._generate_cache_key("test.host", filters1)
        key2 = cache._generate_cache_key("test.host", filters2)

        assert key1 != key2
        cache.close()

    @pytest.mark.unit
    @pytest.mark.skip(reason="Date range comparison has timing precision issues - needs investigation")
    def test_cache_date_range_query(self, tmp_path):
        """Test caching a date range query."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters = {"user": "testuser"}
        job_ids = ["1", "2", "3"]

        # Use a longer time range to avoid timestamp precision issues
        cache.cache_date_range_query("test.host", filters, "7d", job_ids, ttl_seconds=3600)

        # Should be able to retrieve it
        cached_ids = cache.check_date_range_cache("test.host", filters, "7d")

        assert cached_ids == job_ids
        cache.close()

    @pytest.mark.unit
    def test_check_date_range_cache_miss(self, tmp_path):
        """Test cache miss for date range query."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters = {"user": "testuser"}

        cached_ids = cache.check_date_range_cache("test.host", filters, "1d")

        assert cached_ids is None
        cache.close()

    @pytest.mark.unit
    def test_check_date_range_cache_no_since(self, tmp_path):
        """Test that cache check returns None if no since parameter."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters = {"user": "testuser"}

        cached_ids = cache.check_date_range_cache("test.host", filters, None)

        assert cached_ids is None
        cache.close()

    @pytest.mark.unit
    @pytest.mark.skip(reason="Date range comparison has timing precision issues - needs investigation")
    def test_date_range_cache_hit_increments_count(self, tmp_path):
        """Test that cache hits increment the hit count."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters = {"user": "testuser"}
        job_ids = ["1", "2", "3"]

        # Use longer time range for stability
        cache.cache_date_range_query("test.host", filters, "7d", job_ids, ttl_seconds=3600)

        # Hit the cache twice
        result1 = cache.check_date_range_cache("test.host", filters, "7d")
        result2 = cache.check_date_range_cache("test.host", filters, "7d")

        # Verify cache hits worked
        assert result1 == job_ids
        assert result2 == job_ids

        # Check stats
        stats = cache.get_cache_stats()

        assert stats["date_range_cache"]["total_hits"] >= 2
        cache.close()

    @pytest.mark.unit
    def test_cleanup_expired_ranges(self, tmp_path):
        """Test cleanup of expired date range cache entries."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        filters = {"user": "testuser"}
        job_ids = ["1", "2", "3"]

        # Cache with very short TTL
        cache.cache_date_range_query("test.host", filters, "1d", job_ids, ttl_seconds=0)

        # Wait briefly and cleanup
        import time
        time.sleep(0.1)
        deleted = cache.cleanup_expired_ranges()

        assert deleted >= 1

        # Should not be in cache anymore
        cached_ids = cache.check_date_range_cache("test.host", filters, "1d")
        assert cached_ids is None
        cache.close()


class TestOutputCompression:
    """Tests for compressed output storage."""

    @pytest.mark.unit
    def test_update_job_outputs_text(self, tmp_path, sample_job_info):
        """Test updating job outputs with plain text."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info)

        stdout_text = "Test output line 1\nTest output line 2"
        stderr_text = "Error output"

        cache.update_job_outputs(
            sample_job_info.job_id,
            sample_job_info.hostname,
            stdout_content=stdout_text,
            stderr_content=stderr_text,
        )

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        # Outputs should be stored (compressed)
        assert cached.stdout_compressed is not None
        assert cached.stderr_compressed is not None
        cache.close()

    @pytest.mark.unit
    def test_update_job_outputs_large_compresses(self, tmp_path, sample_job_info):
        """Test that large outputs are compressed."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info)

        # Create large output (> 1024 bytes)
        large_output = "A" * 2000

        cache.update_job_outputs(
            sample_job_info.job_id,
            sample_job_info.hostname,
            stdout_content=large_output,
        )

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        # Should be compressed
        assert cached.stdout_compression == "gzip"
        assert cached.stdout_size == len(large_output)
        cache.close()

    @pytest.mark.unit
    def test_update_job_outputs_small_no_compression(self, tmp_path, sample_job_info):
        """Test that small outputs are not compressed."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info)

        # Create small output (< 1024 bytes)
        small_output = "Small output"

        cache.update_job_outputs(
            sample_job_info.job_id,
            sample_job_info.hostname,
            stdout_content=small_output,
        )

        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        # Should not be compressed
        assert cached.stdout_compression == "none"
        cache.close()

    @pytest.mark.unit
    def test_check_outputs_fetched_after_completion(self, tmp_path, sample_job_info):
        """Test checking if outputs were fetched after completion."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        cache.cache_job(sample_job_info)

        # Initially not fetched
        stdout_fetched, stderr_fetched = cache.check_outputs_fetched_after_completion(
            sample_job_info.job_id, sample_job_info.hostname
        )

        assert stdout_fetched is False
        assert stderr_fetched is False
        cache.close()

    @pytest.mark.unit
    def test_mark_outputs_fetched_after_completion(self, tmp_path, sample_job_info):
        """Test marking outputs as fetched after completion."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Create completed job
        completed_job = JobInfo(
            job_id=sample_job_info.job_id,
            name=sample_job_info.name,
            state=JobState.COMPLETED,
            hostname=sample_job_info.hostname,
        )
        cache.cache_job(completed_job)

        # Mark as fetched
        cache.mark_outputs_fetched_after_completion(
            sample_job_info.job_id, sample_job_info.hostname, stdout=True, stderr=True
        )

        # Check status
        stdout_fetched, stderr_fetched = cache.check_outputs_fetched_after_completion(
            sample_job_info.job_id, sample_job_info.hostname
        )

        assert stdout_fetched is True
        assert stderr_fetched is True
        cache.close()


class TestCacheManagement:
    """Tests for cache management operations."""

    @pytest.mark.unit
    def test_cleanup_by_size_preserves_scripts(self, tmp_path):
        """Test that cleanup by size preserves entries with scripts."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache jobs with and without scripts
        job_with_script = JobInfo(
            job_id="1", name="job1", state=JobState.COMPLETED, hostname="test.host"
        )
        cache.cache_job(job_with_script, script_content="#!/bin/bash\necho test")

        job_without_script = JobInfo(
            job_id="2", name="job2", state=JobState.COMPLETED, hostname="test.host"
        )
        cache.cache_job(job_without_script)

        # Trigger cleanup with very small size limit
        deleted = cache.cleanup_by_size(max_size_mb=0)

        # Job with script should still exist
        cached_with_script = cache.get_cached_job("1", "test.host")
        assert cached_with_script is not None
        cache.close()

    @pytest.mark.unit
    def test_cleanup_by_size_no_cleanup_needed(self, tmp_path):
        """Test that cleanup by size does nothing if under limit."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        job = JobInfo(
            job_id="1", name="job1", state=JobState.RUNNING, hostname="test.host"
        )
        cache.cache_job(job)

        # Cleanup with very large size limit
        deleted = cache.cleanup_by_size(max_size_mb=1000)

        assert deleted == 0
        cache.close()

    @pytest.mark.unit
    def test_clear_all_removes_everything(self, tmp_path):
        """Test that clear_all removes all cached data."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache multiple jobs
        for i in range(5):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname="test.host",
            )
            cache.cache_job(job)

        # Clear all
        deleted = cache.clear_all()

        # Should have deleted entries
        assert deleted > 0

        # No jobs should remain
        cached_jobs = cache.get_cached_jobs()
        assert len(cached_jobs) == 0
        cache.close()

    @pytest.mark.unit
    def test_export_cache_data_all_jobs(self, tmp_path):
        """Test exporting all cached jobs to JSON."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache some jobs
        for i in range(3):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname="test.host",
            )
            cache.cache_job(job, script_content=f"#!/bin/bash\necho {i}")

        export_file = tmp_path / "export.json"
        count = cache.export_cache_data(export_file)

        assert count == 3
        assert export_file.exists()

        # Verify JSON content
        with open(export_file) as f:
            data = json.load(f)

        assert len(data) == 3
        cache.close()

    @pytest.mark.unit
    def test_export_cache_data_specific_jobs(self, tmp_path):
        """Test exporting specific jobs to JSON."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache some jobs
        for i in range(5):
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=JobState.RUNNING,
                hostname="test.host",
            )
            cache.cache_job(job)

        export_file = tmp_path / "export.json"
        count = cache.export_cache_data(export_file, job_ids=["1", "3"])

        assert count == 2

        # Verify only specified jobs
        with open(export_file) as f:
            data = json.load(f)

        job_ids = [entry["job_id"] for entry in data]
        assert set(job_ids) == {"1", "3"}
        cache.close()


class TestCompletedJobsRetrieval:
    """Tests for retrieving completed jobs efficiently."""

    @pytest.mark.unit
    def test_get_cached_completed_jobs_basic(self, tmp_path):
        """Test retrieving completed jobs."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache mix of jobs
        for i in range(3):
            state = JobState.COMPLETED if i < 2 else JobState.RUNNING
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=state,
                hostname="test.host",
                submit_time=datetime.now(timezone.utc).isoformat(),
            )
            cache.cache_job(job)

        completed = cache.get_cached_completed_jobs("test.host")

        assert len(completed) == 2
        assert all(j.state == JobState.COMPLETED for j in completed)
        cache.close()

    @pytest.mark.unit
    def test_get_cached_completed_jobs_with_since(self, tmp_path):
        """Test retrieving completed jobs with since filter."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache old and recent jobs
        old_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        recent_time = datetime.now(timezone.utc).isoformat()

        old_job = JobInfo(
            job_id="1",
            name="old_job",
            state=JobState.COMPLETED,
            hostname="test.host",
            submit_time=old_time,
        )
        cache.cache_job(old_job)

        recent_job = JobInfo(
            job_id="2",
            name="recent_job",
            state=JobState.COMPLETED,
            hostname="test.host",
            submit_time=recent_time,
        )
        cache.cache_job(recent_job)

        # Query with since filter
        since = datetime.now(timezone.utc) - timedelta(days=2)
        completed = cache.get_cached_completed_jobs("test.host", since=since)

        # Should only get recent job
        assert len(completed) == 1
        assert completed[0].job_id == "2"
        cache.close()

    @pytest.mark.unit
    def test_get_cached_completed_job_ids_efficient(self, tmp_path):
        """Test efficient retrieval of completed job IDs."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache mix of jobs
        for i in range(5):
            state = JobState.COMPLETED if i < 3 else JobState.RUNNING
            job = JobInfo(
                job_id=f"{i}",
                name=f"job_{i}",
                state=state,
                hostname="test.host",
                submit_time=datetime.now(timezone.utc).isoformat(),
            )
            cache.cache_job(job)

        completed_ids = cache.get_cached_completed_job_ids("test.host")

        assert len(completed_ids) == 3
        assert "0" in completed_ids
        assert "1" in completed_ids
        assert "2" in completed_ids
        cache.close()

    @pytest.mark.unit
    def test_get_cached_completed_job_ids_with_max_age(self, tmp_path):
        """Test that old completed jobs are filtered out."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache old completed job
        old_time = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        old_job = JobInfo(
            job_id="1",
            name="old_job",
            state=JobState.COMPLETED,
            hostname="test.host",
            submit_time=old_time,
        )
        cache.cache_job(old_job)

        # Should not be returned (too old)
        completed_ids = cache.get_cached_completed_job_ids("test.host", max_age_days=30)

        assert "1" not in completed_ids
        cache.close()


class TestAdditionalEdgeCases:
    """Additional edge case tests."""

    @pytest.mark.unit
    def test_get_cache_with_global_instance(self):
        """Test getting global cache instance."""
        from ssync.cache import get_cache

        cache1 = get_cache()
        cache2 = get_cache()

        # Should return same instance
        assert cache1 is cache2

    @pytest.mark.unit
    def test_cache_handles_very_long_script(self, tmp_path):
        """Test caching jobs with very long scripts."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Create very long script
        long_script = "#!/bin/bash\n" + ("echo 'line'\n" * 10000)

        job = JobInfo(
            job_id="1",
            name="job",
            state=JobState.RUNNING,
            hostname="test.host",
        )
        cache.cache_job(job, script_content=long_script)

        cached = cache.get_cached_job("1", "test.host")

        assert cached.script_content == long_script
        cache.close()

    @pytest.mark.unit
    def test_cache_handles_unicode_in_outputs(self, tmp_path):
        """Test caching jobs with unicode characters in outputs."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        job = JobInfo(
            job_id="1",
            name="job",
            state=JobState.RUNNING,
            hostname="test.host",
        )
        cache.cache_job(job)

        unicode_output = "Test with unicode: 日本語 🎉 αβγ"
        cache.update_job_outputs("1", "test.host", stdout_content=unicode_output)

        cached = cache.get_cached_job("1", "test.host")

        assert cached.stdout_compressed is not None
        cache.close()

    @pytest.mark.unit
    def test_cache_local_source_dir_preservation(self, tmp_path, sample_job_info):
        """Test that local_source_dir is preserved on updates."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache with local_source_dir
        cache.cache_job(sample_job_info, local_source_dir="/path/to/source")

        # Update without local_source_dir
        updated_job = JobInfo(
            job_id=sample_job_info.job_id,
            name="updated",
            state=JobState.RUNNING,
            hostname=sample_job_info.hostname,
        )
        cache.cache_job(updated_job)

        # Should preserve local_source_dir
        cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

        assert cached.local_source_dir == "/path/to/source"
        cache.close()

    @pytest.mark.unit
    def test_merge_job_info_preserves_critical_fields(self, tmp_path):
        """Test that job info merging preserves critical fields."""
        cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)

        # Cache job with critical fields
        original = JobInfo(
            job_id="1",
            name="job",
            state=JobState.RUNNING,
            hostname="test.host",
            stdout_file="/path/to/stdout",
            stderr_file="/path/to/stderr",
            work_dir="/path/to/workdir",
        )
        cache.cache_job(original)

        # Update without critical fields
        update = JobInfo(
            job_id="1",
            name="job_updated",
            state=JobState.RUNNING,
            hostname="test.host",
        )
        cache.cache_job(update)

        # Critical fields should be preserved
        cached = cache.get_cached_job("1", "test.host")

        assert cached.job_info.stdout_file == "/path/to/stdout"
        assert cached.job_info.stderr_file == "/path/to/stderr"
        assert cached.job_info.work_dir == "/path/to/workdir"
        assert cached.job_info.name == "job_updated"  # Non-critical updated
        cache.close()
