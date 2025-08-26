import os
import tempfile
from pathlib import Path

from .manager import SlurmManager
from .models.cluster import SlurmHost
from .utils.logging import setup_logger

logger = setup_logger(__name__)


class SyncManager:
    """Manages file synchronization to SLURM hosts."""

    def __init__(
        self,
        slurm_manager: SlurmManager,
        source_dir: Path,
        use_gitignore: bool = True,
        max_depth: int = 3,
    ):
        self.slurm_manager = slurm_manager
        self.source_dir = source_dir
        self.use_gitignore = use_gitignore
        self.max_depth = max_depth

    def _collect_rsync_filter_rules(self, max_depth: int = 3) -> list[str]:
        """
        Convert .gitignore files to basic rsync filter rules.

        Simple approach:
        - Lines starting with ! become include rules (+ pattern)
        - Other non-empty, non-comment lines become exclude rules (- pattern)
        - Patterns ending with / get /*** appended for directory matching
        """
        rules = []

        def process_gitignore(gitignore_path: Path, base_path: str = ""):
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()

                        if not line or line.startswith("#"):
                            continue

                        if line.startswith("!"):
                            pattern = line[1:]
                            prefix = "+"
                        else:
                            pattern = line
                            prefix = "-"

                        if base_path and not pattern.startswith("/"):
                            pattern = f"{base_path}/{pattern}"
                        elif pattern.startswith("/"):
                            pattern = pattern[1:]

                        if pattern.endswith("/"):
                            pattern = pattern.rstrip("/") + "/***"

                        rules.append(f"{prefix} {pattern}")

            except (OSError, UnicodeDecodeError):
                pass

        def walk_directory(path: Path, depth: int = 0):
            if depth > max_depth:
                return

            gitignore = path / ".gitignore"
            if gitignore.exists():
                relative_path = path.relative_to(self.source_dir).as_posix()
                base = relative_path if relative_path != "." else ""
                process_gitignore(gitignore, base)

            if depth < max_depth:
                try:
                    for item in path.iterdir():
                        if item.is_dir():
                            walk_directory(item, depth + 1)
                except (OSError, PermissionError):
                    pass

        walk_directory(self.source_dir)
        return rules

    def sync_to_host(
        self,
        slurm_host: SlurmHost,
        exclude: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> bool:
        """Sync source directory to a specific SLURM host using rsync over SSH."""
        conn = self.slurm_manager._get_connection(slurm_host.host)

        exclude_args = []
        temp_gitignore_path = None
        if self.use_gitignore:
            gitignore_patterns = self._collect_rsync_filter_rules()
            if gitignore_patterns:
                temp_fd, temp_gitignore_path = tempfile.mkstemp(
                    suffix=".gitignore", text=True
                )
                try:
                    with os.fdopen(temp_fd, "w") as temp_gitignore:
                        for pattern in gitignore_patterns:
                            temp_gitignore.write(f"{pattern}\n")
                        temp_gitignore.flush()
                        os.fsync(temp_gitignore.fileno())
                except Exception:
                    if os.path.exists(temp_gitignore_path):
                        os.unlink(temp_gitignore_path)
                    raise

                exclude_args.extend(["--filter", f"'merge {temp_gitignore_path}'"])
            else:
                gitignore_path = self.source_dir / ".gitignore"
                if gitignore_path.exists():
                    exclude_args.extend(["--exclude-from", str(gitignore_path)])

        if exclude:
            for pattern in exclude:
                exclude_args.extend(["--exclude", pattern])

        if include_patterns:
            for pattern in include_patterns:
                exclude_args.extend(["--include", pattern])

        source_dir_name = self.source_dir.name
        target_dir = f"{slurm_host.work_dir}/{source_dir_name}"

        if slurm_host.host.username:
            target = (
                f"{slurm_host.host.username}@{slurm_host.host.hostname}:{target_dir}/"
            )
        else:
            target = f"{slurm_host.host.hostname}:{target_dir}/"

        rsync_cmd = []
        if slurm_host.host.password:
            rsync_cmd = ["sshpass", "-p", slurm_host.host.password]
        rsync_cmd += ["rsync", "-avz", *exclude_args, f"{self.source_dir}/", target]

        try:
            result = conn.local(" ".join(rsync_cmd), hide=False)
            return result.ok
        except Exception as e:
            logger.warning(f"Failed to sync to {slurm_host.host.hostname}: {e}")
            return False
        finally:
            if temp_gitignore_path and os.path.exists(temp_gitignore_path):
                try:
                    os.unlink(temp_gitignore_path)
                except OSError:
                    pass

    def sync_to_all(
        self,
        exclude: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> dict[str, bool]:
        """Sync to all configured hosts. Returns dict of hostname -> success."""
        results = {}
        for slurm_host in self.slurm_manager.slurm_hosts:
            hostname = slurm_host.host.hostname
            results[hostname] = self.sync_to_host(slurm_host, exclude, include_patterns)
        return results
