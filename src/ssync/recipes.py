"""Repo-local launch recipe loading and rendering."""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from shlex import quote
from typing import Any

import yaml

from .utils.config import get_user_config_dir


class RecipeError(Exception):
    """Launch recipe loading or rendering error."""


@dataclass(frozen=True)
class RenderedRecipe:
    """Resolved recipe ready for launch."""

    recipe_path: Path
    repo_root: Path
    script_content: str
    source_dir: Path
    host: str | None = None
    job_name: str | None = None
    cpus: int | None = None
    mem: int | None = None
    time: int | None = None
    partition: str | None = None
    output: str | None = None
    error: str | None = None
    nodes: int | None = None
    ntasks_per_node: int | None = None
    gpus_per_node: int | None = None
    gres: str | None = None
    constraint: str | None = None
    account: str | None = None
    python_env: str | None = None
    vars: dict[str, Any] = field(default_factory=dict)
    fragments: list[Path] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


_ALLOWED_TOP_LEVEL_KEYS = {
    "account",
    "constraint",
    "env",
    "error",
    "extends",
    "gpus_per_node",
    "gres",
    "host",
    "host_partition",
    "job_name",
    "mem",
    "nodes",
    "ntasks_per_node",
    "output",
    "partition",
    "prepare",
    "python_env",
    "run",
    "sbatch",
    "source_dir",
    "time",
    "vars",
    "watchers",
    "workflow",
}

_SBATCH_INT_FIELDS = {
    "cpus",
    "mem",
    "time",
    "nodes",
    "ntasks_per_node",
    "gpus_per_node",
}


