"""SSH connection wrapper with Fabric-compatible API."""

from pathlib import Path
from typing import Any, Optional

from ..utils.logging import setup_logger
from .native import ControlMasterUnavailableError, NativeSSH, SSHResult

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

    SCP_TIMEOUT_SECONDS = 120

    def __init__(
        self,
        host_config: Any,
        host_id: str,
        *,
        command_timeout: float = 120,
    ):
        """Initialize with host configuration.

        Args:
            host_config: SSH config (string alias or dict)
            host_id: Unique identifier for this host
            command_timeout: Default timeout in seconds for remote commands
        """
        self.host_config = host_config
        self.host_id = host_id
        self.command_timeout = command_timeout

        # Extract hostname for compatibility
        if isinstance(host_config, str):
            # SSH alias
            self.host = host_config
            self.user = None
        elif isinstance(host_config, dict):
            # Dictionary config
            self.host = host_config.get(
                "hostname", host_id.split("@")[-1].split(":")[0]
            )
            # Extract username if provided in config
            self.user = host_config.get("user")
        else:
            # Fallback to parsing host_id
            self.host = host_id.split("@")[-1].split(":")[0]
            self.user = None

    def _get_password(self) -> Optional[str]:
        if not isinstance(self.host_config, dict):
            return None
        connect_kwargs = self.host_config.get("connect_kwargs", {})
        return connect_kwargs.get("password")

    def _host_argument(self) -> str:
        if isinstance(self.host_config, str):
            return self.host_config

        hostname = self.host_config.get("hostname", self.host_config.get("host"))
        if "user" in self.host_config:
            return f"{self.host_config['user']}@{hostname}"
        return hostname

    def _build_ssh_command(self) -> list[str]:
        control_path = NativeSSH.ensure_control_master(self.host_config, self.host_id)
        if control_path:
            return [
                *NativeSSH.control_ssh_prefix(control_path),
                self._host_argument(),
            ]

        password = self._get_password()
        if password:
            raise ControlMasterUnavailableError(self.host_id)

        return NativeSSH._build_direct_ssh_command(self.host_config)

    def _build_scp_command(
        self, *, upload: bool, local_path: str, remote: str
    ) -> list[str]:
        host_for_scp = self._host_argument()
        remote_target = f"{host_for_scp}:{remote}"
        control_path = NativeSSH.ensure_control_master(self.host_config, self.host_id)

        if control_path:
            base_cmd = NativeSSH.control_scp_prefix(control_path)
        else:
            password = self._get_password()
            if password:
                raise ControlMasterUnavailableError(self.host_id)
            base_cmd = ["scp"]

        if upload:
            return base_cmd + [local_path, remote_target]
        return base_cmd + [remote_target, local_path]

    @staticmethod
    def _decode_output_chunk(chunk: bytes, stream_name: str) -> str:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            logger.debug(
                "UTF-8 decode error in %s, using replacement characters",
                stream_name,
            )
            return chunk.decode("utf-8", errors="replace")

    @classmethod
    def _run_streaming_command(
        cls,
        ssh_cmd: list[str],
        *,
        timeout: Optional[float],
        out_stream: Any = None,
        err_stream: Any = None,
    ):
        import codecs
        import os
        import select
        import signal
        import subprocess
        import threading

        capture_limit = 1024 * 1024
        effective_timeout = timeout if timeout is not None else 120

        def new_capture() -> dict[str, Any]:
            return {"tail": bytearray(), "total": 0, "lock": threading.Lock()}

        stdout_capture = new_capture()
        stderr_capture = new_capture()

        process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        def retain(capture: dict[str, Any], chunk: bytes) -> None:
            if not chunk:
                return
            with capture["lock"]:
                capture["total"] += len(chunk)
                capture["tail"].extend(chunk)
                if len(capture["tail"]) > capture_limit:
                    del capture["tail"][:-capture_limit]

        def finalize(
            capture: dict[str, Any], stream_name: str, suffix: bytes = b""
        ) -> bytes:
            with capture["lock"]:
                total = capture["total"]
                tail = bytes(capture["tail"])
            if total + len(suffix) <= capture_limit:
                return tail + suffix

            marker = (
                f"\n[... {stream_name} truncated; showing the latest output "
                f"({capture_limit:,} bytes) ...]\n"
            ).encode("utf-8")
            tail_limit = max(0, capture_limit - len(marker) - len(suffix))
            return marker + tail[-tail_limit:] + suffix[-capture_limit:]

        def terminate_group(sig: signal.Signals) -> None:
            try:
                os.killpg(process.pid, sig)
            except (OSError, ProcessLookupError):
                try:
                    process.send_signal(sig)
                except (OSError, ProcessLookupError):
                    pass

        def close_pipe(pipe) -> None:
            if pipe is None:
                return
            try:
                pipe.close()
            except (OSError, ValueError):
                pass

        def pump(pipe, capture: dict[str, Any], stream, stream_name: str):
            if pipe is None:
                return
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            pipe_fd = pipe.fileno()
            os.set_blocking(pipe_fd, False)
            try:
                while True:
                    readable, _, _ = select.select([pipe_fd], [], [], 0.1)
                    if not readable:
                        continue
                    try:
                        chunk = os.read(pipe_fd, 64 * 1024)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        break
                    retain(capture, chunk)
                    if stream is not None:
                        decoded = decoder.decode(chunk)
                        if decoded:
                            stream.write(decoded)
                if stream is not None:
                    decoded = decoder.decode(b"", final=True)
                    if decoded:
                        stream.write(decoded)
            except (OSError, ValueError):
                # The timeout path may close a pipe to unblock a reader that
                # inherited it from a descendant process.
                pass
            finally:
                if stream is not None:
                    if hasattr(stream, "finish"):
                        stream.finish()
                    elif hasattr(stream, "flush"):
                        stream.flush()
                pipe.close()

        stdout_thread = threading.Thread(
            target=pump,
            args=(process.stdout, stdout_capture, out_stream, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=pump,
            args=(process.stderr, stderr_capture, err_stream, "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        try:
            return_code = process.wait(timeout=effective_timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out after %s seconds", effective_timeout)
            timed_out = True
            terminate_group(signal.SIGTERM)
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                terminate_group(signal.SIGKILL)
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
            return_code = 124

        # A child can inherit stdout/stderr and keep a pipe open after the
        # parent exits. Never let cleanup turn a command timeout into a second
        # unbounded wait; closing the descriptors unblocks the daemon pumps.
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            terminate_group(signal.SIGTERM)
            stdout_thread.join(timeout=0.5)
            stderr_thread.join(timeout=0.5)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            terminate_group(signal.SIGKILL)
            stdout_thread.join(timeout=0.5)
            stderr_thread.join(timeout=0.5)
        if stdout_thread.is_alive():
            close_pipe(process.stdout)
        if stderr_thread.is_alive():
            close_pipe(process.stderr)
        stdout_thread.join(timeout=0.25)
        stderr_thread.join(timeout=0.25)

        stdout = finalize(stdout_capture, "stdout")
        if timed_out:
            with stderr_capture["lock"]:
                stderr_has_output = stderr_capture["total"] > 0
            timeout_message = (
                b"\n" if stderr_has_output else b""
            ) + f"Command timed out after {effective_timeout} seconds".encode("utf-8")
        else:
            timeout_message = b""
        stderr = finalize(stderr_capture, "stderr", suffix=timeout_message)

        return subprocess.CompletedProcess(
            ssh_cmd,
            return_code,
            stdout=stdout,
            stderr=stderr,
        )

    def run(
        self,
        command: str,
        hide: bool = True,
        warn: bool = True,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> SSHCommandResult:
        """Run one command without exceeding the host's SSH session limit."""
        with NativeSSH.command_slot(self.host_id):
            return self._run_unthrottled(
                command,
                hide=hide,
                warn=warn,
                timeout=timeout,
                **kwargs,
            )

    def _run_unthrottled(
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
            **kwargs: Other arguments. ``out_stream`` and ``err_stream`` are honored
                for live command output.

        Returns:
            Fabric-compatible result
        """
        _ = hide

        # For synchronous API, we need to block but commands can still
        # run in parallel through the same ControlMaster socket
        try:
            # Use subprocess directly for true parallelism
            import subprocess

            out_stream = kwargs.get("out_stream")
            err_stream = kwargs.get("err_stream")
            effective_timeout = timeout if timeout is not None else self.command_timeout

            # Add command
            ssh_cmd = self._build_ssh_command()
            ssh_cmd.append(command)

            if out_stream is not None or err_stream is not None:
                result = self._run_streaming_command(
                    ssh_cmd,
                    timeout=effective_timeout,
                    out_stream=out_stream,
                    err_stream=err_stream,
                )
            else:
                # Run with subprocess (allows true parallelism)
                try:
                    # Capture as bytes first to handle non-UTF-8 output
                    result = subprocess.run(
                        ssh_cmd, capture_output=True, timeout=effective_timeout
                    )
                except subprocess.TimeoutExpired:
                    logger.exception(
                        "Command timed out after %s seconds", effective_timeout
                    )
                    return SSHCommandResult(
                        SSHResult(
                            success=False,
                            stdout="",
                            stderr=f"Command timed out after {effective_timeout} seconds",
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

        except ControlMasterUnavailableError as e:
            logger.debug("%s", e)
            failed = SSHResult(success=False, stdout="", stderr=str(e), return_code=255)
            return SSHCommandResult(failed)
        except Exception as e:
            logger.error(f"Error running command: {e}")
            # Return a failed result
            failed = SSHResult(success=False, stdout="", stderr=str(e), return_code=255)
            return SSHCommandResult(failed)

    def is_healthy(self, timeout: Optional[float] = None) -> bool:
        """Check whether this connection can be reused safely.

        For key-based hosts, prefer checking the existing ControlMaster socket
        instead of opening a remote session just to validate the connection.
        For password-based hosts, fall back to a lightweight remote command.
        """
        password = None
        if isinstance(self.host_config, dict):
            connect_kwargs = self.host_config.get("connect_kwargs", {})
            password = connect_kwargs.get("password")

        if not password:
            control_path = NativeSSH.get_control_path(self.host_id)
            return Path(control_path).exists() and NativeSSH._check_control_master(
                control_path, self.host_config
            )

        result = self.run("echo 'health check'", hide=True, timeout=timeout or 5)
        return result.ok

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
        _ = preserve_mode

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
            with NativeSSH.command_slot(self.host_id):
                scp_cmd = self._build_scp_command(
                    upload=True, local_path=local_path, remote=remote
                )
                self._run_scp_command(scp_cmd, direction="upload")
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
        _ = preserve_mode

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
            with NativeSSH.command_slot(self.host_id):
                scp_cmd = self._build_scp_command(
                    upload=False, local_path=local_path, remote=remote
                )
                self._run_scp_command(scp_cmd, direction="download")

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

    def _run_scp_command(self, scp_cmd: list[str], direction: str) -> None:
        """Run an scp command with timeout and one retry after socket cleanup."""
        import subprocess

        last_error = None
        for attempt in range(2):
            try:
                result = subprocess.run(
                    scp_cmd,
                    capture_output=True,
                    timeout=self.SCP_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                last_error = f"SCP {direction} timed out after {self.SCP_TIMEOUT_SECONDS} seconds"
                logger.warning(
                    f"{last_error} for {self.host_id} (attempt {attempt + 1}/2)"
                )
                if attempt == 0:
                    NativeSSH.cleanup_control_master(self.host_id)
                    continue
                raise Exception(last_error) from exc

            if result.returncode == 0:
                return

            try:
                stderr = result.stderr.decode("utf-8")
            except UnicodeDecodeError:
                stderr = result.stderr.decode("utf-8", errors="replace")

            last_error = stderr.strip() or f"scp exited with code {result.returncode}"
            logger.warning(
                f"SCP {direction} failed for {self.host_id} "
                f"(attempt {attempt + 1}/2): {last_error}"
            )
            # Missing log files and file permissions are not broken transports.
            # Retrying them after closing ControlMaster would create needless
            # authentication attempts on every background output refresh.
            permanent_error = any(
                message in last_error.lower()
                for message in (
                    "no such file",
                    "permission denied",
                    "not a regular file",
                    "no space left on device",
                    "read-only file system",
                )
            )
            if attempt == 0 and not permanent_error:
                NativeSSH.cleanup_control_master(self.host_id)
                continue
            raise Exception(f"Failed to {direction} file: {last_error}")

        raise Exception(f"Failed to {direction} file: {last_error}")

    @classmethod
    def cleanup_all(cls):
        """Clean up all ControlMaster connections."""
        NativeSSH.cleanup_all()
