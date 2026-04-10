"""Job launch and cancellation route registration."""

import asyncio
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from ...launch import LaunchManager
from ...models.job import JobState
from ...slurm.params import SlurmParams
from ...utils.async_helpers import create_task
from ...utils.logging import setup_logger
from ...utils.slurm_arrays import looks_like_array_submission
from ..models import LaunchJobRequest, LaunchJobResponse, LaunchStatusResponse
from ..security import InputSanitizer, PathValidator, ScriptValidator

logger = setup_logger(__name__)


def register_launch_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    verify_api_key_flexible_dependency,
    get_slurm_manager,
    cache_middleware,
    cache_job_state_transition,
    broadcast_job_state,
    launch_event_manager,
    executor,
) -> None:
    """Register launch and cancel routes."""

    @app.post("/api/jobs/launch", response_model=LaunchJobResponse)
    async def launch_job(
        request: LaunchJobRequest,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Launch a job by syncing source directory and submitting script."""
        try:
            request.script_content = ScriptValidator.validate_script(
                request.script_content
            )
            request.host = InputSanitizer.sanitize_hostname(request.host)

            manager = get_slurm_manager()
            try:
                manager.get_host_by_name(request.host)
            except ValueError:
                raise HTTPException(status_code=400, detail="Host not found")

            source_dir = None
            if request.source_dir:
                source_dir = PathValidator.validate_path(
                    request.source_dir, user_home=Path.home()
                )
                if not source_dir.exists():
                    raise HTTPException(
                        status_code=400, detail="Source directory not found"
                    )
                if not source_dir.is_dir():
                    raise HTTPException(
                        status_code=400, detail="Source path is not a directory"
                    )

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as tmp_script:
                tmp_script.write(request.script_content)
                script_path = Path(tmp_script.name)

            slurm_params = SlurmParams(
                job_name=request.job_name[:64] if request.job_name else None,
                time_min=request.time,
                cpus_per_task=min(request.cpus, 256) if request.cpus else None,
                mem_gb=min(request.mem, 1024) if request.mem else None,
                partition=request.partition,
                output=request.output,
                error=request.error,
                constraint=request.constraint,
                account=request.account,
                nodes=min(request.nodes, 100) if request.nodes else None,
                n_tasks_per_node=request.n_tasks_per_node,
                gpus_per_node=request.gpus_per_node,
                gres=request.gres,
            )

            launch_id = uuid.uuid4().hex[:12]
            launch_emitter = launch_event_manager.create_emitter(launch_id, request.host)
            launch_emitter.stage(
                "accepted",
                message="Launch accepted. Waiting for background execution.",
            )

            host = request.host
            script_content = request.script_content
            job_name = request.job_name
            python_env = request.python_env
            exclude = list(request.exclude)
            include = list(request.include)
            no_gitignore = request.no_gitignore
            sync_enabled = source_dir is not None
            abort_on_setup_failure = request.abort_on_setup_failure

            async def _run_launch_in_background() -> None:
                try:
                    launch_manager = LaunchManager(manager, executor=executor)
                    job = await launch_manager.launch_job(
                        script_path=script_path,
                        source_dir=source_dir,
                        host=host,
                        slurm_params=slurm_params,
                        python_env=python_env,
                        exclude=exclude,
                        include=include,
                        no_gitignore=no_gitignore,
                        sync_enabled=sync_enabled,
                        abort_on_setup_failure=abort_on_setup_failure,
                        launch_event_emitter=launch_emitter,
                    )

                    if job:
                        try:
                            local_dir_str = str(source_dir) if source_dir else None
                            await cache_middleware.cache_job_script(
                                job.job_id, host, script_content, local_dir_str
                            )
                        except Exception as e:
                            logger.warning(f"Failed to cache script: {e}")

                        try:
                            pending_job_info, previous_state = cache_job_state_transition(
                                job.job_id,
                                host,
                                JobState.PENDING,
                                job_name=job_name,
                                array_submission=looks_like_array_submission(
                                    script_content
                                ),
                            )
                            await broadcast_job_state(pending_job_info, previous_state)
                        except Exception as e:
                            logger.warning(
                                f"Failed to broadcast launched job {job.job_id}: {e}"
                            )

                        launch_emitter.result(
                            success=True,
                            message=f"Job launched successfully ({job.job_id})",
                            job_id=job.job_id,
                        )
                    else:
                        launch_emitter.result(
                            success=False,
                            message="Failed to launch job",
                        )
                except Exception as e:
                    logger.error(f"Background launch {launch_id} failed: {e}")
                    launch_emitter.result(success=False, message=str(e))
                finally:
                    try:
                        os.unlink(script_path)
                    except Exception:
                        pass

            create_task(_run_launch_in_background(), name=f"launch-{launch_id}")

            return LaunchJobResponse(
                success=True,
                launch_id=launch_id,
                message="Launch started" if sync_enabled else "Submitting job...",
                hostname=request.host,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error launching job: {e}")
            error_message = str(e)
            if "Failed to submit job" in error_message:
                if "Slurm Error:" in error_message:
                    raise HTTPException(status_code=500, detail=error_message)
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Job submission failed: "
                        f"{error_message}. Check cluster availability, Slurm configuration, and resource limits."
                    ),
                )
            if "Connection" in error_message or "SSH" in error_message:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Cannot connect to cluster: {error_message}. "
                        "Check network connectivity and SSH configuration."
                    ),
                )
            if "Permission" in error_message:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Access denied: {error_message}. "
                        "Verify your cluster credentials and account permissions."
                    ),
                )
            if "Invalid partition" in error_message:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid partition specified: {error_message}. Check available partitions on the cluster.",
                )
            if "Invalid account" in error_message:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid Slurm account: {error_message}. Verify your account is active and has access.",
                )
            if "not found" in error_message.lower():
                raise HTTPException(
                    status_code=404, detail=f"Resource not found: {error_message}"
                )
            if "Timeout" in error_message:
                raise HTTPException(
                    status_code=504,
                    detail=f"Operation timed out: {error_message}. The cluster may be overloaded or unresponsive.",
                )
            if "sbatch" in error_message.lower() and "not found" in error_message.lower():
                raise HTTPException(
                    status_code=503,
                    detail="Slurm commands not available on the cluster. Verify Slurm is installed and accessible.",
                )
            raise HTTPException(
                status_code=500, detail=f"Job launch failed: {error_message}"
            )

    @app.get("/api/launches/{launch_id}", response_model=LaunchStatusResponse)
    async def get_launch_status(
        launch_id: str,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Return current launch state and recent buffered events."""
        status = launch_event_manager.get_status(launch_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Launch not found")
        return LaunchStatusResponse(**status)

    @app.get("/api/launches/{launch_id}/events")
    async def stream_launch_events(
        launch_id: str,
        api_key: Optional[str] = Query(None, description="API key for EventSource"),
        _authenticated: bool = Depends(verify_api_key_flexible_dependency),
    ):
        """Stream launch events via Server-Sent Events."""
        try:
            snapshot, queue = await launch_event_manager.subscribe(launch_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Launch not found")

        async def send_event(payload: dict[str, Any]) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        async def generate():
            try:
                for event in snapshot["events"]:
                    yield await send_event(event)

                if snapshot["terminal"]:
                    return

                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue

                    yield await send_event(payload)
                    if payload["type"] == "launch_result":
                        break
            finally:
                launch_event_manager.unsubscribe(launch_id, queue)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(
        job_id: str,
        host: Optional[str] = Query(None, description="Specific host"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Cancel a running job."""
        try:
            job_id = InputSanitizer.sanitize_job_id(job_id)
            if host:
                host = InputSanitizer.sanitize_hostname(host)

            manager = get_slurm_manager()
            slurm_hosts = manager.slurm_hosts
            if host:
                slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]

            for slurm_host in slurm_hosts:
                try:
                    success = manager.cancel_job(slurm_host, job_id)
                    if success:
                        logger.info(
                            f"Cancelled job {job_id} on {slurm_host.host.hostname}"
                        )
                        try:
                            cancelled_job_info, previous_state = cache_job_state_transition(
                                job_id,
                                slurm_host.host.hostname,
                                JobState.CANCELLED,
                                reason="Cancelled via API",
                            )
                            await broadcast_job_state(
                                cancelled_job_info, previous_state
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to cache/broadcast cancelled job {job_id}: {e}"
                            )

                        try:
                            from ...watchers import get_watcher_engine

                            engine = get_watcher_engine()
                            await engine.stop_watchers_for_job(
                                job_id, slurm_host.host.hostname
                            )
                            logger.info(f"Stopped watchers for job {job_id}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to stop watchers for job {job_id}: {e}"
                            )

                        return {"message": "Job cancelled successfully"}
                    logger.warning(
                        f"Failed to cancel job {job_id} on {slurm_host.host.hostname}: scancel returned false"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to cancel job {job_id} on {slurm_host.host.hostname}: {e}"
                    )
                    continue

            raise HTTPException(
                status_code=500, detail="Failed to cancel job on any host"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            raise HTTPException(
                status_code=500, detail="Internal server error occurred"
            )
