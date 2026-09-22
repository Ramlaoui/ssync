"""Local filesystem browsing route registration."""

import heapq
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query

from ...utils.executors import WorkQueueFull, run_local

ALLOWED_ROOT_PATHS = ["/home", "/Users", "/opt", "/mnt", "/tmp", "/var/tmp"]
MAX_LOCAL_LIST_LIMIT = 1000


def _list_local_path(
    *, path: str, limit: int, show_hidden: bool, dirs_only: bool
) -> dict:
    """Validate and list a local directory without materializing all entries."""
    if limit < 1 or limit > MAX_LOCAL_LIST_LIMIT:
        raise HTTPException(
            status_code=422,
            detail=f"limit must be between 1 and {MAX_LOCAL_LIST_LIMIT}",
        )
    try:
        base = Path(path).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid path: {path}")

    if not any(str(base).startswith(allowed) for allowed in ALLOWED_ROOT_PATHS):
        user_home = Path.home()
        if not base.is_relative_to(user_home):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Access denied. Path must be under {ALLOWED_ROOT_PATHS} "
                    f"or {user_home}"
                ),
            )

    if not base.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not base.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    children = (
        child
        for child in base.iterdir()
        if (show_hidden or not child.name.startswith("."))
        and (not dirs_only or child.is_dir())
    )
    selected = heapq.nsmallest(
        limit,
        children,
        key=lambda candidate: (not candidate.is_dir(), candidate.name.lower()),
    )
    selected.sort(
        key=lambda candidate: (not candidate.is_dir(), candidate.name.lower())
    )
    entries = [
        {
            "name": child.name,
            "path": str(child),
            "is_dir": child.is_dir(),
        }
        for child in selected
    ]
    return {"path": str(base), "entries": entries}


def register_local_fs_routes(app: FastAPI, *, verify_api_key_dependency) -> None:
    """Register local filesystem browsing routes."""

    @app.get("/api/local/list")
    async def list_local_path(
        path: str = Query("/", description="Local filesystem path to list"),
        limit: int = Query(
            100,
            ge=1,
            le=MAX_LOCAL_LIST_LIMIT,
            description="Maximum number of entries to return",
        ),
        show_hidden: bool = Query(
            False, description="Include hidden files/directories"
        ),
        dirs_only: bool = Query(False, description="Show directories only"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """List entries in a local filesystem path to help the web UI pick a source_dir."""
        try:
            return await run_local(
                _list_local_path,
                path=path,
                limit=limit,
                show_hidden=show_hidden,
                dirs_only=dirs_only,
            )
        except WorkQueueFull:
            raise
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to read directory: {str(e)}"
            )
