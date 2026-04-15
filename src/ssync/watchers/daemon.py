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
from typing import List, Tuple

logger = logging.getLogger(__name__)


class WatcherDaemon:
    """Daemon process for running watchers."""

    PID_FILE = Path.home() / ".config" / "ssync" / "watcher-daemon.pid"
    LOG_FILE = Path.home() / ".config" / "ssync" / "watcher-daemon.log"

    @classmethod
    def _list_run_watcher_processes(cls) -> List[Tuple[int, str]]:
        """Find all standalone watcher runner processes across worktrees."""
        try:
            result = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return []

            processes: List[Tuple[int, str]] = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or "run_watchers.py" not in line:
                    continue

                pid_str, _, args = line.partition(" ")
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue

                if pid == os.getpid():
                    continue

                processes.append((pid, args.strip()))

            return processes
        except Exception as e:
            logger.warning(f"Failed to list watcher daemon processes: {e}")
            return []

    @classmethod
    def script_path(cls) -> Path:
        """Return the watcher runner entrypoint path."""
        return Path(__file__).resolve().parents[3] / "utils" / "run_watchers.py"

    @classmethod
    def is_running(cls) -> bool:
        """Check if daemon is already running."""
        if not cls.PID_FILE.exists():
            return bool(cls._list_run_watcher_processes())

        try:
            pid = int(cls.PID_FILE.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            # Process doesn't exist or invalid PID
            cls.PID_FILE.unlink(missing_ok=True)
            return bool(cls._list_run_watcher_processes())

    @classmethod
    def stop_all(cls) -> int:
        """Stop every standalone run_watchers.py process sharing the global cache."""
        processes = cls._list_run_watcher_processes()
        stopped = 0

        for pid, args in processes:
            try:
                os.kill(pid, signal.SIGTERM)
                stopped += 1
                logger.info(f"Stopped watcher runner process {pid}: {args}")
            except ProcessLookupError:
                continue
            except Exception as e:
                logger.warning(f"Failed to stop watcher runner process {pid}: {e}")

        if stopped:
            deadline = time.time() + 5
            while time.time() < deadline:
                remaining = [pid for pid, _ in cls._list_run_watcher_processes()]
                if not remaining:
                    break
                time.sleep(0.1)

            for pid, args in cls._list_run_watcher_processes():
                try:
                    os.kill(pid, signal.SIGKILL)
                    logger.warning(f"Killed stuck watcher runner process {pid}: {args}")
                except ProcessLookupError:
                    continue
                except Exception as e:
                    logger.warning(
                        f"Failed to kill stuck watcher runner process {pid}: {e}"
                    )

        cls.PID_FILE.unlink(missing_ok=True)
        return stopped

    @classmethod
    def start(cls) -> bool:
        """Start the daemon if not already running."""
        cls.stop_all()

        if cls.is_running():
            logger.info("Watcher daemon already running")
            return True

        # Ensure config directory exists
        cls.PID_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Start daemon in background
        script_path = cls.script_path()

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
        stopped = cls.stop_all()
        if stopped == 0:
            logger.info("Watcher daemon not running")
        else:
            logger.info(f"Stopped {stopped} watcher daemon process(es)")
            return True
        return True

    @classmethod
    def ensure_running(cls) -> bool:
        """Ensure daemon is running, start if needed."""
        if not cls.is_running():
            return cls.start()
        return True


def start_daemon_if_needed():
    """Helper function to start daemon if needed."""
    return WatcherDaemon.ensure_running()
