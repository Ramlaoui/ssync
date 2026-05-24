"""Launch catalog route registration."""

from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from ...catalog import LaunchCatalogWarning, discover_launch_catalog
from ..models import LaunchCatalogResponse
from ..security import PathValidator, sanitize_error_message
from .local_fs import ALLOWED_ROOT_PATHS


def _validate_catalog_repo_root(path: str | None) -> Path | None:
    if path is None:
        return None

    resolved = PathValidator.validate_path(path, user_home=Path.home())
    user_home = Path.home().resolve()
    if not any(str(resolved).startswith(root) for root in ALLOWED_ROOT_PATHS):
        try:
            resolved.relative_to(user_home)
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Access denied. Path must be under {ALLOWED_ROOT_PATHS} "
                    f"or {user_home}"
                ),
            )

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")
    return resolved


def register_catalog_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    get_slurm_manager,
) -> None:
    """Register launch catalog routes."""

    @app.get("/api/launch-catalog", response_model=LaunchCatalogResponse)
    async def get_launch_catalog(
        repo_root: Optional[str] = Query(
            None,
            description="Repository root or child path to inspect. Defaults to server cwd.",
        ),
        include_user_config: bool = Query(
            True,
            description="Include user-level ssync profiles after repo-local profiles.",
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Return static launch recipes and profiles without querying Slurm."""
        warnings: list[LaunchCatalogWarning] = []
        slurm_hosts = []
        try:
            slurm_hosts = list(get_slurm_manager().slurm_hosts)
        except Exception as exc:
            warnings.append(
                LaunchCatalogWarning(
                    kind="host",
                    message=f"Configured hosts unavailable: {sanitize_error_message(exc)}",
                )
            )

        try:
            catalog = discover_launch_catalog(
                repo_root=_validate_catalog_repo_root(repo_root),
                include_user_config=include_user_config,
                slurm_hosts=slurm_hosts,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to discover launch catalog: {sanitize_error_message(exc)}",
            )

        catalog.warnings = warnings + catalog.warnings
        return LaunchCatalogResponse(**catalog.to_dict())
