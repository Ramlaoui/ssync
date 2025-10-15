"""SSH connection wrapper with Fabric-compatible API."""

from typing import Any, Optional

from ..utils.logging import setup_logger
from .native import NativeSSH, SSHResult

logger = setup_logger(__name__)


class _CDContext:
    """Context manager for cd command compatibility."""

    def __init__(self, connection, path):
        self.connection = connection
        self.path = path
        self.original_run = None

    def __enter__(self):
        """Enter context - wrap run() to prepend cd."""
        self.original_run = self.connection.run
        path = self.path

        def run_with_cd(command, **kwargs):
            # Prepend cd to the command
            cd_command = f"cd {path} && {command}"
            return self.original_run(cd_command, **kwargs)

        self.connection.run = run_with_cd
        return self

    def __exit__(self, *args):
        """Exit context - restore original run()."""
        if self.original_run:
            self.connection.run = self.original_run


class SSHCommandResult:
    """Result object for SSH command execution."""

    def __init__(self, ssh_result: SSHResult):
        self.stdout = ssh_result.stdout
        self.stderr = ssh_result.stderr
        self.exited = ssh_result.return_code
        self.ok = ssh_result.success
        self.return_code = ssh_result.return_code

    def __str__(self):
        return self.stdout


class SSHConnection:
    """SSH connection with Fabric-compatible API."""

    def __init__(self, host_config: Any, host_id: str):
        """Initialize with host configuration.

        Args:
            host_config: SSH config (string alias or dict)
            host_id: Unique identifier for this host
        """
        self.host_config = host_config
        self.host_id = host_id

        # Extract hostname for compatibility
        if isinstance(host_config, str):
            # SSH alias
            self.host = host_config
        elif isinstance(host_config, dict):
            # Dictionary config
            self.host = host_config.get(
                "hostname", host_id.split("@")[-1].split(":")[0]
            )
        else:
            # Fallback to parsing host_id
            self.host = host_id.split("@")[-1].split(":")[0]

    def run(
        self,
        command: str,
        hide: bool = True,
        warn: bool = True,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> SSHCommandResult:
        """Run command matching Fabric's API.

        Args:
            command: Command to execute
            hide: Whether to hide output (ignored)
            warn: Whether to treat failures as warnings
            timeout: Command timeout in seconds
            **kwargs: Other arguments (ignored)

        Returns:
            Fabric-compatible result
        """
        # For synchronous API, we need to block but commands can still
        # run in parallel through the same ControlMaster socket
        try:
            # Use subprocess directly for true parallelism
            import subprocess

            # Check if this host needs password auth
            password = None
            if isinstance(self.host_config, dict):
                connect_kwargs = self.host_config.get("connect_kwargs", {})
                password = connect_kwargs.get("password")

            # For password auth, skip ControlMaster and use direct connection
            if password:
                # Direct connection with sshpass
                ssh_cmd = ["sshpass", "-p", password, "ssh"]

                # Add hostname
                if isinstance(self.host_config, str):
                    ssh_cmd.append(self.host_config)
                else:
                    hostname = self.host_config.get(
                        "hostname", self.host_config.get("host")
                    )
                    ssh_cmd.append(hostname)
            else:
                # Use ControlMaster for key-based auth
                control_path = NativeSSH.ensure_control_master(
                    self.host_config, self.host_id
                )

                if control_path:
                    # Use the control socket
                    ssh_cmd = ["ssh", "-o", f"ControlPath={control_path}"]

                    # Add hostname
                    if isinstance(self.host_config, str):
                        ssh_cmd.append(self.host_config)
                    else:
                        hostname = self.host_config.get(
                            "hostname", self.host_config.get("host")
                        )
                        if "user" in self.host_config and "." in hostname:
                            ssh_cmd.append(f"{self.host_config['user']}@{hostname}")
                        else:
                            ssh_cmd.append(hostname)
                else:
                    # Fallback without ControlMaster
                    ssh_cmd = NativeSSH._build_direct_ssh_command(self.host_config)

            # Add command
            ssh_cmd.append(command)

            # Run with subprocess (allows true parallelism)
            try:
                # Capture as bytes first to handle non-UTF-8 output
                result = subprocess.run(
                    ssh_cmd, capture_output=True, timeout=timeout or 120
                )
            except subprocess.TimeoutExpired:
                logger.debug(f"Command timed out after {timeout} seconds")
                return SSHCommandResult(
                    SSHResult(
                        success=False,
                        stdout="",
                        stderr=f"Command timed out after {timeout} seconds",
                        return_code=124,
                    )
                )

            # Try to decode the output, handling encoding errors gracefully
            try:
                stdout = result.stdout.decode("utf-8")
            except UnicodeDecodeError:
                # Try with errors='replace' to replace invalid characters
                logger.debug(
                    "UTF-8 decode error in stdout, using replacement characters"
                )
                stdout = result.stdout.decode("utf-8", errors="replace")

            try:
                stderr = result.stderr.decode("utf-8")
            except UnicodeDecodeError:
                # Try with errors='replace' to replace invalid characters
                logger.debug(
                    "UTF-8 decode error in stderr, using replacement characters"
                )
                stderr = result.stderr.decode("utf-8", errors="replace")

            # Convert to our result format
            ssh_result = SSHResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=result.returncode,
            )

            # Convert to Fabric-compatible result
            result = SSHCommandResult(ssh_result)

            # Log errors if not warning mode
            if not result.ok and not warn:
                logger.error(f"Command failed: {result.stderr}")

            return result

        except Exception as e:
            logger.error(f"Error running command: {e}")
            # Return a failed result
            failed = SSHResult(success=False, stdout="", stderr=str(e), return_code=255)
            return SSHCommandResult(failed)

    def put(self, local, remote=None, preserve_mode=True, **kwargs):
        """Upload file matching Fabric's put() signature.

        Args:
            local: Local file path or file-like object
            remote: Remote destination path
            preserve_mode: Whether to preserve file mode (ignored)
            **kwargs: Other arguments (ignored)

        Returns:
            None (Fabric compatibility)
        """
        import os
        import tempfile

        # Handle file-like objects
        if hasattr(local, "read"):
            # It's a file-like object, write to temp file first
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
                tmp.write(local.read())
                local_path = tmp.name
            temp_file = local_path
        else:
            local_path = str(local)
            temp_file = None

        try:
            # Check if this host needs password auth
            password = None
            if isinstance(self.host_config, dict):
                connect_kwargs = self.host_config.get("connect_kwargs", {})
                password = connect_kwargs.get("password")

            # Determine the host string for scp
            if isinstance(self.host_config, str):
                # SSH alias - use it directly
                host_for_scp = self.host_config
            else:
                # Dictionary config - build host string
                host_for_scp = self.host_config.get(
                    "hostname", self.host_config.get("host")
                )
                if "user" in self.host_config:
                    host_for_scp = f"{self.host_config['user']}@{host_for_scp}"

            # For password auth, use sshpass
            if password:
                scp_cmd = [
                    "sshpass",
                    "-p",
                    password,
                    "scp",
                    local_path,
                    f"{host_for_scp}:{remote}",
                ]
            else:
                # Use scp through the control master for key-based auth
                control_path = NativeSSH.ensure_control_master(
                    self.host_config, self.host_id
                )

                if control_path:
                    scp_cmd = [
                        "scp",
                        "-o",
                        f"ControlPath={control_path}",
                        local_path,
                        f"{host_for_scp}:{remote}",
                    ]
                else:
                    # Fallback to direct scp
                    scp_cmd = ["scp", local_path, f"{host_for_scp}:{remote}"]

            # Run scp locally, not through SSH
            import subprocess

            result = subprocess.run(scp_cmd, capture_output=True)
            if result.returncode != 0:
                # Decode stderr for error message
                try:
                    stderr = result.stderr.decode("utf-8")
                except UnicodeDecodeError:
                    stderr = result.stderr.decode("utf-8", errors="replace")
                raise Exception(f"Failed to upload file: {stderr}")
        finally:
            # Clean up temp file if we created one
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)

    def get(self, remote, local=None, preserve_mode=True, **kwargs):
        """Download file matching Fabric's get() signature.

        Args:
            remote: Remote file path
            local: Local destination path or file-like object
            preserve_mode: Whether to preserve file mode (ignored)
            **kwargs: Other arguments (ignored)

        Returns:
            None (Fabric compatibility)
        """
        import os
        import tempfile

        # Determine local path
        if hasattr(local, "write"):
            # It's a file-like object, use temp file
            temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False)
            local_path = temp_file.name
            temp_file.close()
            is_file_obj = True
        else:
            local_path = str(local) if local else os.path.basename(remote)
            is_file_obj = False

        try:
            # Check if this host needs password auth
            password = None
            if isinstance(self.host_config, dict):
                connect_kwargs = self.host_config.get("connect_kwargs", {})
                password = connect_kwargs.get("password")

            # Determine the host string for scp
            if isinstance(self.host_config, str):
                # SSH alias - use it directly
                host_for_scp = self.host_config
            else:
                # Dictionary config - build host string
                host_for_scp = self.host_config.get(
                    "hostname", self.host_config.get("host")
                )
                if "user" in self.host_config:
                    host_for_scp = f"{self.host_config['user']}@{host_for_scp}"

            # For password auth, use sshpass
            if password:
                scp_cmd = [
                    "sshpass",
                    "-p",
                    password,
                    "scp",
                    f"{host_for_scp}:{remote}",
                    local_path,
                ]
            else:
                # Use scp through the control master for key-based auth
                control_path = NativeSSH.ensure_control_master(
                    self.host_config, self.host_id
                )

                if control_path:
                    scp_cmd = [
                        "scp",
                        "-o",
                        f"ControlPath={control_path}",
                        f"{host_for_scp}:{remote}",
                        local_path,
                    ]
                else:
                    # Fallback to direct scp
                    scp_cmd = ["scp", f"{host_for_scp}:{remote}", local_path]

            # Run scp locally, not through SSH
            import subprocess

            result = subprocess.run(scp_cmd, capture_output=True)
            if result.returncode != 0:
                # Decode stderr for error message
                try:
                    stderr = result.stderr.decode("utf-8")
                except UnicodeDecodeError:
                    stderr = result.stderr.decode("utf-8", errors="replace")
                raise Exception(f"Failed to download file: {stderr}")

            # If it was a file object, write the content back
            if is_file_obj:
                with open(local_path, "rb") as f:
                    local.write(f.read())
                os.unlink(local_path)
        except Exception:
            # Clean up temp file on error
            if is_file_obj and os.path.exists(local_path):
                os.unlink(local_path)
            raise

    def cd(self, path):
        """Context manager for changing directory.

        Args:
            path: Directory to change to

        Returns:
            Context manager that prepends cd to commands
        """
        return _CDContext(self, path)

    def close(self):
        """Close connection (doesn't actually close ControlMaster)."""
        # We don't close the ControlMaster here because it's shared
        # It will be closed when the process exits or explicitly cleaned up
        logger.debug(f"Close called for {self.host_id} (ControlMaster remains active)")

    @classmethod
    def cleanup_all(cls):
        """Clean up all ControlMaster connections."""
        NativeSSH.cleanup_all()
