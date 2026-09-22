"""Simplified native SSH implementation using ControlMaster correctly.

This implementation creates ONE ControlMaster connection per host and
allows unlimited parallel SSH commands through that single connection.
"""

import asyncio
import fcntl
import hashlib
import os
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Optional, Union

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class SSHResult:
    """Result from SSH command execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int


class ControlMasterUnavailableError(RuntimeError):
    """Raised when a password-backed host has no reusable SSH master."""

    def __init__(self, host_id: str):
        super().__init__(
            f"ControlMaster unavailable for password-authenticated host {host_id}"
        )


class NativeSSH:
    """Native SSH implementation using ControlMaster - one connection per host."""

    # Class-level tracking of established control masters
    _control_masters: Dict[str, str] = {}  # host_id -> control_path
    _master_processes: Dict[str, subprocess.Popen] = {}
    _host_locks: Dict[str, threading.Lock] = {}
    _host_locks_guard = threading.Lock()
    _command_semaphores: Dict[str, threading.BoundedSemaphore] = {}
    _command_semaphores_guard = threading.Lock()

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
    _MASTER_START_TIMEOUT = 8.0
    _MASTER_HOLD_COMMAND = "exec cat >/dev/null"
    _MAX_COMMANDS_PER_HOST = 8
    _CONTROL_CLIENT_OPTIONS = (
        "-o",
        "ControlMaster=no",
        "-o",
        "BatchMode=yes",
        "-o",
        "ProxyCommand=false",
    )

    @classmethod
    def ensure_control_master(
        cls, host_config: Union[str, Dict], host_id: str
    ) -> Optional[str]:
        """Return one reusable SSH master socket for a host.

        Creation is serialized per host. The SSH process remains in the
        foreground with a harmless blocking remote command because some
        ProxyJump/password hosts close an idle ``ssh -N -f`` session before its
        socket can be reused.
        """
        control_path = cls.get_control_path(host_id)

        with cls._get_host_lock(host_id):
            existing = cls._reuse_control_master(host_config, host_id, control_path)
            if existing:
                return existing

            last_failure = cls._failed_hosts.get(host_id)
            if last_failure is not None:
                elapsed = time.monotonic() - last_failure
                if elapsed < cls._FAILURE_BACKOFF:
                    logger.debug(
                        "Skipping ControlMaster retry for %s for another %.1fs",
                        host_id,
                        cls._FAILURE_BACKOFF - elapsed,
                    )
                    return None

            try:
                with cls._control_creation_lock(control_path):
                    # Another ssync process may have created it while we waited.
                    existing = cls._reuse_control_master(
                        host_config, host_id, control_path
                    )
                    if existing:
                        return existing

                    cls._discard_local_master(host_id)
                    cls._remove_socket(control_path)
                    return cls._start_control_master(host_config, host_id, control_path)
            except OSError as exc:
                cls._record_failure(host_id)
                logger.error(
                    "Could not lock ControlMaster creation for %s: %s",
                    host_id,
                    exc,
                )
                return None

    @classmethod
    def _get_host_lock(cls, host_id: str) -> threading.Lock:
        with cls._host_locks_guard:
            return cls._host_locks.setdefault(host_id, threading.Lock())

    @classmethod
    @contextmanager
    def command_slot(cls, host_id: str) -> Iterator[None]:
        """Limit simultaneous sessions opened through one host connection."""
        with cls._command_semaphores_guard:
            semaphore = cls._command_semaphores.setdefault(
                host_id,
                threading.BoundedSemaphore(
                    cls._max_commands_for_host(host_id)
                ),
            )

        semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()

    @classmethod
    def _max_commands_for_host(cls, host_id: str) -> int:
        normalized_host_id = "".join(
            character if character.isalnum() else "_"
            for character in host_id.upper()
        )
        configured = os.getenv(
            f"SSYNC_MAX_COMMANDS_PER_HOST_{normalized_host_id}",
            os.getenv("SSYNC_MAX_COMMANDS_PER_HOST"),
        )
        if configured is None:
            return cls._MAX_COMMANDS_PER_HOST

        try:
            return max(1, int(configured))
        except ValueError:
            logger.warning(
                "Ignoring invalid SSH command limit %r for host %s",
                configured,
                host_id,
            )
            return cls._MAX_COMMANDS_PER_HOST

    @classmethod
    @contextmanager
    def _control_creation_lock(cls, control_path: str) -> Iterator[None]:
        lock_path = Path(f"{control_path}.lock")
        with lock_path.open("a") as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @classmethod
    def _reuse_control_master(
        cls,
        host_config: Union[str, Dict],
        host_id: str,
        control_path: str,
    ) -> Optional[str]:
        process = cls._master_processes.get(host_id)
        if (
            process is not None
            and process.poll() is None
            and Path(control_path).exists()
        ):
            cls._control_masters[host_id] = control_path
            cls._failed_hosts.pop(host_id, None)
            return control_path

        if not Path(control_path).exists():
            return None

        if cls._check_control_master(control_path, host_config):
            cls._control_masters[host_id] = control_path
            cls._failed_hosts.pop(host_id, None)
            return control_path

        cls._discard_local_master(host_id)
        cls._remove_socket(control_path)
        return None

    @classmethod
    def _start_control_master(
        cls,
        host_config: Union[str, Dict],
        host_id: str,
        control_path: str,
    ) -> Optional[str]:
        password = cls._get_password(host_config)
        if password and shutil.which("sshpass") is None:
            cls._record_failure(host_id)
            logger.error("Password auth requires sshpass for %s", host_id)
            return None

        ssh_cmd = cls._build_control_master_command(
            host_config, control_path, password=bool(password)
        )
        env = os.environ.copy()
        if password:
            env["SSHPASS"] = password

        logger.debug("Establishing supervised ControlMaster for %s", host_id)
        try:
            process = subprocess.Popen(
                ssh_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            cls._record_failure(host_id)
            logger.error("Could not start ControlMaster for %s: %s", host_id, exc)
            return None

        deadline = time.monotonic() + cls._MASTER_START_TIMEOUT
        while time.monotonic() < deadline:
            if Path(control_path).exists() and cls._check_control_master(
                control_path, host_config
            ):
                cls._master_processes[host_id] = process
                cls._control_masters[host_id] = control_path
                cls._failed_hosts.pop(host_id, None)
                logger.info("ControlMaster established for %s", host_id)
                return control_path

            if process.poll() is not None:
                break
            time.sleep(0.05)

        return_code = process.poll()
        cls._stop_process(process)
        cls._remove_socket(control_path)
        cls._record_failure(host_id)
        if return_code is None:
            logger.error(
                "ControlMaster for %s did not create a usable socket within %.0fs",
                host_id,
                cls._MASTER_START_TIMEOUT,
            )
        else:
            logger.error(
                "ControlMaster for %s exited before its socket was ready (code %s)",
                host_id,
                return_code,
            )
        return None

    @classmethod
    def _build_control_master_command(
        cls,
        host_config: Union[str, Dict],
        control_path: str,
        *,
        password: bool,
    ) -> list[str]:
        ssh_cmd = [
            "ssh",
            "-o",
            "ControlMaster=yes",
            "-o",
            f"ControlPath={control_path}",
            "-o",
            "ControlPersist=600",
            "-o",
            "ServerAliveInterval=60",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if isinstance(host_config, dict) and host_config.get("port", 22) != 22:
            ssh_cmd.extend(["-p", str(host_config["port"])])
        ssh_cmd.extend([cls._host_argument(host_config), cls._MASTER_HOLD_COMMAND])
        if password:
            ssh_cmd = ["sshpass", "-e", *ssh_cmd]
        return ssh_cmd

    @classmethod
    def control_ssh_prefix(cls, control_path: str) -> list[str]:
        """Build an SSH client that can only use an existing control socket.

        OpenSSH normally falls back to a direct connection when the socket
        disappears between validation and command startup. ``ProxyCommand=false``
        makes that fallback fail locally, while ``BatchMode=yes`` guarantees it
        can never display a password prompt.
        """
        return ["ssh", "-S", control_path, *cls._CONTROL_CLIENT_OPTIONS]

    @classmethod
    def control_scp_prefix(cls, control_path: str) -> list[str]:
        """Build an SCP client that can only use an existing control socket."""
        return [
            "scp",
            "-o",
            f"ControlPath={control_path}",
            *cls._CONTROL_CLIENT_OPTIONS,
        ]

    @staticmethod
    def _host_argument(host_config: Union[str, Dict]) -> str:
        if isinstance(host_config, str):
            return host_config
        hostname = host_config.get("hostname", host_config.get("host"))
        if not hostname:
            raise ValueError("No hostname in SSH config")
        if "user" in host_config:
            return f"{host_config['user']}@{hostname}"
        return hostname

    @staticmethod
    def _get_password(host_config: Union[str, Dict]) -> Optional[str]:
        if not isinstance(host_config, dict):
            return None
        return host_config.get("connect_kwargs", {}).get("password")

    @classmethod
    def _record_failure(cls, host_id: str) -> None:
        cls._failed_hosts[host_id] = time.monotonic()

    @staticmethod
    def _stop_process(process: subprocess.Popen) -> None:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    process.kill()
                process.wait(timeout=2)

    @classmethod
    def _discard_local_master(cls, host_id: str) -> None:
        process = cls._master_processes.pop(host_id, None)
        if process is not None:
            cls._stop_process(process)
        cls._control_masters.pop(host_id, None)

    @staticmethod
    def _remove_socket(control_path: str) -> None:
        try:
            Path(control_path).unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.debug(
                "Could not remove stale control socket %s: %s", control_path, exc
            )

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

        # Check if control master is responsive
        check_cmd = [
            "ssh",
            "-S",
            control_path,
            "-O",
            "check",
            cls._host_argument(host_config),
        ]

        try:
            result = subprocess.run(check_cmd, capture_output=True, timeout=5)
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
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
            if cls._get_password(host_config):
                error = ControlMasterUnavailableError(host_id)
                return SSHResult(
                    success=False,
                    stdout="",
                    stderr=str(error),
                    return_code=255,
                )
            # Fallback to direct SSH without ControlMaster
            logger.warning(f"Running without ControlMaster for {host_id}")
            ssh_cmd = cls._build_direct_ssh_command(host_config)
        else:
            # Use control master socket
            ssh_cmd = [
                *cls.control_ssh_prefix(control_path),
                cls._host_argument(host_config),
            ]

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
        ssh_cmd = [
            "ssh",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if isinstance(host_config, dict) and host_config.get("port", 22) != 22:
            ssh_cmd.extend(["-p", str(host_config["port"])])
        ssh_cmd.append(cls._host_argument(host_config))

        return ssh_cmd

    @classmethod
    def cleanup_control_master(cls, host_id: str):
        """Clean up ControlMaster for a host.

        Args:
            host_id: Host identifier
        """
        with cls._get_host_lock(host_id):
            control_path = cls._control_masters.get(host_id)
            if control_path and Path(control_path).exists():
                try:
                    exit_cmd = ["ssh", "-S", control_path, "-O", "exit", "dummy"]
                    subprocess.run(exit_cmd, capture_output=True, timeout=5)
                except (subprocess.SubprocessError, OSError):
                    pass

            cls._discard_local_master(host_id)
            if control_path:
                cls._remove_socket(control_path)
            cls._failed_hosts.pop(host_id, None)
            logger.info("Cleaned up ControlMaster for %s", host_id)

    @classmethod
    def cleanup_all(cls):
        """Clean up all ControlMaster connections."""
        host_ids = set(cls._control_masters) | set(cls._master_processes)
        for host_id in list(host_ids):
            cls.cleanup_control_master(host_id)
