from fabric import Connection
from fastapi import Path

from .config import config


def get_file(
    conn: Connection, remote_path: str, local_path: str, filename: str | None
) -> None:
    """Download a file from a remote host."""

    if not local_path:
        local_path = config.cache_path
    file_path = Path(local_path) / (filename or Path(remote_path).name)
    conn.get(remote_path, local=file_path)

    return file_path
