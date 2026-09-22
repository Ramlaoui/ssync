"""Launch catalog route registration."""

import copy
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from ...catalog import LaunchCatalogWarning, discover_launch_catalog
from ...models.cluster import SlurmHost
from ...recipes import find_repo_root
from ...utils.executors import WorkQueueFull, run_local
from ..models import LaunchCatalogResponse
from ..security import PathValidator, sanitize_error_message
from .local_fs import ALLOWED_ROOT_PATHS

DEFAULT_CATALOG_CACHE_TTL_SECONDS = 5.0
MAX_CATALOG_CACHE_ENTRIES = 32


@dataclass
class _CatalogCacheEntry:
    payload: dict
    created_at: float


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


def _default_cache_ttl_seconds() -> float:
    raw_value = os.getenv(
        "SSYNC_LAUNCH_CATALOG_TTL_SECONDS",
        str(DEFAULT_CATALOG_CACHE_TTL_SECONDS),
    )
    try:
        return max(float(raw_value), 0.0)
    except ValueError:
        return DEFAULT_CATALOG_CACHE_TTL_SECONDS


def _host_cache_fingerprint(slurm_hosts: list[SlurmHost]) -> tuple:
    fingerprint = []
    for slurm_host in slurm_hosts:
        defaults = (
            tuple(sorted(slurm_host.slurm_defaults.__dict__.items()))
            if slurm_host.slurm_defaults
            else ()
        )
        fingerprint.append(
            (
                slurm_host.host.hostname,
                bool(slurm_host.host.password),
                bool(slurm_host.host.key_file),
                bool(slurm_host.host.use_ssh_config),
                defaults,
            )
        )
    return tuple(sorted(fingerprint))


def _prepare_catalog_context(
    *, repo_root: str | None, get_slurm_manager, include_user_config: bool
):
    """Resolve local catalog inputs in a worker thread.

    Manager construction can reload the local config and repository discovery
    performs filesystem reads. Keeping both in the local pool prevents either
    operation from blocking the event loop or waiting behind SSH work.
    """
    warnings: list[LaunchCatalogWarning] = []
    slurm_hosts = []
    host_lookup_ok = True
    try:
        slurm_hosts = list(get_slurm_manager().slurm_hosts)
    except WorkQueueFull:
        raise
    except Exception as exc:
        host_lookup_ok = False
        warnings.append(
            LaunchCatalogWarning(
                kind="host",
                message=f"Configured hosts unavailable: {sanitize_error_message(exc)}",
            )
        )

    requested_repo_root = _validate_catalog_repo_root(repo_root)
    resolved_repo_root = find_repo_root(requested_repo_root or Path.cwd())
    return (
        resolved_repo_root,
        slurm_hosts,
        host_lookup_ok,
        warnings,
        include_user_config,
    )


def register_catalog_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    get_slurm_manager,
    cache_ttl_seconds: float | None = None,
) -> None:
    """Register launch catalog routes."""
    catalog_cache: OrderedDict[tuple, _CatalogCacheEntry] = OrderedDict()
    catalog_cache_lock = Lock()
    cache_ttl = (
        _default_cache_ttl_seconds()
        if cache_ttl_seconds is None
        else max(float(cache_ttl_seconds), 0.0)
    )

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
        force_refresh: bool = Query(
            False,
            description="Bypass the short in-process launch catalog cache.",
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Return static launch recipes and profiles without querying Slurm."""
        try:
            (
                resolved_repo_root,
                slurm_hosts,
                host_lookup_ok,
                warnings,
                include_user_config,
            ) = await run_local(
                _prepare_catalog_context,
                repo_root=repo_root,
                get_slurm_manager=get_slurm_manager,
                include_user_config=include_user_config,
            )
            cache_key = (
                str(resolved_repo_root),
                include_user_config,
                _host_cache_fingerprint(slurm_hosts),
            )
            now = monotonic()
            if cache_ttl > 0 and not force_refresh and host_lookup_ok:
                with catalog_cache_lock:
                    for stale_key, stale_entry in list(catalog_cache.items()):
                        if now - stale_entry.created_at > cache_ttl:
                            del catalog_cache[stale_key]
                    entry = catalog_cache.get(cache_key)
                    if entry and now - entry.created_at <= cache_ttl:
                        catalog_cache.move_to_end(cache_key)
                        payload = copy.deepcopy(entry.payload)
                        payload["cached"] = True
                        payload["cache_age_seconds"] = now - entry.created_at
                        return LaunchCatalogResponse(**payload)

            catalog = await run_local(
                discover_launch_catalog,
                repo_root=resolved_repo_root,
                include_user_config=include_user_config,
                slurm_hosts=slurm_hosts,
            )
        except WorkQueueFull:
            raise
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to discover launch catalog: {sanitize_error_message(exc)}",
            )

        catalog.warnings = warnings + catalog.warnings
        payload = catalog.to_dict()
        payload["cached"] = False
        payload["cache_age_seconds"] = 0.0
        payload["cache_ttl_seconds"] = cache_ttl
        if cache_ttl > 0 and host_lookup_ok:
            with catalog_cache_lock:
                now = monotonic()
                for stale_key, stale_entry in list(catalog_cache.items()):
                    if now - stale_entry.created_at > cache_ttl:
                        del catalog_cache[stale_key]
                if cache_key in catalog_cache:
                    del catalog_cache[cache_key]
                while len(catalog_cache) >= MAX_CATALOG_CACHE_ENTRIES:
                    catalog_cache.popitem(last=False)
                catalog_cache[cache_key] = _CatalogCacheEntry(
                    payload=copy.deepcopy(payload),
                    created_at=now,
                )
        return LaunchCatalogResponse(**payload)
