"""Authenticated, narrowly scoped editing of host submission defaults."""

import asyncio
import copy
import hashlib
import threading
from pathlib import Path
from typing import Annotated, Optional

import yaml
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from ...config_hosts import _atomic_write_config

_EDIT_LOCK = threading.RLock()


class HostDefaultsPatch(BaseModel):
    """Editable submission defaults; connection credentials are never exposed."""

    model_config = ConfigDict(extra="forbid")
    partition: Optional[str] = None
    account: Optional[str] = None
    constraint: Optional[str] = None
    qos: Optional[str] = None
    gres: Optional[str] = None
    time: Optional[str] = None
    cpus: Optional[Annotated[StrictInt, Field(ge=1)]] = None
    mem: Optional[Annotated[StrictInt, Field(ge=1)]] = None
    nodes: Optional[Annotated[StrictInt, Field(ge=1)]] = None
    ntasks_per_node: Optional[Annotated[StrictInt, Field(ge=1)]] = None
    gpus_per_node: Optional[Annotated[StrictInt, Field(ge=0)]] = None

    @field_validator("partition", "account", "constraint", "qos", "gres", "time")
    @classmethod
    def single_line(cls, value):
        if value is None:
            return None
        value = value.strip()
        if len(value) > 256 or any(ord(char) < 32 for char in value):
            raise ValueError("Use a single line of at most 256 characters")
        return value or None


class UpdateHostSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    slurm_defaults: HostDefaultsPatch


def _snapshot(config):
    paths = [Path(config.config_path), *config.get_overlay_paths()]
    documents = []
    digest = hashlib.sha256()
    for path in paths:
        try:
            text = path.read_text()
            data = yaml.safe_load(text) or {}
        except (OSError, yaml.YAMLError):
            raise HTTPException(
                409,
                "The ssync configuration cannot be read. Fix it before editing host defaults.",
            )
        if not isinstance(data, dict):
            raise HTTPException(409, "The ssync configuration must be a YAML mapping.")
        digest.update(str(path).encode())
        digest.update(b"\0")
        digest.update(text.encode())
        documents.append((path, text, data))
    owners = [item for item in documents if "hosts" in item[2]]
    if not owners:
        raise HTTPException(404, "No hosts are configured.")
    return owners[-1], digest.hexdigest()


def _find_host(data, hostname):
    hosts = data.get("hosts")
    if not isinstance(hosts, list):
        raise HTTPException(409, "Configured hosts must be a list.")
    matches = [
        (index, host)
        for index, host in enumerate(hosts)
        if isinstance(host, dict) and host.get("hostname") == hostname
    ]
    if not matches:
        raise HTTPException(404, "Host not found.")
    if len(matches) != 1:
        raise HTTPException(409, "This hostname has more than one configuration entry.")
    return matches[0]


def _safe_settings(hostname, host, revision):
    defaults = host.get("slurm_defaults") or {}
    if not isinstance(defaults, dict):
        raise HTTPException(409, "Host defaults must be a YAML mapping.")
    return {
        "hostname": hostname,
        "slurm_defaults": {
            key: value
            for key, value in defaults.items()
            if key in HostDefaultsPatch.model_fields
        },
        "revision": revision,
    }


def _replace_defaults(text, data, host_index, updated):
    """Replace only the chosen defaults block, retaining unrelated YAML verbatim."""
    document = yaml.compose(text, Loader=yaml.SafeLoader)
    if not isinstance(document, yaml.MappingNode):
        raise HTTPException(409, "The ssync configuration must be a YAML mapping.")
    hosts_node = next(
        (value for key, value in document.value if key.value == "hosts"), None
    )
    if not isinstance(hosts_node, yaml.SequenceNode):
        raise HTTPException(409, "Host settings use an unsupported YAML layout.")
    node = hosts_node.value[host_index]
    if (
        not isinstance(node, yaml.MappingNode)
        or node.flow_style
        or hosts_node.flow_style
    ):
        raise HTTPException(
            409, "Expand the host's compact YAML mapping before editing its defaults."
        )
    entry = next(
        ((key, value) for key, value in node.value if key.value == "slurm_defaults"),
        None,
    )
    lines = text.splitlines(keepends=True)
    indent = node.start_mark.column
    if entry:
        key, value = entry
        start = key.start_mark.line
        end_mark = value.end_mark
        if isinstance(value, yaml.MappingNode) and value.value:
            end_mark = value.value[-1][1].end_mark
        end = end_mark.line + (1 if end_mark.column else 0)
        end = max(end, start + 1)
    else:
        end_mark = node.value[-1][1].end_mark
        start = end = end_mark.line + (1 if end_mark.column else 0)
    block = yaml.safe_dump({"slurm_defaults": updated}, sort_keys=False)
    replacement = "".join(
        " " * indent + line if line.strip() else line
        for line in block.splitlines(keepends=True)
    )
    if start and not lines[start - 1].endswith("\n"):
        replacement = "\n" + replacement
    rendered = "".join(lines[:start]) + replacement + "".join(lines[end:])
    expected = copy.deepcopy(data)
    expected["hosts"][host_index]["slurm_defaults"] = updated
    try:
        valid = yaml.safe_load(rendered) == expected
    except yaml.YAMLError:
        valid = False
    if not valid:
        raise HTTPException(
            409,
            "This host uses shared or complex YAML. Edit its defaults in the configuration file.",
        )
    return rendered


def read_host_settings(config, hostname):
    with _EDIT_LOCK:
        (_, _, data), revision = _snapshot(config)
        _, host = _find_host(data, hostname)
        return _safe_settings(hostname, host, revision)


def update_host_settings(config, hostname, request):
    with _EDIT_LOCK:
        (path, text, data), revision = _snapshot(config)
        if revision != request.revision:
            raise HTTPException(
                409, "Host settings changed. Reopen the settings form before saving."
            )
        index, host = _find_host(data, hostname)
        defaults = host.get("slurm_defaults") or {}
        if not isinstance(defaults, dict):
            raise HTTPException(409, "Host defaults must be a YAML mapping.")
        updated = dict(defaults)
        for key, value in request.slurm_defaults.model_dump(exclude_unset=True).items():
            if value is None:
                updated.pop(key, None)
            else:
                updated[key] = value
        if updated != defaults:
            rendered = _replace_defaults(text, data, index, updated)
            # An external editor may have saved while this request was preparing the change.
            if _snapshot(config)[1] != revision:
                raise HTTPException(
                    409,
                    "Host settings changed. Reopen the settings form before saving.",
                )
            _atomic_write_config(path, rendered)
        return read_host_settings(config, hostname)


def register_host_settings_routes(app: FastAPI, *, verify_api_key_dependency, config):
    @app.get("/api/hosts/{hostname}/settings")
    async def get_settings(
        hostname: str, _authenticated=Depends(verify_api_key_dependency)
    ):
        return await asyncio.to_thread(read_host_settings, config, hostname)

    @app.put("/api/hosts/{hostname}/settings")
    async def put_settings(
        hostname: str,
        request: UpdateHostSettings,
        _authenticated=Depends(verify_api_key_dependency),
    ):
        return await asyncio.to_thread(update_host_settings, config, hostname, request)
