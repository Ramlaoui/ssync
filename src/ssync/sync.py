from pathlib import Path

from .manager import SlurmManager
from .models.cluster import SlurmHost


class SyncManager:
    """Manages file synchronization to SLURM hosts."""

    def __init__(
        self, slurm_manager: SlurmManager, source_dir: Path, use_gitignore: bool = True
    ):
        self.slurm_manager = slurm_manager
        self.source_dir = source_dir
        self.use_gitignore = use_gitignore

    def sync_to_host(
        self,
        slurm_host: SlurmHost,
        exclude: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> bool:
        """Sync source directory to a specific SLURM host using rsync over SSH."""
        conn = self.slurm_manager._get_connection(slurm_host.host)

        # Build rsync command with excludes
        exclude_args = []

        # First, add .gitignore patterns if it exists and not disabled
        gitignore_path = self.source_dir / ".gitignore"
        if self.use_gitignore and gitignore_path.exists():
            exclude_args.extend(["--exclude-from", str(gitignore_path)])

        # Add manual excludes
        if exclude:
            for pattern in exclude:
                exclude_args.extend(["--exclude", pattern])

        # Add include patterns to override .gitignore
        if include_patterns:
            for pattern in include_patterns:
                exclude_args.extend(["--include", pattern])

        # Create target directory: work_dir/source_dir_name/
        source_dir_name = self.source_dir.name
        target_dir = f"{slurm_host.work_dir}/{source_dir_name}"

        # Build target - use just hostname if username is empty (SSH config will handle it)
        if slurm_host.host.username:
            target = (
                f"{slurm_host.host.username}@{slurm_host.host.hostname}:{target_dir}/"
            )
        else:
            target = f"{slurm_host.host.hostname}:{target_dir}/"

        rsync_cmd = []
        if slurm_host.host.password:
            rsync_cmd = [
                "sshpass",
                "-p",
                slurm_host.host.password
            ]
        rsync_cmd += ["rsync", "-avz", *exclude_args, f"{self.source_dir}/", target]

        try:
            # Use fabric's local() to run rsync locally (it handles SSH properly)
            result = conn.local(" ".join(rsync_cmd), hide=False)
            return result.ok
        except Exception as e:
            print(f"Failed to sync to {slurm_host.host.hostname}: {e}")
            return False

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
