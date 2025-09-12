"""
Watcher daemon that runs in the background to monitor all active watchers.
Can be started automatically when jobs are submitted.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class WatcherDaemon:
    """Daemon process for running watchers."""

    PID_FILE = Path.home() / ".config" / "ssync" / "watcher-daemon.pid"
    LOG_FILE = Path.home() / ".config" / "ssync" / "watcher-daemon.log"

    @classmethod
    def is_running(cls) -> bool:
        """Check if daemon is already running."""
        if not cls.PID_FILE.exists():
            return False

        try:
            pid = int(cls.PID_FILE.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            # Process doesn't exist or invalid PID
            cls.PID_FILE.unlink(missing_ok=True)
            return False

    @classmethod
    def start(cls) -> bool:
        """Start the daemon if not already running."""
        if cls.is_running():
            logger.info("Watcher daemon already running")
            return True

        # Ensure config directory exists
        cls.PID_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Start daemon in background
        script_path = Path(__file__).parent.parent.parent.parent / "run_watchers.py"

        cmd = [sys.executable, str(script_path)]

        # Start process in background, redirecting output to log file
        with open(cls.LOG_FILE, "a") as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # Detach from parent
                cwd=str(script_path.parent),
            )

        # Write PID file
        cls.PID_FILE.write_text(str(process.pid))

        # Give it a moment to start
        time.sleep(1)

        # Verify it started
        if cls.is_running():
            logger.info(f"Started watcher daemon (PID: {process.pid})")
            return True
        else:
            logger.error("Failed to start watcher daemon")
            return False

    @classmethod
    def stop(cls) -> bool:
        """Stop the daemon if running."""
        if not cls.is_running():
            logger.info("Watcher daemon not running")
            return True

        try:
            pid = int(cls.PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            cls.PID_FILE.unlink(missing_ok=True)
            logger.info(f"Stopped watcher daemon (PID: {pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to stop daemon: {e}")
            return False

    @classmethod
    def ensure_running(cls) -> bool:
        """Ensure daemon is running, start if needed."""
        if not cls.is_running():
            return cls.start()
        return True


def start_daemon_if_needed():
    """Helper function to start daemon if needed."""
    return WatcherDaemon.ensure_running()
