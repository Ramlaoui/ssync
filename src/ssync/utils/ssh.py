from fabric import Connection
from pathlib import Path

from .config import config
from .logging import setup_logger

logger = setup_logger(__name__, "DEBUG")

def get_file(
    conn: Connection, remote_path: str, local_path: str, filename: str | None
) -> None:
    """Download a file from a remote host."""

    if not local_path:
        local_path = config.cache_path
    file_path = Path(local_path) / (filename or Path(remote_path).name)
    conn.get(remote_path, local=file_path)

    return file_path


def send_file(conn: Connection, local_path: str | Path, remote_path: str | Path, is_remote_dir: bool=False) -> str:
    """Upload a file to a remote host."""
    if not Path(local_path).exists():
        raise FileNotFoundError(f"Local file {local_path} does not exist.")

    if is_remote_dir:
        remote_path = Path(remote_path) / Path(local_path).name

    if isinstance(remote_path, Path):
        remote_path = str(remote_path.resolve())

    logger.debug(f"Sending {local_path} to {conn.host}:{remote_path}")
    # Use shlex.quote to prevent command injection
    from shlex import quote
    parent_dir = str(Path(remote_path).parent.resolve())
    conn.run(f"mkdir -p {quote(parent_dir)}")
    conn.put(open(local_path, "rb"), remote=remote_path)
    logger.debug(f"Sent {local_path} to {conn.host}:{remote_path}")

    return remote_path

