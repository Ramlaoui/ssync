"""API server management utilities."""

import subprocess
import time
from pathlib import Path

import requests

from ..utils.logging import setup_logger

logger = setup_logger(__name__, "DEBUG")


class ServerManager:
    """Manages the ssync API server lifecycle."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def is_running(self) -> bool:
        """Check if API server is running."""
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def start(self, config_path: Path) -> bool:
        """Start API server if not running."""
        if self.is_running():
            return True

        logger.debug("Starting ssync API server...")
        try:
            # Start API server in background
            cmd = [
                "uvicorn",
                "src.ssync.web.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ]

            # Start in background, detached from terminal
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent
                cwd=Path(
                    __file__
                ).parent.parent.parent.parent,  # Set working directory to project root
            )

            # Wait for API to start
            for i in range(20):  # Wait up to 10 seconds
                time.sleep(0.5)
                if self.is_running():
                    logger.debug("API server started successfully")
                    return True

            logger.debug("Failed to start API server")
            return False

        except Exception as e:
            logger.debug(f"Failed to start API server: {e}")
            return False