def find_repo_root(start: str | Path) -> Path:
    """Find the nearest repository root for a recipe or working directory."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        if (directory / ".ssync").is_dir() or (directory / ".git").exists():
            return directory

    return current


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RecipeError(f"Recipe not found: {path}")

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise RecipeError(f"Invalid YAML in recipe {path}: {exc}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RecipeError("Launch recipe must be a YAML mapping")

    return data


def _recipe_config_roots(repo_root: Path) -> list[Path]:
    return [repo_root / ".ssync", get_user_config_dir()]


def _is_bare_recipe_ref(value: str | Path) -> bool:
    raw_value = str(value)
    path = Path(value).expanduser()
    return not (
        path.is_absolute()
        or path.exists()
        or path.suffix in {".yaml", ".yml"}
        or "/" in raw_value
    )


def _resolve_named_recipe_path(value: str | Path) -> Path:
    raw_value = str(value)
    path = Path(value).expanduser()
    if not _is_bare_recipe_ref(value):
        return path.resolve()

    repo_root = find_repo_root(Path.cwd())
    for root in _recipe_config_roots(repo_root):
        for suffix in (".yaml", ".yml"):
            candidate = root / "recipes" / f"{raw_value}{suffix}"
            if candidate.exists():
                return candidate.resolve()

    return path.resolve()


def _profile_path(repo_root: Path, kind: str, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise RecipeError(f"{kind} profile reference must be a non-empty string")

    path = Path(value).expanduser()
    if path.is_absolute() or path.suffix in {".yaml", ".yml"} or "/" in value:
        return (repo_root / path).resolve() if not path.is_absolute() else path

    first_candidate: Path | None = None
    for root in _recipe_config_roots(repo_root):
        for suffix in (".yaml", ".yml"):
            candidate = root / kind / f"{value}{suffix}"
            first_candidate = first_candidate or candidate
            if candidate.exists():
                return candidate

    return first_candidate or repo_root / ".ssync" / kind / f"{value}.yaml"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _merge_section(base: Any, overlay: Any, *, append_scripts: bool) -> Any:
    if base is None:
        return overlay
    if overlay is None:
        return base

    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, overlay_value in overlay.items():
            if append_scripts and key == "scripts":
                merged[key] = _as_list(merged.get(key)) + _as_list(overlay_value)
            else:
                merged[key] = _merge_section(
                    merged.get(key),
                    overlay_value,
                    append_scripts=append_scripts,
                )
        return merged

    if append_scripts and isinstance(base, list) and isinstance(overlay, list):
        return base + overlay

    return overlay


def _merge_recipe_data(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, overlay_value in overlay.items():
        if key in {"extends", "workflow"}:
            continue
        if key in {"env", "prepare", "watchers"}:
            merged[key] = _merge_section(
                merged.get(key), overlay_value, append_scripts=True
            )
        elif key in {"vars", "sbatch"}:
            merged[key] = _merge_section(
                merged.get(key), overlay_value, append_scripts=False
            )
        else:
            merged[key] = overlay_value
    return merged


def _load_profile(repo_root: Path, kind: str, value: Any) -> dict[str, Any]:
    profile_path = _profile_path(repo_root, kind, value)
    return _load_yaml_mapping(profile_path)


def _resolve_workflow_data(
    repo_root: Path, data: dict[str, Any], seen: set[Path] | None = None
) -> dict[str, Any]:
    profile_ref = data.get("extends") or data.get("workflow")
    if not profile_ref:
        return {}

    profile_path = _profile_path(repo_root, "workflows", profile_ref)
    seen = seen or set()
    if profile_path in seen:
        raise RecipeError(f"Workflow profile cycle detected at {profile_path}")
    seen.add(profile_path)

    profile_data = _load_yaml_mapping(profile_path)
    base_data = _resolve_workflow_data(repo_root, profile_data, seen)
    return _merge_recipe_data(base_data, profile_data)


def _load_host_partition_profile_data(
    repo_root: Path, host_partition: Any
) -> dict[str, Any]:
    if not host_partition:
        return {}

    partition_data = _load_profile(repo_root, "partitions", host_partition)
    host_ref = partition_data.get("host")
    host_data: dict[str, Any] = {}
    if isinstance(host_ref, str):
        host_path = _profile_path(repo_root, "hosts", host_ref)
        if host_path.exists():
            host_data = _load_yaml_mapping(host_path)

    return _merge_recipe_data(host_data, partition_data)


def _load_env_profile_data(repo_root: Path, env: Any) -> dict[str, Any]:
    if not isinstance(env, str):
        return {}
    return {"env": _load_profile(repo_root, "envs", env)}


def _load_watcher_policy(repo_root: Path, value: str) -> dict[str, Any]:
    policy = _load_profile(repo_root, "watchers", value)
    policy.setdefault("name", Path(value).stem)
    policy["policy_ref"] = value
    return policy


def _resolve_recipe_data(repo_root: Path, data: dict[str, Any]) -> dict[str, Any]:
    workflow_data = _resolve_workflow_data(repo_root, data)
    selector_data = _merge_recipe_data(workflow_data, data)
    host_partition_data = _load_host_partition_profile_data(
        repo_root, selector_data.get("host_partition")
    )
    env_data = _load_env_profile_data(repo_root, selector_data.get("env"))

    recipe_overlay = {
        key: value
        for key, value in data.items()
        if key not in {"extends", "workflow"}
        and not (key == "env" and isinstance(value, str))
    }

    resolved = _merge_recipe_data(workflow_data, host_partition_data)
    resolved = _merge_recipe_data(resolved, env_data)
    return _merge_recipe_data(resolved, recipe_overlay)


def _resolve_path(
    repo_root: Path, recipe_dir: Path, value: Any, field_name: str
) -> Path:
    if not isinstance(value, str) or not value:
        raise RecipeError(f"Recipe field '{field_name}' must be a non-empty path")

    path = Path(value).expanduser()
    if path.is_absolute():
        return path

    recipe_relative = (recipe_dir / path).resolve()
    if recipe_relative.exists():
        return recipe_relative

    return (repo_root / path).resolve()


def _resolve_repo_path(repo_root: Path, value: Any, field_name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RecipeError(f"Recipe field '{field_name}' must be a non-empty path")

    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _script_entries(value: Any, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []

    if isinstance(value, dict):
        scripts = value.get("scripts")
        if scripts is None and "script" in value:
            scripts = [value]
    else:
        scripts = value

    if scripts is None:
        return []
    if isinstance(scripts, (str, dict)):
        scripts = [scripts]
    if not isinstance(scripts, list):
        raise RecipeError(f"Recipe field '{field_name}' must be a script or list")

    entries = []
    for item in scripts:
        if isinstance(item, str):
            entries.append({"script": item})
        elif isinstance(item, dict) and isinstance(item.get("script"), str):
            entries.append(item)
        else:
            raise RecipeError(
                f"Recipe field '{field_name}' contains an invalid script entry"
            )
    return entries


def _watcher_entries(
    repo_root: Path,
    value: Any,
    *,
    add_watchers: list[str] | None = None,
    remove_watchers: list[str] | None = None,
) -> list[dict[str, Any]]:
    raw_entries = _as_list(value) + list(add_watchers or [])
    remove_names = set(remove_watchers or [])
    entries = []

    for item in raw_entries:
        if isinstance(item, str):
            policy = _load_watcher_policy(repo_root, item)
        elif isinstance(item, dict):
            policy = dict(item)
        else:
            raise RecipeError("Recipe field 'watchers' must contain names or mappings")

        policy_name = policy.get("name")
        policy_ref = policy.get("policy_ref")
        ref_stem = Path(str(policy_ref)).stem if policy_ref else None
        if (
            policy_name in remove_names
            or policy_ref in remove_names
            or ref_stem in remove_names
        ):
            continue
        entries.append(policy)

    return entries


def _action_to_string(action: Any) -> str:
    if isinstance(action, str):
        return action
    if isinstance(action, dict) and len(action) == 1:
        action_name, params = next(iter(action.items()))
        if params in (None, {}):
            return f"{action_name}()"
        if isinstance(params, dict):
            param_parts = [
                f"{key}={json.dumps(str(value))}"
                for key, value in sorted(params.items())
            ]
            return f"{action_name}({', '.join(param_parts)})"
        return f"{action_name}({json.dumps(str(params))})"
    raise RecipeError("Watcher actions must be strings or single-key mappings")


def _render_watcher_blocks(watchers: list[dict[str, Any]]) -> str:
    if not watchers:
        return ""

    blocks = []
    for watcher in watchers:
        pattern = watcher.get("pattern")
        trigger_on_job_end = watcher.get("trigger_on_job_end")
        if not pattern and not trigger_on_job_end:
            name = watcher.get("name") or watcher.get("policy_ref") or "<unnamed>"
            raise RecipeError(
                f"Watcher policy '{name}' must define pattern or trigger_on_job_end"
            )

        lines = ["#WATCHER_BEGIN"]
        for key in (
            "name",
            "pattern",
            "interval",
            "captures",
            "condition",
            "timer_mode_enabled",
            "timer_interval_seconds",
            "trigger_on_job_end",
            "trigger_job_states",
            "remaining_resubmits",
        ):
            if key not in watcher:
                continue
            value = watcher[key]
            if isinstance(value, (list, dict)):
                rendered_value = json.dumps(value)
            elif isinstance(value, bool):
                rendered_value = "true" if value else "false"
            else:
                rendered_value = str(value)
            lines.append(f"# {key}: {rendered_value}")

        actions = _as_list(watcher.get("actions"))
        if actions:
            lines.append("# actions:")
            for action in actions:
                lines.append(f"#   - {_action_to_string(action)}")
        lines.append("#WATCHER_END")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _merge_vars(*maps: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in maps:
        if value is None:
            continue
        if not isinstance(value, dict):
            raise RecipeError("Recipe vars must be a mapping")
        merged.update(value)
    return merged


def _validate_recipe_data(data: dict[str, Any], source_dir: Path) -> None:
    unknown_keys = sorted(set(data) - _ALLOWED_TOP_LEVEL_KEYS)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise RecipeError(f"Unknown launch recipe field(s): {joined}")

    if not source_dir.exists():
        raise RecipeError(f"Recipe source_dir does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise RecipeError(f"Recipe source_dir is not a directory: {source_dir}")

    env = data.get("env")
    if env is not None and not isinstance(env, (str, dict)):
        raise RecipeError("Recipe field 'env' must be a profile name or mapping")

    sbatch = data.get("sbatch", {})
    if sbatch is None:
        return
    if not isinstance(sbatch, dict):
        raise RecipeError("Recipe field 'sbatch' must be a mapping")
    for field_name in _SBATCH_INT_FIELDS:
        value = sbatch.get(field_name)
        if value is None:
            continue
        if not isinstance(value, int) or value <= 0:
            raise RecipeError(
                f"Recipe sbatch field '{field_name}' must be a positive integer"
            )


def _render_var_exports(values: dict[str, Any]) -> str:
    if not values:
        return ""

    lines = ["# ssync recipe variables"]
    for key, value in values.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise RecipeError(f"Invalid recipe variable name: {key}")
        lines.append(f"export {key}={quote(str(value))}")
    return "\n".join(lines)


def _read_fragment(path: Path) -> str:
    if not path.exists():
        raise RecipeError(f"Recipe fragment not found: {path}")
    if not path.is_file():
        raise RecipeError(f"Recipe fragment is not a file: {path}")
    return path.read_text().strip()


def _render_fragment_entries(
    *,
    repo_root: Path,
    recipe_dir: Path,
    entries: list[dict[str, Any]],
    field_name: str,
    section_vars: dict[str, Any],
    fragment_paths: list[Path],
    resolved_vars: dict[str, Any],
) -> list[str]:
    sections = []
    for entry in entries:
        fragment_vars = _merge_vars(entry.get("vars"))
        fragment_path = _resolve_path(
            repo_root, recipe_dir, entry["script"], f"{field_name}.script"
        )
        fragment_paths.append(fragment_path)
        sections.append(
            f"# ssync {field_name}: {_display_path(fragment_path, repo_root)}"
        )
        section_exports = _render_var_exports(section_vars)
        if section_exports:
            sections.append(section_exports)
            resolved_vars.update(section_vars)
        fragment_exports = _render_var_exports(fragment_vars)
        if fragment_exports:
            sections.append(fragment_exports)
            resolved_vars.update(fragment_vars)
        sections.append(_read_fragment(fragment_path))
    return sections


def render_launch_recipe(
    recipe_path: str | Path,
    *,
    workflow: str | None = None,
    host_partition: str | None = None,
    env: str | None = None,
    vars: dict[str, Any] | None = None,
    sbatch: dict[str, Any] | None = None,
    add_watchers: list[str] | None = None,
    remove_watchers: list[str] | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> RenderedRecipe:
    """Resolve a project launch recipe into one shell script."""
    bare_recipe_ref = _is_bare_recipe_ref(recipe_path)
    recipe_path = _resolve_named_recipe_path(recipe_path)
    recipe_dir = recipe_path.parent
    repo_root = find_repo_root(Path.cwd() if bare_recipe_ref else recipe_path)
    recipe_data = _load_yaml_mapping(recipe_path)
    if workflow is not None:
        recipe_data["extends"] = workflow
        recipe_data.pop("workflow", None)
    if host_partition is not None:
        recipe_data["host_partition"] = host_partition
    if env is not None:
        recipe_data["env"] = env
    if vars:
        recipe_data["vars"] = _merge_section(
            recipe_data.get("vars"), vars, append_scripts=False
        )
    if sbatch:
        recipe_data["sbatch"] = _merge_section(
            recipe_data.get("sbatch"), sbatch, append_scripts=False
        )

    data = _resolve_recipe_data(repo_root, recipe_data)

    source_value = data.get("source_dir")
    source_dir = (
        repo_root
        if source_value is None
        else _resolve_repo_path(repo_root, source_value, "source_dir")
    )
    _validate_recipe_data(data, source_dir)

    vars_from_recipe = _merge_vars(data.get("vars"))
    resolved_vars = dict(vars_from_recipe)
    sections = ["#!/bin/bash", "set -euo pipefail"]
    resolved_watchers = _watcher_entries(
        repo_root,
        data.get("watchers"),
        add_watchers=add_watchers,
        remove_watchers=remove_watchers,
    )
    watcher_blocks = _render_watcher_blocks(resolved_watchers)
    if watcher_blocks:
        sections.append(watcher_blocks)

    var_exports = _render_var_exports(vars_from_recipe)
    if var_exports:
        sections.append(var_exports)

    fragment_paths: list[Path] = []
    prepare_section = data.get("prepare")
    prepare_vars = (
        _merge_vars(prepare_section.get("vars"))
        if isinstance(prepare_section, dict) and "vars" in prepare_section
        else {}
    )
    prepare_sections = _render_fragment_entries(
        repo_root=repo_root,
        recipe_dir=recipe_dir,
        entries=_script_entries(prepare_section, "prepare"),
        field_name="prepare",
        section_vars=prepare_vars,
        fragment_paths=fragment_paths,
        resolved_vars=resolved_vars,
    )
    if prepare_sections:
        sections.append("#LOGIN_SETUP_BEGIN")
        if var_exports:
            sections.append(var_exports)
        sections.extend(prepare_sections)
        sections.append("#LOGIN_SETUP_END")

    env_section = data.get("env")
    env_vars = (
        _merge_vars(env_section.get("vars"))
        if isinstance(env_section, dict) and "vars" in env_section
        else {}
    )
    sections.extend(
        _render_fragment_entries(
            repo_root=repo_root,
            recipe_dir=recipe_dir,
            entries=_script_entries(env_section, "env"),
            field_name="env",
            section_vars=env_vars,
            fragment_paths=fragment_paths,
            resolved_vars=resolved_vars,
        )
    )

    run_entries = _script_entries(data.get("run"), "run")
    if len(run_entries) != 1:
        raise RecipeError("Launch recipe must define exactly one run script")

    run_entry = run_entries[0]
    run_vars = _merge_vars(run_entry.get("vars"))
    run_path = _resolve_path(repo_root, recipe_dir, run_entry["script"], "run.script")
    fragment_paths.append(run_path)
    sections.append(f"# ssync run: {_display_path(run_path, repo_root)}")
    run_exports = _render_var_exports(run_vars)
    if run_exports:
        sections.append(run_exports)
        resolved_vars.update(run_vars)
    sections.append(_read_fragment(run_path))

    sbatch = data.get("sbatch", {})
    if sbatch is None:
        sbatch = {}
    if not isinstance(sbatch, dict):
        raise RecipeError("Recipe field 'sbatch' must be a mapping")

    script_content = "\n\n".join(sections).rstrip() + "\n"
    sbatch_manifest = {
        key: value
        for key, value in {
            "job_name": data.get("job_name") or sbatch.get("job_name"),
            "cpus": sbatch.get("cpus"),
            "mem": sbatch.get("mem"),
            "time": sbatch.get("time"),
            "partition": sbatch.get("partition"),
            "output": sbatch.get("output"),
            "error": sbatch.get("error"),
            "nodes": sbatch.get("nodes"),
            "ntasks_per_node": sbatch.get("ntasks_per_node"),
            "gpus_per_node": sbatch.get("gpus_per_node"),
            "gres": sbatch.get("gres"),
            "constraint": sbatch.get("constraint"),
            "account": sbatch.get("account"),
        }.items()
        if value is not None
    }
    manifest = {
        "manifest_version": 1,
        "recipe_path": str(recipe_path),
        "repo_root": str(repo_root),
        "source_dir": str(source_dir),
        "host": data.get("host"),
        "host_partition": data.get("host_partition"),
        "env": recipe_data.get("env")
        if isinstance(recipe_data.get("env"), str)
        else None,
        "fragments": [str(path) for path in fragment_paths],
        "watchers": resolved_watchers,
        "vars": resolved_vars,
        "sbatch": sbatch_manifest,
        "cli_overrides": cli_overrides or {},
        "script_sha256": sha256(script_content.encode("utf-8")).hexdigest(),
        "rendered_script": script_content,
    }

    return RenderedRecipe(
        recipe_path=recipe_path,
        repo_root=repo_root,
        script_content=script_content,
        source_dir=source_dir,
        host=data.get("host"),
        job_name=data.get("job_name") or sbatch.get("job_name"),
        cpus=sbatch.get("cpus"),
        mem=sbatch.get("mem"),
        time=sbatch.get("time"),
        partition=sbatch.get("partition"),
        output=sbatch.get("output"),
        error=sbatch.get("error"),
        nodes=sbatch.get("nodes"),
        ntasks_per_node=sbatch.get("ntasks_per_node"),
        gpus_per_node=sbatch.get("gpus_per_node"),
        gres=sbatch.get("gres"),
        constraint=sbatch.get("constraint"),
        account=sbatch.get("account"),
        python_env=data.get("python_env"),
        vars=resolved_vars,
        fragments=fragment_paths,
        manifest=manifest,
    )
