"""Static launch catalog discovery for recipes and profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .models.cluster import SlurmHost
from .recipes import (
    RecipeError,
    _as_list,
    _load_yaml_mapping,
    _profile_path,
    _recipe_config_roots,
    _script_entries,
    find_repo_root,
)

_PROFILE_KINDS = {
    "hosts": "host_profile",
    "recipes": "recipe",
    "workflows": "workflow",
    "partitions": "partition",
    "envs": "env",
    "watchers": "watcher",
}
_PROFILE_COLLECTIONS = {
    "host_profile": "host_profiles",
    "recipe": "recipes",
    "workflow": "workflows",
    "partition": "partitions",
    "env": "envs",
    "watcher": "watchers",
}
_SBATCH_FIELDS = (
    "job_name",
    "cpus",
    "mem",
    "time",
    "partition",
    "output",
    "error",
    "nodes",
    "ntasks_per_node",
    "gpus_per_node",
    "gres",
    "constraint",
    "account",
    "qos",
    "dependency",
)
@dataclass
class LaunchCatalogWarning:
    """Non-fatal catalog discovery warning."""

    kind: str
    message: str
    path: str | None = None


@dataclass
class LaunchCatalogRoot:
    """Config root inspected during discovery."""

    source: str
    path: str
    exists: bool


@dataclass
class LaunchCatalogHost:
    """Safe configured host summary."""

    id: str
    label: str
    hostname: str
    source: str = "config"
    work_dir: str = "[CONFIGURED]"
    scratch_dir: str = "[CONFIGURED]"
    slurm_defaults: dict[str, Any] = field(default_factory=dict)
    requires_password: bool = False
    has_key_file: bool = False
    uses_ssh_config: bool = True


@dataclass
class LaunchCatalogProfile:
    """Safe recipe/profile summary for UI and automation clients."""

    id: str
    label: str
    kind: str
    source: str
    path: str
    active: bool = True
    shadowed_by: str | None = None
    host: str | None = None
    host_partition: str | None = None
    env: str | None = None
    workflow: str | None = None
    source_dir: str | None = None
    sbatch: dict[str, Any] = field(default_factory=dict)
    variable_names: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    references: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LaunchCatalog:
    """Catalog of launch surfaces discovered from repo and user config."""

    repo_root: str
    include_user_config: bool
    roots: list[LaunchCatalogRoot] = field(default_factory=list)
    hosts: list[LaunchCatalogHost] = field(default_factory=list)
    recipes: list[LaunchCatalogProfile] = field(default_factory=list)
    workflows: list[LaunchCatalogProfile] = field(default_factory=list)
    partitions: list[LaunchCatalogProfile] = field(default_factory=list)
    envs: list[LaunchCatalogProfile] = field(default_factory=list)
    watchers: list[LaunchCatalogProfile] = field(default_factory=list)
    host_profiles: list[LaunchCatalogProfile] = field(default_factory=list)
    warnings: list[LaunchCatalogWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def discover_launch_catalog(
    repo_root: str | Path | None = None,
    *,
    include_user_config: bool = True,
    slurm_hosts: Iterable[SlurmHost] | None = None,
) -> LaunchCatalog:
    """Discover static launch recipes and profiles.

    Discovery is intentionally tolerant: malformed files produce warnings and the
    rest of the catalog remains usable.
    """
    resolved_repo_root = find_repo_root(repo_root or Path.cwd())
    roots = _catalog_roots(resolved_repo_root, include_user_config)
    catalog = LaunchCatalog(
        repo_root=str(resolved_repo_root),
        include_user_config=include_user_config,
        roots=[
            LaunchCatalogRoot(source=source, path=str(root), exists=root.exists())
            for source, root in roots
        ],
        hosts=[_host_summary(host) for host in slurm_hosts or []],
    )
    active_paths: dict[tuple[str, str], str] = {}

    for source, root in roots:
        for directory_name, public_kind in _PROFILE_KINDS.items():
            _discover_profile_directory(
                catalog=catalog,
                repo_root=resolved_repo_root,
                root=root,
                source=source,
                directory_name=directory_name,
                public_kind=public_kind,
                active_paths=active_paths,
            )

    return catalog


def _catalog_roots(repo_root: Path, include_user_config: bool) -> list[tuple[str, Path]]:
    roots = _recipe_config_roots(repo_root)
    if not include_user_config:
        roots = roots[:1]
    return [
        ("repo" if index == 0 else "user", root)
        for index, root in enumerate(roots)
    ]


def _host_summary(slurm_host: SlurmHost) -> LaunchCatalogHost:
    defaults = slurm_host.slurm_defaults.__dict__ if slurm_host.slurm_defaults else {}
    hostname = slurm_host.host.hostname
    return LaunchCatalogHost(
        id=hostname,
        label=hostname,
        hostname=hostname,
        slurm_defaults={
            key: value for key, value in defaults.items() if value is not None
        },
        requires_password=bool(slurm_host.host.password),
        has_key_file=bool(slurm_host.host.key_file),
        uses_ssh_config=bool(slurm_host.host.use_ssh_config),
    )


def _discover_profile_directory(
    *,
    catalog: LaunchCatalog,
    repo_root: Path,
    root: Path,
    source: str,
    directory_name: str,
    public_kind: str,
    active_paths: dict[tuple[str, str], str],
) -> None:
    directory = root / directory_name
    if not directory.exists():
        return

    for path in _iter_yaml_files(directory):
        profile_id = path.relative_to(directory).with_suffix("").as_posix()
        _append_profile(
            catalog=catalog,
            repo_root=repo_root,
            path=path,
            profile_id=profile_id,
            public_kind=public_kind,
            source=source,
            active_paths=active_paths,
        )


def _iter_yaml_files(directory: Path) -> list[Path]:
    return sorted(
        (
            path
            for pattern in ("*.yaml", "*.yml")
            for path in directory.rglob(pattern)
            if path.is_file()
        ),
        key=lambda path: path.as_posix(),
    )

def _append_profile(
    *,
    catalog: LaunchCatalog,
    repo_root: Path,
    path: Path,
    profile_id: str,
    public_kind: str,
    source: str,
    active_paths: dict[tuple[str, str], str],
) -> None:
    data = _load_mapping_or_warn(catalog, public_kind, path)
    if data is None:
        return

    key = (public_kind, profile_id)
    shadowed_by = active_paths.get(key)
    if shadowed_by is None:
        active = True
        active_paths[key] = str(path)
    else:
        active = False

    profile = _profile_summary(
        catalog=catalog,
        repo_root=repo_root,
        path=path,
        profile_id=profile_id,
        public_kind=public_kind,
        source=source,
        data=data,
        active=active,
        shadowed_by=shadowed_by,
    )
    getattr(catalog, _PROFILE_COLLECTIONS[public_kind]).append(profile)


def _load_mapping_or_warn(
    catalog: LaunchCatalog, public_kind: str, path: Path
) -> dict[str, Any] | None:
    try:
        return _load_yaml_mapping(path)
    except RecipeError as exc:
        catalog.warnings.append(
            LaunchCatalogWarning(
                kind=public_kind,
                path=str(path),
                message=_catalog_error_message(exc),
            )
        )
        return None


def _profile_summary(
    *,
    catalog: LaunchCatalog,
    repo_root: Path,
    path: Path,
    profile_id: str,
    public_kind: str,
    source: str,
    data: dict[str, Any],
    active: bool,
    shadowed_by: str | None,
) -> LaunchCatalogProfile:
    references = _references_for_profile(data, public_kind)
    _warn_for_missing_references(catalog, repo_root, path, public_kind, references)
    return LaunchCatalogProfile(
        id=profile_id,
        label=str(data.get("name") or data.get("job_name") or profile_id),
        kind=public_kind,
        source=source,
        path=str(path),
        active=active,
        shadowed_by=shadowed_by,
        host=_string_or_none(data.get("host") or data.get("hostname")),
        host_partition=_string_or_none(data.get("host_partition")),
        env=_string_or_none(data.get("env")),
        workflow=_string_or_none(data.get("extends") or data.get("workflow")),
        source_dir=_string_or_none(data.get("source_dir")),
        sbatch=_safe_sbatch(data),
        variable_names=_variable_names(data),
        scripts=_script_refs(catalog, path, public_kind, data),
        references=references,
        metadata=_metadata_for_profile(data, public_kind),
    )


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _catalog_error_message(exc: Exception) -> str:
    message = str(exc)
    if "Invalid YAML" in message:
        return "Invalid YAML; profile skipped"
    return message


def _safe_sbatch(data: dict[str, Any]) -> dict[str, Any]:
    sbatch = data.get("sbatch")
    safe: dict[str, Any] = {}
    if isinstance(sbatch, dict):
        for field_name in _SBATCH_FIELDS:
            if field_name in sbatch and sbatch[field_name] is not None:
                safe[field_name] = sbatch[field_name]

    if "job_name" in data and data["job_name"] is not None:
        safe.setdefault("job_name", data["job_name"])
    for field_name in _SBATCH_FIELDS:
        if field_name in data and data[field_name] is not None:
            safe.setdefault(field_name, data[field_name])
    return safe


def _variable_names(data: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    _collect_var_names(data.get("vars"), names)
    for section_name in ("prepare", "env", "run"):
        section = data.get(section_name)
        if isinstance(section, dict):
            _collect_var_names(section.get("vars"), names)
            for entry in _as_list(section.get("scripts")):
                if isinstance(entry, dict):
                    _collect_var_names(entry.get("vars"), names)
    return sorted(names)


def _collect_var_names(value: Any, names: set[str]) -> None:
    if isinstance(value, dict):
        names.update(str(key) for key in value)


def _script_refs(
    catalog: LaunchCatalog,
    path: Path,
    public_kind: str,
    data: dict[str, Any],
) -> list[str]:
    scripts: list[str] = []
    for section_name in ("prepare", "env", "run"):
        try:
            entries = _script_entries(data.get(section_name), section_name)
        except RecipeError as exc:
            catalog.warnings.append(
                LaunchCatalogWarning(
                    kind=public_kind,
                    path=str(path),
                    message=str(exc),
                )
            )
            continue
        scripts.extend(entry["script"] for entry in entries)

    if "scripts" in data:
        try:
            entries = _script_entries(data, public_kind)
        except RecipeError as exc:
            catalog.warnings.append(
                LaunchCatalogWarning(
                    kind=public_kind,
                    path=str(path),
                    message=str(exc),
                )
            )
        else:
            scripts.extend(entry["script"] for entry in entries)

    return _unique_sorted(scripts)


def _references_for_profile(data: dict[str, Any], public_kind: str) -> dict[str, Any]:
    references: dict[str, Any] = {}
    workflow = _string_or_none(data.get("extends") or data.get("workflow"))
    if workflow:
        references["workflow"] = workflow
    host_partition = _string_or_none(data.get("host_partition"))
    if host_partition:
        references["host_partition"] = host_partition
    env = _string_or_none(data.get("env"))
    if env:
        references["env"] = env

    watcher_refs = [
        item for item in _as_list(data.get("watchers")) if isinstance(item, str)
    ]
    if watcher_refs:
        references["watchers"] = watcher_refs

    if public_kind == "partition":
        host = _string_or_none(data.get("host"))
        if host:
            references["host"] = host

    return references


def _warn_for_missing_references(
    catalog: LaunchCatalog,
    repo_root: Path,
    path: Path,
    public_kind: str,
    references: dict[str, Any],
) -> None:
    _warn_if_profile_missing(
        catalog, repo_root, path, public_kind, "workflows", references.get("workflow")
    )
    _warn_if_profile_missing(
        catalog,
        repo_root,
        path,
        public_kind,
        "partitions",
        references.get("host_partition"),
    )
    _warn_if_profile_missing(
        catalog, repo_root, path, public_kind, "envs", references.get("env")
    )
    for watcher_ref in references.get("watchers", []):
        _warn_if_profile_missing(
            catalog, repo_root, path, public_kind, "watchers", watcher_ref
        )


def _warn_if_profile_missing(
    catalog: LaunchCatalog,
    repo_root: Path,
    source_path: Path,
    public_kind: str,
    profile_kind: str,
    ref: Any,
) -> None:
    if not isinstance(ref, str) or not ref:
        return
    try:
        path = _profile_path(repo_root, profile_kind, ref)
    except RecipeError as exc:
        catalog.warnings.append(
            LaunchCatalogWarning(
                kind=public_kind,
                path=str(source_path),
                message=str(exc),
            )
        )
        return
    if not path.exists():
        catalog.warnings.append(
            LaunchCatalogWarning(
                kind=public_kind,
                path=str(source_path),
                message=f"Referenced {profile_kind} profile not found: {ref}",
            )
        )


def _metadata_for_profile(data: dict[str, Any], public_kind: str) -> dict[str, Any]:
    if public_kind == "watcher":
        return {
            "has_pattern": bool(data.get("pattern")),
            "trigger_on_job_end": bool(data.get("trigger_on_job_end")),
            "action_count": len(_as_list(data.get("actions"))),
        }
    if "watchers" in data:
        return {"watcher_count": len(_as_list(data.get("watchers")))}
    return {}


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))

