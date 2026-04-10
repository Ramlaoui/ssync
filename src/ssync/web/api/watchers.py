"""Watcher API route registration and shared helpers."""

import json
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query

from ...cache import get_cache
from ...utils.logging import setup_logger
from ..security import InputSanitizer
from ..services.watchers import (
    attach_watchers_to_job_payload,
    cleanup_orphaned_watchers_payload,
    discover_array_tasks_payload,
    get_all_watchers_payload,
    get_job_watchers_payload,
    get_watcher_events_payload,
    get_watcher_stats_payload,
    trigger_watcher_manually_payload,
)
from ..services.watchers import (
    create_watcher as create_watcher_record,
)
from ..services.watchers import (
    delete_watcher as delete_watcher_record,
)
from ..services.watchers import (
    pause_watcher as pause_watcher_record,
)
from ..services.watchers import (
    resume_watcher as resume_watcher_record,
)
from ..services.watchers import (
    update_watcher as update_watcher_record,
)

logger = setup_logger(__name__)


def register_watcher_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    get_slurm_manager,
) -> None:
    """Register watcher-related routes."""

    @app.get("/api/jobs/{job_id}/watchers")
    async def get_job_watchers(
        job_id: str,
        host: Optional[str] = Query(None, description="Filter by hostname"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get watchers for a specific job."""
        try:
            job_id_sanitized = InputSanitizer.sanitize_job_id(job_id)
            host_sanitized = InputSanitizer.sanitize_hostname(host) if host else None
            return get_job_watchers_payload(
                cache=get_cache(),
                job_id=job_id_sanitized,
                host=host_sanitized,
            )
        except Exception as e:
            logger.error(f"Error getting watchers for job {job_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to get watchers")

    @app.get("/api/watchers")
    async def get_all_watchers(
        state: Optional[str] = Query(
            None, description="Filter by state (active, paused, completed, failed)"
        ),
        limit: int = Query(100, description="Maximum number of watchers to return"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get all watchers across all jobs."""
        try:
            return get_all_watchers_payload(
                cache=get_cache(),
                state=state,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting all watchers: {e}")
            raise HTTPException(status_code=500, detail="Failed to get watchers")

    @app.get("/api/watchers/events")
    async def get_watcher_events(
        job_id: Optional[str] = Query(None, description="Filter by job ID"),
        watcher_id: Optional[int] = Query(None, description="Filter by watcher ID"),
        limit: int = Query(50, description="Maximum number of events to return"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get recent watcher events."""
        try:
            if job_id:
                job_id = InputSanitizer.sanitize_job_id(job_id)
            return get_watcher_events_payload(
                cache=get_cache(),
                job_id=job_id,
                watcher_id=watcher_id,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting watcher events: {e}")
            raise HTTPException(status_code=500, detail="Failed to get watcher events")

    @app.get("/api/watchers/stats")
    async def get_watcher_stats(
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get watcher statistics."""
        try:
            return get_watcher_stats_payload(cache=get_cache())
        except Exception as e:
            logger.error(f"Error getting watcher stats: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to get watcher statistics"
            )

    @app.post("/api/watchers/cleanup")
    async def cleanup_orphaned_watchers(
        dry_run: bool = Query(
            default=False, description="Only list what would be cleaned"
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Clean up watchers for completed or non-existent jobs."""
        try:
            return await cleanup_orphaned_watchers_payload(
                cache=get_cache(),
                dry_run=dry_run,
            )
        except Exception as e:
            logger.error(f"Error cleaning up watchers: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to cleanup watchers: {e}"
            )

    @app.post("/api/watchers/{watcher_id}/pause")
    async def pause_watcher(
        watcher_id: int,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Pause a watcher."""
        try:
            return pause_watcher_record(cache=get_cache(), watcher_id=watcher_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Watcher not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error pausing watcher {watcher_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to pause watcher")

    @app.post("/api/watchers/{watcher_id}/trigger")
    async def trigger_watcher_manually(
        watcher_id: int,
        test_text: str = Body(None, description="Optional test text to match against"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Manually trigger a watcher for testing purposes."""
        try:
            return await trigger_watcher_manually_payload(
                cache=get_cache(),
                get_slurm_manager=get_slurm_manager,
                watcher_id=watcher_id,
                test_text=test_text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to manually trigger watcher {watcher_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to trigger watcher: {str(e)}"
            )

    @app.post("/api/watchers/{watcher_id}/resume")
    async def resume_watcher(
        watcher_id: int,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Resume a paused watcher."""
        try:
            return resume_watcher_record(cache=get_cache(), watcher_id=watcher_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Watcher not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resuming watcher {watcher_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to resume watcher")

    @app.post("/api/watchers/{watcher_id}/discover-array-tasks")
    async def discover_array_tasks(
        watcher_id: int,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Manually trigger array task discovery for a template watcher."""
        try:
            return await discover_array_tasks_payload(watcher_id=watcher_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Watcher not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error discovering array tasks for watcher {watcher_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to discover array tasks: {str(e)}"
            )

    @app.post("/api/watchers")
    async def create_watcher(
        watcher_config: Dict[str, Any] = Body(...),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Create a new watcher."""
        try:
            return create_watcher_record(
                cache=get_cache(),
                watcher_config=watcher_config,
                get_slurm_manager=get_slurm_manager,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating watcher: {e}")
            logger.error(f"Watcher config received: {json.dumps(watcher_config)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to create watcher: {str(e)}"
            )

    @app.put("/api/watchers/{watcher_id}")
    async def update_watcher(
        watcher_id: int,
        watcher_update: Dict[str, Any] = Body(...),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Update a watcher configuration."""
        try:
            return update_watcher_record(
                cache=get_cache(),
                watcher_id=watcher_id,
                watcher_update=watcher_update,
            )
        except ValueError:
            raise HTTPException(status_code=404, detail="Watcher not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating watcher {watcher_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to update watcher")

    @app.delete("/api/watchers/{watcher_id}")
    async def delete_watcher(
        watcher_id: int,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Delete a watcher."""
        try:
            return delete_watcher_record(cache=get_cache(), watcher_id=watcher_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Watcher not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting watcher {watcher_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete watcher")

    @app.post("/api/jobs/{job_id}/watchers")
    async def attach_watchers_to_job(
        job_id: str,
        host: str = Query(..., description="Hostname where job is running"),
        watchers: List[Dict[str, Any]] = Body(
            ..., description="List of watcher definitions"
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Attach watchers to an existing running job."""
        try:
            job_id = InputSanitizer.sanitize_job_id(job_id)
            host = InputSanitizer.sanitize_hostname(host)
            return await attach_watchers_to_job_payload(
                get_slurm_manager=get_slurm_manager,
                job_id=job_id,
                host=host,
                watchers=watchers,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except RuntimeError as exc:
            message = str(exc)
            status_code = 400
            if message.startswith("Error checking job status:"):
                status_code = 500
            raise HTTPException(status_code=status_code, detail=message)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to attach watchers to job {job_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
