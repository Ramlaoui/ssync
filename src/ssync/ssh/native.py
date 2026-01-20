"""Simplified native SSH implementation using ControlMaster correctly.

This implementation creates ONE ControlMaster connection per host and
allows unlimited parallel SSH commands through that single connection.
"""

import asyncio
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class SSHResult:
    """Result from SSH command execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int


class NativeSSH:
    """Native SSH implementation using ControlMaster - one connection per host."""

    # Class-level tracking of established control masters
    _control_masters: Dict[str, str] = {}  # host_id -> control_path

    @classmethod
    def get_control_path(cls, host_id: str) -> str:
        """Get control socket path for a host.

        Args:
            host_id: Unique identifier for the host

        Returns:
            Path to control socket
        """
        # Use hash to avoid issues with special chars
        host_hash = hashlib.md5(host_id.encode()).hexdigest()[:8]

        # Use XDG runtime dir if available
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        control_dir = Path(runtime_dir) / "ssync_ssh"
        control_dir.mkdir(parents=True, exist_ok=True)

        return str(control_dir / f"control_{host_hash}.sock")

    # Class-level tracking of failed connection attempts to avoid repeated failures
    _failed_hosts: Dict[str, float] = {}  # host_id -> last_failed_time
    _FAILURE_BACKOFF = 60.0  # Don't retry failed hosts for 60 seconds

    @classmethod
    def ensure_control_master(
        cls, host_config: Union[str, Dict], host_id: str
    ) -> Optional[str]:
        """Ensure ControlMaster is established for a host.

        Args:
            host_config: SSH config (string alias or dict)
            host_id: Unique identifier for the host

        Returns:
            Control socket path if successful, None otherwise
        """
        import time

        # Check if this host recently failed - if so, skip retry for backoff period
        if host_id in cls._failed_hosts:
            time_since_failure = time.time() - cls._failed_hosts[host_id]
            if time_since_failure < cls._FAILURE_BACKOFF:
                logger.debug(
                    f"Skipping ControlMaster retry for {host_id} "
                    f"(failed {time_since_failure:.1f}s ago, backoff={cls._FAILURE_BACKOFF}s)"
                )
                return None

        # Get control path
        control_path = cls.get_control_path(host_id)

        # Check if socket already exists on disk (from previous session)
        if Path(control_path).exists():
            # Verify it's still valid
            if cls._check_control_master(control_path, host_config):
                # Existing ControlMaster is valid, use it!
                cls._control_masters[host_id] = control_path
                # Clear failure record on success
                cls._failed_hosts.pop(host_id, None)
                logger.debug(f"Found existing ControlMaster for {host_id}")
                return control_path
            else:
                # Socket exists but is stale, remove it
                try:
                    Path(control_path).unlink()
                    logger.debug(f"Removed stale socket for {host_id}")
                except:
                    pass

        # Check if we already tracked this control master
        if host_id in cls._control_masters:
            control_path = cls._control_masters[host_id]
            # Verify it's still valid
            if cls._check_control_master(control_path, host_config):
                return control_path
            else:
                # Clean up stale entry
                del cls._control_masters[host_id]

        # Build SSH command for master
        ssh_cmd = ["ssh"]

        # Handle different config types
        if isinstance(host_config, str):
            # SSH config alias
            ssh_cmd.append(host_config)
        elif isinstance(host_config, dict):
            # Build from dict
            hostname = host_config.get("hostname", host_config.get("host"))
            if not hostname:
                logger.error("No hostname in config")
                return None

            # Check if it's an SSH alias (no dots, no user)
            if "." not in hostname and "user" not in host_config:
                ssh_cmd.append(hostname)
            else:
                # Build user@host
                if "user" in host_config:
                    ssh_cmd.append(f"{host_config['user']}@{hostname}")
                else:
                    ssh_cmd.append(hostname)

                # Add port if needed
                if "port" in host_config and host_config["port"] != 22:
                    ssh_cmd.extend(["-p", str(host_config["port"])])

        # Add ControlMaster options
        # Override any existing ControlMaster settings from SSH config
        ssh_cmd.extend(
            [
                "-o",
                "ControlMaster=yes",  # Override SSH config
                "-o",
                f"ControlPath={control_path}",  # Our socket path
                "-o",
                "ControlPersist=600",  # Keep alive for 10 minutes
                "-o",
                "ServerAliveInterval=60",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "ConnectTimeout=5",  # Reduced from 10s to 5s for faster failure
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-N",  # No command
                "-f",  # Background
            ]
        )

        # Handle password if present
        password = None
        if isinstance(host_config, dict):
            connect_kwargs = host_config.get("connect_kwargs", {})
            password = connect_kwargs.get("password")

        if password:
            # Check for sshpass
            if (
                subprocess.run(["which", "sshpass"], capture_output=True).returncode
                == 0
            ):
                ssh_cmd = ["sshpass", "-p", password] + ssh_cmd
                logger.debug(f"Using sshpass for {host_id}")
            else:
                logger.warning(f"Password auth requires sshpass for {host_id}")
                # Try anyway - maybe SSH askpass is configured
                pass

        logger.debug(f"Establishing ControlMaster for {host_id}")

        try:
            # For debugging, log the command (without password)
            safe_cmd = [c if not password or c != password else "***" for c in ssh_cmd]
            logger.debug(f"SSH command: {' '.join(safe_cmd[:10])}...")

            # Start control master with shorter timeout for faster failure
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=5)

            # Wait a bit for socket to be created
            import time

            time.sleep(1)

            # Check if socket was created
            if Path(control_path).exists():
                cls._control_masters[host_id] = control_path
                # Clear failure record on success
                cls._failed_hosts.pop(host_id, None)
                logger.debug(f"ControlMaster established for {host_id}")
                return control_path
            else:
                # Record failure with timestamp for backoff
                cls._failed_hosts[host_id] = time.time()
                if result.stderr:
                    logger.error(f"Failed to establish ControlMaster for {host_id}: {result.stderr}")
                if result.stdout:
                    logger.debug(f"SSH stdout: {result.stdout}")
                return None

        except subprocess.TimeoutExpired:
            # Record failure with timestamp for backoff
            import time
            cls._failed_hosts[host_id] = time.time()
            logger.error(f"Timeout establishing ControlMaster for {host_id}")
            return None
        except Exception as e:
            # Record failure with timestamp for backoff
            import time
            cls._failed_hosts[host_id] = time.time()
            logger.error(f"Error establishing ControlMaster for {host_id}: {e}")
            return None

    @classmethod
    def _check_control_master(
        cls, control_path: str, host_config: Union[str, Dict]
    ) -> bool:
        """Check if a ControlMaster socket is still valid.

        Args:
            control_path: Path to control socket
            host_config: SSH config

        Returns:
            True if socket is valid and responsive
        """
        if not Path(control_path).exists():
            return False

        # Get hostname for check command
        if isinstance(host_config, str):
            hostname = host_config
        else:
            hostname = host_config.get("hostname", host_config.get("host", ""))
            if "user" in host_config and "." in hostname:
                hostname = f"{host_config['user']}@{hostname}"

        # Check if control master is responsive
        check_cmd = ["ssh", "-S", control_path, "-O", "check", hostname]

        try:
            result = subprocess.run(check_cmd, capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    @classmethod
    async def run_command(
        cls,
        host_config: Union[str, Dict],
        host_id: str,
        command: str,
        timeout: Optional[float] = None,
    ) -> SSHResult:
        """Run a command through SSH.

        Args:
            host_config: SSH config (string alias or dict)
            host_id: Unique identifier for the host
            command: Command to execute
            timeout: Optional timeout in seconds

        Returns:
            SSHResult with command output
        """
        # Ensure control master exists
        control_path = cls.ensure_control_master(host_config, host_id)

        if not control_path:
            # Fallback to direct SSH without ControlMaster
            logger.warning(f"Running without ControlMaster for {host_id}")
            ssh_cmd = cls._build_direct_ssh_command(host_config)
        else:
            # Use control master socket
            ssh_cmd = ["ssh", "-S", control_path]

            # Add hostname
            if isinstance(host_config, str):
                ssh_cmd.append(host_config)
            else:
                hostname = host_config.get("hostname", host_config.get("host"))
                if "user" in host_config and "." in hostname:
                    ssh_cmd.append(f"{host_config['user']}@{hostname}")
                else:
                    ssh_cmd.append(hostname)

        # Add the command
        ssh_cmd.append(command)

        # Run command asynchronously
        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Wait with timeout
            if timeout:
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return SSHResult(
                        success=False,
                        stdout="",
                        stderr=f"Command timed out after {timeout} seconds",
                        return_code=124,
                    )
            else:
                stdout, stderr = await process.communicate()

            return SSHResult(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                return_code=process.returncode,
            )

        except Exception as e:
            logger.error(f"Error running command: {e}")
            return SSHResult(success=False, stdout="", stderr=str(e), return_code=255)

    @classmethod
    def _build_direct_ssh_command(cls, host_config: Union[str, Dict]) -> list:
        """Build SSH command without ControlMaster.

        Args:
            host_config: SSH config

        Returns:
            SSH command arguments
        """
        ssh_cmd = ["ssh"]

        if isinstance(host_config, str):
            ssh_cmd.append(host_config)
        else:
            hostname = host_config.get("hostname", host_config.get("host"))
            if "user" in host_config:
                ssh_cmd.append(f"{host_config['user']}@{hostname}")
            else:
                ssh_cmd.append(hostname)

            if "port" in host_config and host_config["port"] != 22:
                ssh_cmd.extend(["-p", str(host_config["port"])])

        ssh_cmd.extend(
            ["-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new"]  # Faster timeout
        )

        return ssh_cmd

    @classmethod
    def cleanup_control_master(cls, host_id: str):
        """Clean up ControlMaster for a host.

        Args:
            host_id: Host identifier
        """
        if host_id in cls._control_masters:
            control_path = cls._control_masters[host_id]

            # Send exit command
            try:
                # We need the hostname for the exit command
                exit_cmd = ["ssh", "-S", control_path, "-O", "exit", "dummy"]
                subprocess.run(exit_cmd, capture_output=True, timeout=5)
            except:
                pass

            # Remove socket file
            try:
                Path(control_path).unlink()
            except:
                pass

            del cls._control_masters[host_id]
            logger.info(f"Cleaned up ControlMaster for {host_id}")

    @classmethod
    def cleanup_all(cls):
        """Clean up all ControlMaster connections."""
        for host_id in list(cls._control_masters.keys()):
            cls.cleanup_control_master(host_id)
