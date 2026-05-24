from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .models.cluster import SlurmDefaults
from .utils.config import Config, ConfigError, get_user_config_path


class ConfigHostError(Exception):
    """Raised when ssync host config editing cannot be completed."""


@dataclass(frozen=True)
class SshAlias:
    """An SSH config alias discovered from a concrete Host entry."""

    alias: str
    source_path: Path
    line_number: int


@dataclass(frozen=True)
class ResolvedSshAlias:
    """Safe subset of `ssh -G` output for an SSH config alias."""

    alias: str
    hostname: str
    user: str | None = None
    port: int | None = None
    proxyjump: str | None = None
    has_identity_file: bool = False
    options: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ConfigEditResult:
    """Result of previewing or writing an ssync host config edit."""

    config_path: Path
    host_entry: dict[str, Any]
    rendered_yaml: str
    dry_run: bool
    changed: bool
    created: bool
    updated: bool
    before_sha256: str | None
    after_sha256: str
    before_mtime_ns: int | None


def _is_concrete_alias(value: str) -> bool:
    if not value or value.startswith("-"):
        return False
    return not any(char in value for char in "*?! \t\r\n/")


def _default_ssh_config_path() -> Path:
    return Path.home() / ".ssh" / "config"


def _resolve_include_path(include_path: str, *, current_file: Path) -> list[Path]:
    expanded = Path(include_path).expanduser()
    if not expanded.is_absolute():
        expanded = current_file.parent / expanded
    return sorted(path for path in expanded.parent.glob(expanded.name) if path.is_file())


def _iter_ssh_config_files(config_path: Path) -> list[Path]:
    config_path = config_path.expanduser()
    if not config_path.exists():
        return []

    ordered: list[Path] = []
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.expanduser().resolve()
        if resolved in seen or not resolved.exists() or not resolved.is_file():
            return
        seen.add(resolved)
        ordered.append(resolved)

        try:
            lines = resolved.read_text().splitlines()
        except OSError:
            return

        for line in lines:
            try:
                parts = shlex.split(line, comments=True, posix=True)
            except ValueError:
                continue
            if not parts or parts[0].lower() != "include":
                continue
            for pattern in parts[1:]:
                for included in _resolve_include_path(pattern, current_file=resolved):
                    visit(included)

    visit(config_path)
    return ordered


def list_ssh_config_aliases(config_path: str | Path | None = None) -> list[SshAlias]:
    """Return concrete aliases declared in OpenSSH config Host lines."""
    root_config = Path(config_path).expanduser() if config_path else _default_ssh_config_path()
    aliases: dict[str, SshAlias] = {}

    for path in _iter_ssh_config_files(root_config):
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue

        for line_number, line in enumerate(lines, start=1):
            try:
                parts = shlex.split(line, comments=True, posix=True)
            except ValueError:
                continue
            if not parts or parts[0].lower() != "host":
                continue

            for alias in parts[1:]:
                if not _is_concrete_alias(alias):
                    continue
                aliases.setdefault(
                    alias,
                    SshAlias(alias=alias, source_path=path, line_number=line_number),
                )

    return sorted(aliases.values(), key=lambda item: item.alias)


def _parse_ssh_g_output(output: str) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        key, _, value = line.partition(" ")
        if not value:
            continue
        options.setdefault(key.lower(), []).append(value.strip())
    return options


