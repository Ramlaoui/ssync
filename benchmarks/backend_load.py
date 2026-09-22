"""Local, reproducible backend responsiveness/memory checks; never uses SSH.

Run with uv run --no-sync python benchmarks/backend_load.py. The same script
can be run against an older checkout by pointing PYTHONPATH at its src folder.
Measurements describe these synthetic workloads, not production throughput.
"""

import asyncio
import gc
import gzip
import inspect
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

import ssync
from ssync.cache import JobDataCache
from ssync.catalog import LaunchCatalog
from ssync.models.job import JobInfo, JobState
from ssync.web.api import catalog
from ssync.web.services.jobs import decode_cached_output_for_response


def measured(call):
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()
    result = call()
    seconds = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {
        "seconds": round(seconds, 6),
        "python_peak_mib": round(peak / 1024**2, 3),
    }


async def catalog_latency():
    app = FastAPI()
    manager = SimpleNamespace(slurm_hosts=[])

    def discover(**kwargs):
        time.sleep(0.25)  # Deterministic slow disk traversal, no external I/O.
        return LaunchCatalog(repo_root=str(Path.cwd()), include_user_config=False)

    original = catalog.discover_launch_catalog
    catalog.discover_launch_catalog = discover
    catalog.register_catalog_routes(
        app, verify_api_key_dependency=lambda: True, get_slurm_manager=lambda: manager
    )

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    delays = []
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            for _ in range(5):
                scheduled = time.perf_counter() + 0.01
                heavy = asyncio.create_task(
                    client.get("/api/launch-catalog?force_refresh=true")
                )
                await asyncio.sleep(0.01)
                response = await client.get("/health")
                assert response.status_code == 200
                delays.append((time.perf_counter() - scheduled) * 1000)
                assert (await heavy).status_code == 200
    finally:
        catalog.discover_launch_catalog = original
    return {
        "samples": 5,
        "slow_catalog_ms": 250,
        "health_scheduling_delay_max_ms": round(max(delays), 3),
        "health_scheduling_delay_median_ms": round(sorted(delays)[2], 3),
    }


def main():
    source = gzip.compress(
        b"HEADER\n" + b"x" * (64 * 1024**2) + b"\nEND\n", compresslevel=1
    )
    preview, preview_stats = measured(
        lambda: decode_cached_output_for_response(
            compressed_data=source,
            compression="gzip",
            output_type="stdout",
            lines=None,
            max_bytes=512 * 1024,
            metadata_only=False,
        )
    )
    assert (
        preview[1]
        and preview[0].startswith("HEADER\n")
        and preview[0].endswith("END\n")
    )
    preview_stats.update(
        {
            "uncompressed_mib": 64,
            "response_limit_kib": 512,
            "returned_bytes": len(preview[0].encode()),
        }
    )

    with tempfile.TemporaryDirectory(prefix="ssync-load-") as directory:
        cache = JobDataCache(Path(directory))
        jobs = [
            JobInfo(
                job_id=str(i),
                hostname="synthetic",
                name=f"job-{i}",
                state=JobState.COMPLETED,
            )
            for i in range(32)
        ]
        cache.cache_jobs(jobs)
        with cache._get_connection() as conn:
            conn.execute(
                "UPDATE cached_jobs SET stdout_compressed = zeroblob(1048576), stdout_size = 1048576"
            )
            conn.commit()
        kwargs = (
            {"include_outputs": False}
            if "include_outputs" in inspect.signature(cache.get_cached_jobs).parameters
            else {}
        )
        rows, cache_stats = measured(lambda: cache.get_cached_jobs(**kwargs))
        assert len(rows) == 32
        cache_stats.update({"jobs": 32, "stored_log_mib": 32})
        cache.close()

    print(
        json.dumps(
            {
                "source": ssync.__file__,
                "catalog_contention": asyncio.run(catalog_latency()),
                "cached_log_preview": preview_stats,
                "status_cache_read": cache_stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
