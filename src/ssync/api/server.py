"""API server management utilities."""

import os
import signal
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from urllib3.exceptions import InsecureRequestWarning

from ..utils.logging import setup_logger
from ..web.ssl_utils import generate_self_signed_cert

# Suppress SSL warnings for self-signed certificates
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

logger = setup_logger(__name__, "INFO")


class ServerManager:
    """Manages the ssync API server lifecycle."""

    def __init__(self, base_url: str = "https://localhost:8042"):
        self.base_url = base_url
        parsed = urlparse(base_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 8042
        self.use_https = parsed.scheme == "https"
        self.pid_file = Path.home() / ".config" / "ssync" / "api-server.pid"
        self.log_file = Path.home() / ".config" / "ssync" / "api-server.log"

    def _ensure_dirs(self):
        """Ensure required directories exist."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

    def _save_pid(self, pid: int):
        """Save process PID to file."""
        self._ensure_dirs()
        self.pid_file.write_text(str(pid))

    def _get_saved_pid(self) -> Optional[int]:
        """Get saved PID if exists."""
        if self.pid_file.exists():
            try:
                return int(self.pid_file.read_text().strip())
            except (ValueError, IOError):
                return None
        return None

    def _is_process_running(self, pid: int) -> bool:
        """Check if process with given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _check_uvicorn_available(self) -> bool:
        """Check if uvicorn is available."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "uvicorn", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_port_available(self) -> bool:
        """Check if the port is available for binding."""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
            sock.close()
            return True
        except (OSError, socket.error) as e:
            logger.debug(f"Port {self.port} check failed: {e}")
            return False

    def is_running(self) -> bool:
        """Check if API server is running."""
        # First check if we have a PID and process is running
        pid = self._get_saved_pid()
        if pid and self._is_process_running(pid):
            # Verify it's actually our API server by checking the endpoint
            try:
                protocol = "https" if self.use_https else "http"
                response = requests.get(
                    f"{protocol}://{self.host}:{self.port}/health",
                    timeout=2,
                    verify=False,
                )
                return response.status_code == 200
            except requests.exceptions.RequestException:
                # Process exists but API not responding, might be starting up
                return False

        # No PID or process not running, check if something else is on the port
        if not self._check_port_available():
            # Port is in use, check if it's our API
            try:
                protocol = "https" if self.use_https else "http"
                response = requests.get(
                    f"{protocol}://{self.host}:{self.port}/health",
                    timeout=2,
                    verify=False,
                )
                # It's our API but we don't have the PID
                if response.status_code == 200:
                    logger.warning("API server running but PID unknown")
                    return True
            except requests.exceptions.RequestException:
                pass

        return False

    def stop(self) -> bool:
        """Stop the running server."""
        pid = self._get_saved_pid()
        if pid and self._is_process_running(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                # Wait for graceful shutdown
                for _ in range(10):
                    time.sleep(0.5)
                    if not self._is_process_running(pid):
                        break
                else:
                    # Force kill if still running
                    os.kill(pid, signal.SIGKILL)

                logger.info(f"Stopped API server (PID: {pid})")
                self.pid_file.unlink(missing_ok=True)
                return True
            except Exception as e:
                logger.error(f"Failed to stop API server: {e}")
                return False

        # Clean up stale PID file
        self.pid_file.unlink(missing_ok=True)
        return False

    def start(self, config_path: Path) -> bool:
        """Start API server if not running."""
        if self.is_running():
            logger.debug("API server already running")
            return True

        # Check dependencies
        if not self._check_uvicorn_available():
            logger.error(
                "uvicorn is not installed. Please install it with: pip install uvicorn"
            )
            return False

        # Check port availability
        if not self._check_port_available():
            logger.error(f"Port {self.port} is already in use by another process")
            return False

        logger.info(
            f"Starting ssync API server on {self.host}:{self.port} (HTTPS: {self.use_https})"
        )

        try:
            self._ensure_dirs()

            # Build uvicorn command
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "ssync.web.app:app",  # Fixed module path
                "--host",
                self.host,
                "--port",
                str(self.port),
            ]

            # Add SSL if needed
            if self.use_https:
                cert_path, key_path = generate_self_signed_cert()
                cmd.extend(
                    ["--ssl-keyfile", str(key_path), "--ssl-certfile", str(cert_path)]
                )

            # Open log file for output
            log_fd = open(self.log_file, "w")

            # Start the process with proper stdin handling to avoid TTY issues
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,  # Critical: prevents TTY issues with SSH
                stdout=log_fd,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                start_new_session=True,  # Detach from parent
                env={
                    **os.environ,
                    "SSYNC_CONFIG_PATH": str(config_path),
                },  # Pass config path
            )

            # Save PID
            self._save_pid(process.pid)
            logger.debug(f"Started API server with PID: {process.pid}")

            # Wait for API to become responsive
            protocol = "https" if self.use_https else "http"
            start_time = time.time()
            max_wait = 15  # Maximum seconds to wait

            while time.time() - start_time < max_wait:
                time.sleep(0.5)

                # Check if process is still running
                if not self._is_process_running(process.pid):
                    # Process died, check logs
                    log_fd.close()
                    if self.log_file.exists():
                        logs = self.log_file.read_text()
                        logger.error(f"API server failed to start. Logs:\n{logs}")
                    else:
                        logger.error("API server failed to start (no logs available)")
                    self.pid_file.unlink(missing_ok=True)
                    return False

                # Try to connect
                try:
                    response = requests.get(
                        f"{protocol}://{self.host}:{self.port}/health",
                        timeout=2,
                        verify=False,
                    )
                    if response.status_code == 200:
                        logger.info(
                            f"API server started successfully on {protocol}://{self.host}:{self.port}"
                        )
                        log_fd.close()
                        return True
                except requests.exceptions.RequestException:
                    # Not ready yet, keep waiting
                    continue

            # Timeout reached
            log_fd.close()
            logger.error(
                f"API server failed to become responsive within {max_wait} seconds"
            )

            # Check if still running and show logs
            if self._is_process_running(process.pid):
                if self.log_file.exists():
                    logs = self.log_file.read_text()
                    if logs:
                        logger.error(f"API server logs:\n{logs}")
                # Kill the unresponsive process
                self.stop()

            return False

        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            return False

    def get_logs(self, lines: int = 50) -> Optional[str]:
        """Get recent logs from the API server."""
        if self.log_file.exists():
            try:
                with open(self.log_file, "r") as f:
                    all_lines = f.readlines()
                    return "".join(all_lines[-lines:])
            except Exception as e:
                logger.error(f"Failed to read logs: {e}")
        return None
