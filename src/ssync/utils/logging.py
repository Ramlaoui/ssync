import logging
import sys
from collections import deque
from threading import Lock
from typing import List, Optional

COLORS = {
    "DEBUG": "\033[94m",  # Blue
    "INFO": "\033[92m",  # Green
    "WARNING": "\033[93m",  # Yellow
    "ERROR": "\033[91m",  # Red
    "CRITICAL": "\033[95m",  # Magenta
    "ENDC": "\033[0m",  # Reset color
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""

    def format(self, record):
        levelname = record.levelname
        if levelname in COLORS:
            record.levelname = f"{COLORS[levelname]}{levelname}{COLORS['ENDC']}"
        return super().format(record)


class MemoryLogHandler(logging.Handler):
    """Handler that stores log records in memory for API access."""

    def __init__(self, max_entries: int = 1000):
        super().__init__()
        self.max_entries = max_entries
        self._logs: deque = deque(maxlen=max_entries)
        self._lock = Lock()
        # Use a plain formatter without colors for API output
        self.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._lock:
                self._logs.append(msg)
        except Exception:
            self.handleError(record)

    def get_logs(self, lines: int = 50) -> List[str]:
        """Get the most recent log entries."""
        with self._lock:
            logs = list(self._logs)
        return logs[-lines:] if lines < len(logs) else logs

    def clear(self) -> None:
        """Clear all stored logs."""
        with self._lock:
            self._logs.clear()


# Global memory log handler instance
_memory_handler: Optional[MemoryLogHandler] = None


def get_memory_handler() -> MemoryLogHandler:
    """Get or create the global memory log handler."""
    global _memory_handler
    if _memory_handler is None:
        _memory_handler = MemoryLogHandler()
    return _memory_handler


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Set up and return a logger with colored console output.

    Args:
        name: The name of the logger (typically __name__)
        level: The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
              If None, defaults to INFO

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)

    log_level = getattr(logging, level.upper()) if level else logging.INFO
    logger.setLevel(log_level)

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        formatter = ColoredFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def enable_memory_logging(level: Optional[str] = None) -> None:
    """Enable memory logging for API access.

    Call this when starting the API server to capture logs in memory.
    """
    memory_handler = get_memory_handler()
    log_level = getattr(logging, level.upper()) if level else logging.INFO
    memory_handler.setLevel(log_level)

    # Add to root logger to capture all logs
    root_logger = logging.getLogger()
    if memory_handler not in root_logger.handlers:
        root_logger.addHandler(memory_handler)