def resolve_ssh_config_alias(
    alias: str,
    *,
    config_path: str | Path | None = None,
    timeout: float = 5.0,
) -> ResolvedSshAlias:
    """Resolve an SSH alias with OpenSSH's own config expansion."""
    if not _is_concrete_alias(alias):
        raise ConfigHostError(f"Invalid SSH alias: {alias!r}")

    known_aliases = {item.alias for item in list_ssh_config_aliases(config_path)}
    if alias not in known_aliases:
        raise ConfigHostError(f"SSH alias {alias!r} was not found in SSH config")

    command = ["ssh", "-G"]
    if config_path is not None:
        command.extend(["-F", str(Path(config_path).expanduser())])
    command.append(alias)

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ConfigHostError("OpenSSH client executable 'ssh' was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConfigHostError(f"Timed out resolving SSH alias {alias!r}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "ssh -G failed"
        raise ConfigHostError(f"Could not resolve SSH alias {alias!r}: {detail}")

    options = _parse_ssh_g_output(result.stdout)
    port = None
    if options.get("port"):
        try:
            port = int(options["port"][-1])
        except ValueError:
            port = None

    safe_options = {
        key: values[-1]
        for key, values in options.items()
        if key in {"hostname", "user", "port", "proxyjump"}
    }
    identity_files = options.get("identityfile", [])
    return ResolvedSshAlias(
        alias=alias,
        hostname=options.get("hostname", [alias])[-1],
        user=options.get("user", [None])[-1],
        port=port,
        proxyjump=options.get("proxyjump", [None])[-1],
        has_identity_file=bool(identity_files),
        options=safe_options,
    )


def _read_config_for_edit(config_path: Path) -> tuple[dict[str, Any], str | None]:
    if not config_path.exists():
        return {}, None

    text = config_path.read_text()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigHostError(f"Invalid YAML in config file: {exc}") from exc

    if data is None:
        return {}, text
    if not isinstance(data, dict):
        raise ConfigHostError("ssync config must be a YAML mapping")
    return data, text


def _sha256_text(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _guard_current_config(
    *,
    config_path: Path,
    expected_mtime_ns: int | None,
    expected_sha256: str | None,
    current_text: str | None,
) -> None:
    if expected_mtime_ns is not None:
        current_mtime_ns = config_path.stat().st_mtime_ns if config_path.exists() else None
        if current_mtime_ns != expected_mtime_ns:
            raise ConfigHostError("Config file changed since preview")

    if expected_sha256 is not None and _sha256_text(current_text) != expected_sha256:
        raise ConfigHostError("Config file content changed since preview")


def _validated_slurm_defaults(
    slurm_defaults: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if slurm_defaults is None:
        return None
    try:
        defaults = SlurmDefaults(**dict(slurm_defaults))
    except TypeError as exc:
        raise ConfigHostError(f"Invalid Slurm defaults: {exc}") from exc
    return {
        key: value
        for key, value in defaults.__dict__.items()
        if value is not None
    }


def _render_yaml(data: Mapping[str, Any]) -> str:
    rendered = yaml.safe_dump(dict(data), sort_keys=False, default_flow_style=False)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def _validate_rendered_config(rendered_yaml: str, config_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ssync-config-validate-") as temp_dir:
        temp_path = Path(temp_dir) / config_path.name
        temp_path.write_text(rendered_yaml)
        try:
            Config(config_path=temp_path)
        except ConfigError as exc:
            raise ConfigHostError(f"Resulting ssync config is invalid: {exc}") from exc


def _atomic_write_config(config_path: Path, rendered_yaml: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    mode = (config_path.stat().st_mode & 0o777) if config_path.exists() else 0o600
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        dir=config_path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w") as temp_file:
            temp_file.write(rendered_yaml)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, config_path)
    finally:
        temp_path.unlink(missing_ok=True)


def add_host_from_ssh_alias(
    alias: str,
    work_dir: str,
    scratch_dir: str,
    slurm_defaults: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
    *,
    ssh_config_path: str | Path | None = None,
    dry_run: bool = False,
    replace_existing: bool = False,
    expected_mtime_ns: int | None = None,
    expected_sha256: str | None = None,
) -> ConfigEditResult:
    """Add an ssync host entry backed by an existing SSH config alias."""
    resolved = resolve_ssh_config_alias(alias, config_path=ssh_config_path)
    target_path = Path(config_path).expanduser() if config_path else get_user_config_path()
    data, before_text = _read_config_for_edit(target_path)
    before_mtime_ns = target_path.stat().st_mtime_ns if target_path.exists() else None
    _guard_current_config(
        config_path=target_path,
        expected_mtime_ns=expected_mtime_ns,
        expected_sha256=expected_sha256,
        current_text=before_text,
    )

    hosts = data.setdefault("hosts", [])
    if not isinstance(hosts, list):
        raise ConfigHostError("ssync config 'hosts' value must be a list")

    defaults = _validated_slurm_defaults(slurm_defaults)
    host_entry: dict[str, Any] = {
        "hostname": resolved.alias,
        "use_ssh_config": True,
        "work_dir": str(work_dir),
        "scratch_dir": str(scratch_dir),
    }
    if defaults:
        host_entry["slurm_defaults"] = defaults

    existing_index = next(
        (
            index
            for index, item in enumerate(hosts)
            if isinstance(item, dict) and item.get("hostname") == alias
        ),
        None,
    )
    updated = existing_index is not None
    if updated and not replace_existing:
        raise ConfigHostError(f"ssync host {alias!r} already exists")
    if updated:
        hosts[existing_index] = host_entry
    else:
        hosts.append(host_entry)

    rendered_yaml = _render_yaml(data)
    _validate_rendered_config(rendered_yaml, target_path)
    after_sha256 = _sha256_text(rendered_yaml)
    assert after_sha256 is not None
    changed = before_text != rendered_yaml

    if changed and not dry_run:
        _atomic_write_config(target_path, rendered_yaml)

    return ConfigEditResult(
        config_path=target_path,
        host_entry=host_entry,
        rendered_yaml=rendered_yaml,
        dry_run=dry_run,
        changed=changed,
        created=before_text is None,
        updated=updated,
        before_sha256=_sha256_text(before_text),
        after_sha256=after_sha256,
        before_mtime_ns=before_mtime_ns,
    )
