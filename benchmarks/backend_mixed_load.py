"""Bounded local mixed-load probe for the backend request-isolation work.

The child process is a private FastAPI/uvicorn app.  It does not import the
production app, start lifecycle tasks, use SSH, or send notifications.  The
parent drives real cached output services while event-gated calls fill the
real bounded remote/background/transfer executors.

Run from the repository with::

    PYTHONPATH=$PWD/src \
      UV_PROJECT_ENVIRONMENT=$PWD/.venv \
      uv run --no-sync python benchmarks/backend_mixed_load.py

The result is synthetic evidence about this process and workload.  It is not
a production throughput benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import gc
import gzip
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx

PAYLOAD_BYTES = 64 * 1024**2
JOB_ID = "mixed-load-cache"
HOST = "synthetic"
LANES = ("remote", "background", "transfer")


def _rss_kib(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError, ValueError):
        return 0
    return 0


def _fixture() -> bytes:
    line = b"cached mixed-load line 0123456789 abcdefghijklmnopqrstuvwxyz\n"
    return (line * (PAYLOAD_BYTES // len(line) + 1))[:PAYLOAD_BYTES]


def _server(cache_dir: str, config_path: str, port: int) -> None:
    """Run the isolated benchmark-only server in a subprocess."""
    os.environ["SSYNC_CONFIG_PATH"] = config_path

    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse

    import ssync.cache as cache_module
    from ssync.cache import JobDataCache
    from ssync.models.job import JobInfo, JobState
    from ssync.utils import executors
    from ssync.utils.executors import (
        WorkQueueFull,
        run_background,
        run_remote,
        run_transfer,
    )
    from ssync.web.admission import RequestAdmissionMiddleware
    from ssync.web.cache.middleware import CacheMiddleware
    from ssync.web.services.jobs import (
        build_download_job_output_response,
        get_job_output_response,
    )

    cache = JobDataCache(Path(cache_dir), max_age_days=30)
    cache_module._cache_instance = cache
    payload = _fixture()
    payload_size = len(payload)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    compressed = gzip.compress(payload, compresslevel=1)
    cache.cache_job(
        JobInfo(
            job_id=JOB_ID,
            hostname=HOST,
            name="mixed-load-fixture",
            state=JobState.COMPLETED,
            stdout_file="/tmp/mixed-load.stdout",
            stderr_file="/tmp/mixed-load.stderr",
        )
    )
    cache.update_job_outputs_compressed(
        JOB_ID,
        HOST,
        stdout_data={
            "compressed": True,
            "data": base64.b64encode(compressed).decode("ascii"),
            "original_size": len(payload),
            "compression": "gzip",
        },
        mark_fetched_after_completion=True,
    )
    del payload, compressed
    gc.collect()

    gates = {lane: threading.Event() for lane in LANES}
    api = FastAPI()
    cache_middleware = CacheMiddleware()
    manager = SimpleNamespace(slurm_hosts=[])

    def snapshot():
        return {
            "executors": {
                "remote": executors.interactive_executor.stats(),
                "background": executors.background_executor.stats(),
                "transfer": executors.transfer_executor.stats(),
            },
            "admission": admission.active,
        }

    @api.exception_handler(WorkQueueFull)
    async def worker_queue_full(_request, _exc):
        return JSONResponse(
            {"detail": "Server busy. Please retry shortly."},
            status_code=503,
            headers={"Retry-After": "1"},
        )

    @api.get("/health")
    async def health():
        # /health bypasses admission, so this is also the unambiguous idle
        # snapshot: a /synthetic/stats request would count itself as active.
        return {"status": "healthy", "snapshot": snapshot()}

    @api.get("/synthetic/fixture")
    async def fixture_info():
        return {"bytes": payload_size, "sha256": payload_sha256}

    @api.get("/synthetic/rss")
    async def rss_info():
        return {"vmrss_kib": _rss_kib(os.getpid())}

    @api.get("/synthetic/stats")
    async def executor_stats():
        return snapshot()

    @api.post("/synthetic/release")
    async def release_gates():
        for gate in gates.values():
            gate.set()
        return {"released": True}

    async def run_gated(lane: str):
        runner = {
            "remote": run_remote,
            "background": run_background,
            "transfer": run_transfer,
        }[lane]

        def blocked():
            gates[lane].wait(30)
            return {"released": True}

        return await runner(blocked)

    @api.get("/synthetic/{lane}")
    async def synthetic_lane(lane: str):
        if lane not in LANES:
            raise HTTPException(status_code=404, detail="unknown synthetic lane")
        return await run_gated(lane)

    @api.get("/api/jobs/{job_id}/output")
    async def cached_output(
        job_id: str,
        host: str,
        output_type: str = "stdout",
        max_bytes: int = 512 * 1024,
        metadata_only: bool = False,
    ):
        return await get_job_output_response(
            job_id=job_id,
            host=host,
            lines=None,
            output_type=output_type,
            max_bytes=max_bytes,
            metadata_only=metadata_only,
            force_refresh=False,
            get_slurm_manager=lambda: manager,
            cache_middleware=cache_middleware,
            job_manager=None,
        )

    @api.get("/api/jobs/{job_id}/output/download")
    async def cached_download(
        job_id: str,
        host: str,
        output_type: str = "stdout",
        compressed: bool = True,
    ):
        return await build_download_job_output_response(
            job_id=job_id,
            host=host,
            output_type=output_type,
            compressed=compressed,
            get_slurm_manager=lambda: manager,
        )

    admission = RequestAdmissionMiddleware(api)
    config = uvicorn.Config(
        admission,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    finally:
        for gate in gates.values():
            gate.set()
        cache.close()


async def _wait_for_server(
    client: httpx.AsyncClient, process: subprocess.Popen
) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("benchmark server exited before readiness")
        try:
            if (await client.get("/health")).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.05)
    raise RuntimeError("benchmark server did not become ready")


async def _wait_until(client, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def _run_probe(process: subprocess.Popen, base_url: str) -> dict:
    limits = httpx.Limits(max_connections=128, max_keepalive_connections=128)
    timeout = httpx.Timeout(45.0)
    async with httpx.AsyncClient(
        base_url=base_url, limits=limits, timeout=timeout
    ) as client:
        await _wait_for_server(client, process)
        fixture = (await client.get("/synthetic/fixture")).json()
        baseline_rss = _rss_kib(process.pid)

        async def stats():
            return (await client.get("/health")).json()["snapshot"]

        initial = await stats()

        lane_tasks = {}
        for lane in LANES:
            capacity = initial["executors"][lane]["capacity"]
            lane_tasks[lane] = [
                asyncio.create_task(client.get(f"/synthetic/{lane}"))
                for _ in range(capacity + 3)
            ]

        async def saturated():
            snapshot_data = await stats()
            return all(
                snapshot_data["executors"][lane]["outstanding"]
                >= initial["executors"][lane]["capacity"]
                for lane in LANES
            )

        assert await _wait_until(client, saturated), "synthetic pools did not fill"
        overload = {}
        for lane, tasks in lane_tasks.items():
            overload[lane] = {
                "requests": len(tasks),
                "status_503": 0,
                "retry_after_1": 0,
            }
            for task in tasks:
                if task.done():
                    response = task.result()
                    if response.status_code == 503:
                        overload[lane]["status_503"] += 1
                        if response.headers.get("retry-after") == "1":
                            overload[lane]["retry_after_1"] += 1
            assert overload[lane]["status_503"] > 0, f"{lane} was not overloaded"
            assert overload[lane]["retry_after_1"] == overload[lane]["status_503"], (
                f"{lane} overload responses lacked Retry-After: 1"
            )

        health_samples = []
        metadata_success = 0
        preview_success = 0
        metadata_latencies = []
        preview_latencies = []
        rss_samples = [baseline_rss]

        async def health_probe():
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                started = time.perf_counter()
                response = await client.get("/health")
                health_samples.append(
                    {
                        "status": response.status_code,
                        "ms": (time.perf_counter() - started) * 1000,
                    }
                )
                await asyncio.sleep(0.02)

        async def cache_probe():
            nonlocal metadata_success, preview_success
            for _ in range(16):

                async def timed(request):
                    started = time.perf_counter()
                    response = await request
                    return response, (time.perf_counter() - started) * 1000

                metadata, preview = await asyncio.gather(
                    timed(
                        client.get(
                            f"/api/jobs/{JOB_ID}/output",
                            params={
                                "host": HOST,
                                "output_type": "stdout",
                                "metadata_only": "true",
                            },
                        )
                    ),
                    timed(
                        client.get(
                            f"/api/jobs/{JOB_ID}/output",
                            params={
                                "host": HOST,
                                "output_type": "stdout",
                                "max_bytes": 65536,
                            },
                        )
                    ),
                )
                metadata_response, metadata_ms = metadata
                preview_response, preview_ms = preview
                metadata_success += metadata_response.status_code == 200
                preview_success += preview_response.status_code == 200
                metadata_latencies.append(metadata_ms)
                preview_latencies.append(preview_ms)

        async def download_one(index):
            compressed_mode = index < 2
            digest = hashlib.sha256()
            decompressor = zlib.decompressobj(wbits=31) if compressed_mode else None
            received = 0
            async with client.stream(
                "GET",
                f"/api/jobs/{JOB_ID}/output/download",
                params={
                    "host": HOST,
                    "output_type": "stdout",
                    "compressed": str(compressed_mode).lower(),
                },
            ) as response:
                if response.status_code != 200:
                    return {
                        "mode": "gzip" if compressed_mode else "uncompressed",
                        "status": response.status_code,
                        "bytes": 0,
                        "sha256": "",
                    }

                def consume(chunk):
                    assert decompressor is not None
                    decoded = decompressor.decompress(chunk)
                    if decoded:
                        digest.update(decoded)
                    return len(decoded)

                def finish():
                    assert decompressor is not None
                    tail = decompressor.flush()
                    if tail:
                        digest.update(tail)
                    return len(tail)

                async for chunk in response.aiter_bytes(64 * 1024):
                    if compressed_mode:
                        # Keep client-side gzip work from delaying health
                        # probes on this asyncio loop. The response remains
                        # chunked.
                        received += await asyncio.to_thread(consume, chunk)
                    else:
                        digest.update(chunk)
                        received += len(chunk)

                if compressed_mode:
                    received += await asyncio.to_thread(finish)
            return {
                "mode": "gzip" if compressed_mode else "uncompressed",
                "status": 200,
                "bytes": received,
                "sha256": digest.hexdigest(),
            }

        async def rss_probe():
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                rss_samples.append(_rss_kib(process.pid))
                await asyncio.sleep(0.02)

        workload = await asyncio.gather(
            health_probe(),
            cache_probe(),
            rss_probe(),
            *(download_one(index) for index in range(4)),
        )
        downloads = [item for item in workload[3:] if isinstance(item, dict)]
        assert metadata_success == 16 and preview_success == 16
        assert len(downloads) == 4
        assert {item["mode"] for item in downloads} == {"gzip", "uncompressed"}
        assert all(
            item["status"] == 200
            and item["bytes"] == fixture["bytes"]
            and item["sha256"] == fixture["sha256"]
            for item in downloads
        )

        await client.post("/synthetic/release")
        all_lane_tasks = [task for tasks in lane_tasks.values() for task in tasks]
        await asyncio.gather(*all_lane_tasks)

        async def recovered():
            snapshot_data = await stats()
            return all(
                snapshot_data["executors"][lane]["outstanding"] == 0 for lane in LANES
            ) and all(value == 0 for value in snapshot_data["admission"].values())

        if not await _wait_until(client, recovered):
            raise AssertionError(f"capacity did not recover to zero: {await stats()}")
        final_stats = await stats()
        recovery = await asyncio.gather(
            *(client.get("/health") for _ in range(8)),
            *(
                client.get(
                    f"/api/jobs/{JOB_ID}/output",
                    params={
                        "host": HOST,
                        "output_type": "stdout",
                        "metadata_only": "true",
                    },
                )
                for _ in range(4)
            ),
        )

    health_latencies = [
        sample["ms"] for sample in health_samples if sample["status"] == 200
    ]
    sorted_latencies = sorted(health_latencies)

    def percentile(q):
        return sorted_latencies[
            min(len(sorted_latencies) - 1, int(len(sorted_latencies) * q))
        ]

    def latency_stats(samples):
        ordered = sorted(samples)
        return {
            "samples": len(ordered),
            "p50_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.50))], 3)
            if ordered
            else None,
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3)
            if ordered
            else None,
            "max_ms": round(max(ordered), 3) if ordered else None,
        }

    return {
        "source": "benchmarks/backend_mixed_load.py",
        "workload": {
            "payload_bytes": fixture["bytes"],
            "payload_sha256": fixture["sha256"],
            "concurrent_downloads": 4,
            "download_mode": "2 gzip + 2 uncompressed streams, incremental checksum",
            "gated_lanes": {
                lane: {
                    "workers": initial["executors"][lane]["workers"],
                    "queue": initial["executors"][lane]["capacity"]
                    - initial["executors"][lane]["workers"],
                    "capacity": initial["executors"][lane]["capacity"],
                }
                for lane in LANES
            },
        },
        "server_process": {
            "pid": process.pid,
            "baseline_vmrss_kib": baseline_rss,
            "peak_vmrss_kib": max(rss_samples),
        },
        "health": {
            "samples": len(health_samples),
            "successful": len(health_latencies),
            "p50_ms": round(percentile(0.50), 3) if sorted_latencies else None,
            "p95_ms": round(percentile(0.95), 3) if sorted_latencies else None,
            "max_ms": round(max(health_latencies), 3) if health_latencies else None,
            "all_status_200": all(sample["status"] == 200 for sample in health_samples),
            "measurement": "client-observed HTTP round trip; gzip decode/checksum offloaded",
        },
        "cache": {
            "metadata_success": metadata_success,
            "preview_success": preview_success,
            "metadata_latency": latency_stats(metadata_latencies),
            "preview_latency": latency_stats(preview_latencies),
            "downloads": downloads,
            "all_downloads_valid": all(
                item["status"] == 200
                and item["bytes"] == fixture["bytes"]
                and item["sha256"] == fixture["sha256"]
                for item in downloads
            ),
        },
        "overload": overload,
        "recovery": {
            "all_requests_200": all(
                response.status_code == 200 for response in recovery
            ),
            "final_stats": final_stats,
            "capacity_counters_zero": all(
                item["outstanding"] == 0 for item in final_stats["executors"].values()
            )
            and all(value == 0 for value in final_stats["admission"].values()),
        },
        "limits": [
            "Synthetic event-gated executor work and a local temporary SQLite cache.",
            "VmRSS is sampled from the private server PID; client RSS is excluded.",
            "This is not a production throughput or network performance benchmark.",
        ],
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--cache-dir")
    parser.add_argument("--config-path")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.server:
        _server(args.cache_dir, args.config_path, args.port)
        return

    process = None
    temp_dir = None
    try:
        temp_dir = tempfile.TemporaryDirectory(prefix="ssync-backend-mixed-")
        root = Path(temp_dir.name)
        config_path = root / "config.yaml"
        config_path.write_text("hosts: []\n", encoding="utf-8")
        port = _free_port()
        env = os.environ.copy()
        env["SSYNC_CONFIG_PATH"] = str(config_path)
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--server",
                "--cache-dir",
                str(root / "cache"),
                "--config-path",
                str(config_path),
                "--port",
                str(port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        result = asyncio.run(_run_probe(process, f"http://127.0.0.1:{port}"))
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        output = Path(__file__).parent / "results" / "backend-mixed-load.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if process is not None and process.poll() is None:
            try:
                # Release event-gated calls before termination so no child
                # worker remains blocked if the probe fails midway.
                import urllib.request

                urllib.request.urlopen(
                    urllib.request.Request(
                        f"http://127.0.0.1:{port}/synthetic/release", method="POST"
                    ),
                    timeout=1,
                ).close()
            except Exception:
                pass
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None and process.stderr is not None:
            stderr = process.stderr.read()
            if process.returncode not in (0, None) and stderr:
                print(stderr[-4000:], file=sys.stderr)
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
