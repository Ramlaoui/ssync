from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Host:
    hostname: str
    username: str
    port: int = 22
    password: str | None = None
    ProxyJump: Host | None = None
    key_file: str | None = None
    use_ssh_config: bool = True

    def __post_init__(self):
        if self.key_file:
            self.key_file = Path(self.key_file).expanduser().resolve()
        if self.ProxyJump:
            self.ProxyJump = Host(**self.ProxyJump)


@dataclass(frozen=True)
class SlurmHost:
    host: Host
    work_dir: Path
    scratch_dir: Path
