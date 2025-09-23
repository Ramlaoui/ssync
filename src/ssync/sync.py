import fnmatch
import os
import subprocess
import tempfile
from pathlib import Path

from .manager import SlurmManager
from .models.cluster import PathRestrictions, SlurmHost
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
        path_restrictions: PathRestrictions | None = None,
    ):
        self.slurm_manager = slurm_manager
        self.source_dir = source_dir
        self.use_gitignore = use_gitignore
        self.max_depth = max_depth
        self.path_restrictions = path_restrictions

    def _validate_path(self, path: Path) -> tuple[bool, str]:
        """Validate a path against restrictions.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.path_restrictions or not self.path_restrictions.enabled:
            return True, ""

        path = path.resolve()
        path_str = str(path)
        home_path = Path.home()

        # Check if path is in forbidden locations first (highest priority)
        for forbidden in self.path_restrictions.forbidden_paths:
            if path_str.startswith(forbidden) or fnmatch.fnmatch(path_str, forbidden):
                return False, f"Path is in forbidden location: {forbidden}"

        # Check if path is explicitly allowed (this takes precedence over other restrictions)
        if self.path_restrictions.allowed_paths:
            allowed = False
            for allowed_path in self.path_restrictions.allowed_paths:
                # Handle paths that might contain wildcards
                if "*" in allowed_path:
                    if fnmatch.fnmatch(path_str, allowed_path):
                        allowed = True
                        break
                else:
                    # For non-wildcard paths, check if path starts with allowed path
                    if path_str.startswith(allowed_path.rstrip("/")):
                        allowed = True
                        break

            if allowed:
                # Path is explicitly allowed, skip other checks
                return True, ""
            else:
                # Path is not in allowed list
                return False, "Path is not in allowed locations"

        # If no allowed_paths specified, check general restrictions
        # Check if absolute paths are allowed
        if not self.path_restrictions.allow_absolute:
            if not path_str.startswith(str(home_path)) and not path_str.startswith(
                "/tmp"
            ):
                return False, "Absolute paths outside home directory are not allowed"

        # Check home directory restriction
        if not self.path_restrictions.allow_home:
            if path_str.startswith(str(home_path)):
                return False, "Syncing from home directory is not allowed"

        # Check tmp directory restriction
        if not self.path_restrictions.allow_tmp:
            if path_str.startswith("/tmp"):
                return False, "Syncing from /tmp is not allowed"

        return True, ""

    def _check_directory_size(self, path: Path) -> tuple[float, bool, str]:
        """Check directory size and validate against restrictions.

        Returns:
            Tuple of (size_gb, is_valid, error_message)
        """
        try:
            # Use du to get directory size
            result = subprocess.run(
                ["du", "-sb", str(path)], capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                size_bytes = int(result.stdout.split()[0])
                size_gb = size_bytes / (1024**3)

                if self.path_restrictions and self.path_restrictions.enabled:
                    if size_gb > self.path_restrictions.max_size_gb:
                        return (
                            size_gb,
                            False,
                            f"Directory size ({size_gb:.2f} GB) exceeds limit ({self.path_restrictions.max_size_gb} GB)",
                        )

                return size_gb, True, ""
            else:
                logger.warning(f"Failed to get directory size: {result.stderr}")
                return 0, True, ""  # Allow sync if we can't determine size
        except Exception as e:
            logger.warning(f"Error checking directory size: {e}")
            return 0, True, ""  # Allow sync if we can't determine size

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
        # Validate path restrictions
        is_valid, error_msg = self._validate_path(self.source_dir)
        if not is_valid:
            logger.error(f"Path validation failed: {error_msg}")
            raise ValueError(f"Path validation failed: {error_msg}")

        # Check directory size
        size_gb, is_valid, error_msg = self._check_directory_size(self.source_dir)
        if not is_valid:
            logger.error(f"Directory size check failed: {error_msg}")
            raise ValueError(f"Directory size check failed: {error_msg}")
        elif size_gb > 0:
            logger.info(f"Directory size: {size_gb:.2f} GB")

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

                exclude_args.extend(["--filter", f"merge {temp_gitignore_path}"])
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

        # First ensure the remote directory exists
        try:
            conn.run(f"mkdir -p {target_dir}")
            logger.debug(f"Created remote directory: {target_dir}")
        except Exception as e:
            logger.warning(f"Failed to create remote directory {target_dir}: {e}")

        try:
            # Use subprocess to run rsync locally
            # Build command based on authentication method
            if slurm_host.host.password:
                # Use sshpass with environment variable for better security
                env = os.environ.copy()
                env["SSHPASS"] = slurm_host.host.password
                rsync_cmd = (
                    ["sshpass", "-e", "rsync", "-avz"]
                    + exclude_args
                    + [f"{self.source_dir}/", target]
                )
                logger.debug("Running rsync with password authentication")
                result = subprocess.run(rsync_cmd, env=env, capture_output=False)
            else:
                # Use rsync directly for key-based auth
                rsync_cmd = (
                    ["rsync", "-avz"] + exclude_args + [f"{self.source_dir}/", target]
                )
                logger.debug(f"Running rsync command: {' '.join(rsync_cmd)}")
                result = subprocess.run(rsync_cmd, capture_output=False)

            if result.returncode == 0:
                logger.info(f"Successfully synced to {slurm_host.host.hostname}")
                return True
            else:
                logger.warning(f"Rsync failed with exit code {result.returncode}")
                return False
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
