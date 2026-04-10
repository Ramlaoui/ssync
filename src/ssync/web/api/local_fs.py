"""Local filesystem browsing route registration."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query

ALLOWED_ROOT_PATHS = ["/home", "/Users", "/opt", "/mnt", "/tmp", "/var/tmp"]


def register_local_fs_routes(app: FastAPI, *, verify_api_key_dependency) -> None:
    """Register local filesystem browsing routes."""

    @app.get("/api/local/list")
    async def list_local_path(
        path: str = Query("/", description="Local filesystem path to list"),
        limit: int = Query(100, description="Maximum number of entries to return"),
        show_hidden: bool = Query(
            False, description="Include hidden files/directories"
        ),
        dirs_only: bool = Query(False, description="Show directories only"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """List entries in a local filesystem path to help the web UI pick a source_dir."""
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
            raise HTTPException(
                status_code=400, detail=f"Path is not a directory: {path}"
            )

        entries = []
        try:
            for child in sorted(
                base.iterdir(), key=lambda candidate: (not candidate.is_dir(), candidate.name.lower())
            ):
                if not show_hidden and child.name.startswith("."):
                    continue
                if dirs_only and not child.is_dir():
                    continue

                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "is_dir": child.is_dir(),
                    }
                )

                if limit and len(entries) >= limit:
                    break

            return {"path": str(base), "entries": entries}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to read directory: {str(e)}"
            )
