import pytest

from ssync.cache import JobDataCache
from ssync.models.job import JobInfo, JobState


@pytest.mark.unit
def test_cache_stores_and_retrieves_run_manifest(tmp_path):
    cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
    manifest = {
        "manifest_version": 1,
        "recipe_path": "/repo/experiments/train.yaml",
        "vars": {"CONFIG": "experiments/train"},
        "sbatch": {"partition": "gpu"},
        "script_sha256": "abc123",
    }

    cache.store_run_manifest("123", "cluster.example.com", manifest)

    assert cache.get_run_manifest("123", "cluster.example.com") == manifest


@pytest.mark.unit
def test_cache_preserves_run_manifest_when_job_cache_updates(tmp_path):
    cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
    manifest = {
        "manifest_version": 1,
        "recipe_path": "/repo/experiments/train.yaml",
        "vars": {"CONFIG": "experiments/train"},
        "sbatch": {"partition": "gpu"},
        "script_sha256": "abc123",
    }
    cache.store_run_manifest("123", "cluster.example.com", manifest)

    cache.cache_job(
        JobInfo(
            job_id="123",
            hostname="cluster.example.com",
            name="train",
            state=JobState.RUNNING,
        )
    )

    assert cache.get_run_manifest("123", "cluster.example.com") == manifest
