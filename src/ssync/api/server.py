"""API server management utilities."""

import os
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import List, Optional

import requests
from urllib3.exceptions import InsecureRequestWarning

from ..utils.logging import setup_logger
from ..web.ssl_utils import generate_self_signed_cert

# Suppress SSL warnings for self-signed certificates
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

logger = setup_logger(__name__, "INFO")


class ServerManager:
    """Manages the ssync API server lifecycle.

    Uses config-based server discovery - no PID or log files needed.
    Server address comes from config, lifecycle managed via HTTP endpoints.
    """

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize ServerManager.

        Args:
            url: API server URL. If None, reads from config.
            api_key: API key for authentication. If None, reads from config.
        """
        from ..utils.config import config as global_config

        if url is None:
            self.url = global_config.api_settings.url
            self.host = global_config.api_settings.host
            self.port = global_config.api_settings.port
            self.use_https = global_config.api_settings.https
        else:
            from urllib.parse import urlparse

            self.url = url
            parsed = urlparse(url)
            self.host = parsed.hostname or "localhost"
            self.port = parsed.port or 8042
            self.use_https = parsed.scheme == "https"

        self.api_key = api_key if api_key is not None else global_config.api_key

    def _get_headers(self) -> dict:
        """Get headers including API key if available."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _get_check_url(self) -> tuple[str, str]:
        """Get the host and protocol for health checks."""
        check_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        protocol = "https" if self.use_https else "http"
        return check_host, protocol

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
        """Check if API server is running by hitting the health endpoint."""
        check_host, protocol = self._get_check_url()

        try:
            response = requests.get(
                f"{protocol}://{check_host}:{self.port}/health",
                timeout=5,
                verify=False,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def stop(self) -> bool:
        """Stop the running server via the shutdown endpoint."""
        if not self.is_running():
            logger.debug("Server is not running")
            return False

        check_host, protocol = self._get_check_url()

        try:
            response = requests.post(
                f"{protocol}://{check_host}:{self.port}/api/shutdown",
                headers=self._get_headers(),
                timeout=5,
                verify=False,
            )
            if response.status_code == 200:
                # Wait for server to actually stop
                for _ in range(10):
                    time.sleep(0.5)
                    if not self.is_running():
                        logger.info("API server stopped")
                        return True
                logger.warning("Server may not have stopped completely")
                return True
            else:
                logger.error(f"Shutdown request failed: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to stop server: {e}")
            return False

    def start(self, config_path: Optional[Path] = None) -> bool:
        """Start API server if not running.

        Args:
            config_path: Path to config file. If None, uses default.
        """
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
            # Build uvicorn command
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "ssync.web.app:app",
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

            # Set up environment
            env = {**os.environ}
            if config_path:
                env["SSYNC_CONFIG_PATH"] = str(config_path)

            # If binding to 0.0.0.0, add it to trusted hosts
            if self.host == "0.0.0.0":
                current_trusted = os.environ.get(
                    "SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1"
                )
                env["SSYNC_TRUSTED_HOSTS"] = f"{current_trusted},0.0.0.0"

            # Start the process as a daemon (no log file, output goes to /dev/null)
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )

            # Wait for API to become responsive
            check_host, protocol = self._get_check_url()
            start_time = time.time()
            max_wait = 30

            while time.time() - start_time < max_wait:
                time.sleep(0.5)

                try:
                    response = requests.get(
                        f"{protocol}://{check_host}:{self.port}/health",
                        timeout=2,
                        verify=False,
                    )
                    if response.status_code == 200:
                        logger.info(
                            f"API server started successfully on {protocol}://{self.host}:{self.port}"
                        )
                        return True
                except requests.exceptions.RequestException:
                    continue

            # Timeout reached
            logger.error(
                f"API server failed to become responsive within {max_wait} seconds. "
                f"Run 'ssync api' in foreground to debug."
            )
            return False

        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            return False

    def get_logs(self, lines: int = 50) -> Optional[List[str]]:
        """Get recent logs from the API server via the /api/logs endpoint."""
        if not self.is_running():
            logger.debug("Server is not running, cannot fetch logs")
            return None

        check_host, protocol = self._get_check_url()

        try:
            response = requests.get(
                f"{protocol}://{check_host}:{self.port}/api/logs",
                params={"lines": lines},
                headers=self._get_headers(),
                timeout=5,
                verify=False,
            )
            if response.status_code == 200:
                return response.json().get("logs", [])
            else:
                logger.error(f"Failed to fetch logs: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch logs: {e}")
            return None
